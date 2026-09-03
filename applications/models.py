from django.db import models
from decimal import Decimal
from django.conf import settings
from . import functions as Essco_Functions
from django.core.validators import RegexValidator
import logging
from django.db.models.signals import pre_save
from django.dispatch import receiver
from datetime import date
from loans.models import LoanProduct
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


# ✅ Correct import for your file structure
from services.payroll_service import PayrollService

logger = logging.getLogger(__name__)

no_spaces_validator = RegexValidator(regex=r"^[^\s]+$", message="Spaces are not allowed.", code="no_spaces",)

def get_default_empty_string():
    """Return an empty string as the default value"""
    return 'test'

def get_default_zero():
    """Return zero as the default value"""
    return 0.00

#########################################################################################################################################################
#########################################
###########################################################################################################################################################

class InterestRate(models.Model):
    """
    Model to store interest rates for loan products.
    Can be managed by admin users without code changes.
    """
    # Rate identification
    name = models.CharField(max_length=100, unique=True, help_text="e.g., 'low'/Approved pending, 'Medium'/Human Review, 'High'/Rejected")

    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Interest rate as percentage (e.g., 5.00 = 5%)")

    # Applicable ranges
    min_loan_amount = models.DecimalField(max_digits=12, decimal_places=2, default=500.00, help_text="Minimum loan amount for this rate")

    max_loan_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Maximum loan amount (leave blank for no limit)")

    # Active/Inactive
    is_active = models.BooleanField(default=True, help_text="Uncheck to disable this rate without deleting")

    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_rates')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='updated_rates')

    # Additional notes
    notes = models.TextField(blank=True, null=True, help_text="Any additional information about this rate")

    class Meta:
        ordering = ['rate']
        verbose_name = "Interest Rate"
        verbose_name_plural = "Interest Rates"

    def __str__(self):
        return f"{self.name} - {self.rate}%"


#########################################################################################################################################################
#########################################
###########################################################################################################################################################

class StaffMember(models.Model):
    """Staff members who can receive email notifications"""

    ROLE_CHOICES = [
        ('manager', 'Manager'),
        ('supervisor', 'Supervisor'),
        ('agent', 'Agent'),
        ('admin', 'Admin'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    is_approval_recipient = models.BooleanField(default=False)  # ← The key field
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'staff_members'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.role}"


#########################################################################################################################################################
#########################################
###########################################################################################################################################################

class Interest_Rates(models.Model):
    Rate_Name = models.CharField(max_length=100, null=True, blank=True,)
    Rate_Value = models.DecimalField(max_digits=10, decimal_places=2)


#########################################################################################################################################################
#########################################
###########################################################################################################################################################

class ApplicationModel(models.Model):
    #Personal
    version = models.IntegerField(default=1)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='applications', null=True, blank=True)
    reference_number = models.CharField(max_length=20, unique=True, blank=True, null=True, help_text="Unique reference number for this application (e.g., ESS-000001)")
    prefix_options = [ ('Mr', 'Mr') , ('Mrs', 'Mrs'), ('Miss', 'Miss'), ('Ms', 'Ms')]
    Prefix = models.CharField(max_length=5, choices = prefix_options, default='Mr')
    Fname = models.CharField(max_length=100)
    Lname = models.CharField(max_length=100)
    DOB = models.DateField(default='2006-07-07')
    age = models.IntegerField(null=True, blank=True)
    Nationality = models.CharField(max_length=100)
    ID_number = models.CharField(max_length=100, validators=[no_spaces_validator])
    IDOptions = [ ('National ID card', 'National ID card'), ('Valid Passport', 'Valid Passport'), ('Valid Drivers license', 'Valid Drivers license' )]
    ID_Type = models.CharField(max_length=50, choices = IDOptions, default='National ID card')
    GenderOptions = [ ('Male', 'Male'), ('Female', 'Female')]
    Gender = models.CharField(max_length=50, choices = GenderOptions)
    MaritalOptions = [ ('Single', 'Single'), ('Married', 'Married'), ('Divorced', 'Divorced'), ('Widowed', 'Widowed')]
    Marital_Status = models.CharField(max_length=50, choices = MaritalOptions)
    #Num_Dependents = models.IntegerField()
    NumberOptions = [(i, i) for i in range(0, 10)]
    NumberOptions.append((10, '10+'))
    Num_Dependents = models.IntegerField(choices=NumberOptions)
    Parish_Options = [('Christ Church','Christ Church'), ('Saint Philip','Saint Philip'), ('Saint Michael','Saint Michael'), ('Saint Thomas','Saint Thomas'),
    ('Saint Peter','Saint Peter'), ('Saint Lucy','Saint Lucy'), ('Saint Joseph','Saint Joseph'), ('Saint John','Saint John'), ('Saint James','Saint James'),
    ('Saint George','Saint George'), ('Saint Andrew','Saint Andrew')]
    Parish = models.CharField(max_length=100, choices = Parish_Options, default = 'Christ Church')
    Address = models.CharField(max_length=100)
    Length_at_Address = models.IntegerField(choices=NumberOptions)
    Residential_Status_Options = [('Owner','Owner'), ('Tenant','Tenant'), ('Living with Parents','Living with Parents'), ('Shared Rental','Shared Rental')]
    Residential_Status = models.CharField(max_length=50, choices = Residential_Status_Options, default = 'Owner')
    Cell_Phone = models.CharField(max_length=20, help_text="e.g., 246-555-1234 or +12465551234", blank=False, null=False, default="+12465645676")
    Home_Phone = models.CharField(max_length=20, help_text="e.g., 246-555-1234 or +12465551234", blank=True, null=True, default="+12465645676")
    Work_Phone = models.CharField(max_length=20, help_text="e.g., 246-555-1234 or +12465551234", blank=True, null=True, default="+12465645676")
    #email = models.CharField(max_length=100)
    email = models.EmailField(max_length=254, help_text="Enter a valid email address")
    YNOptions = [ ('Yes', 'Yes'), ('No', 'No')]
    Existing_Customer = models.CharField(max_length=50, choices = YNOptions, default = 'Yes')

    #Employment Info
    Employer_Name = models.CharField(max_length=100)
    Employer_Address = models.CharField(max_length=100)
    EmployerOptions = [ ('Permanent', 'Permanent'), ('Contract', 'Contract'), ('Probationary', 'Probationary'), ('Self-Employed', 'Self-Employed')]
    Employer_Type = models.CharField(max_length=50, choices = EmployerOptions)
    Job_Title = models.CharField(max_length=100)
    less_than_six = models.CharField(max_length=50, choices = YNOptions)
    #Len_Employ = models.IntegerField(null=True, blank=True,)
    Employer_Num = models.CharField(max_length=20, help_text="e.g., 246-555-1234 or +12465551234", blank=False, null=False, default="+12465645676")
    Len_Employ_Options = [ ('2 + Years', '2 + Years'), ('6 months to 2 years', '6 months to 2 years'), ('Less than 6 months', 'Less than 6 months')]
    Len_Employ = models.CharField(max_length=50, choices = Len_Employ_Options, default = '2 + Years',)
    Gross_Monthly_Income = models.DecimalField(max_digits=10, decimal_places=2)
    Previous_Employer = models.CharField(max_length=100)

    # Financial Info
    Loan_mortgages_payments = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    CCPayments = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    Other_Debt_Payments = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    Rent = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    Transportation = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    Insurance = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    Other_Living_Expenses = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    food = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)
    utilities = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True, null=True)

    #Reference
    Reference1_FullName = models.CharField(max_length=100)
    Reference1_Relationship = models.CharField(max_length=100)
    Reference1_Employer = models.CharField(max_length=100)
    Reference1_Job_Title = models.CharField(max_length=100)
    Reference1_Contact_Number = models.CharField(max_length=20, help_text="e.g., 246-555-1234 or +12465551234", blank=False, null=False, default="+12465645676")
    Reference1_Len_Time_Known = models.IntegerField(choices=NumberOptions)
    Reference1_Address = models.CharField(max_length=100)

    Reference2_FullName = models.CharField(max_length=100)
    Reference2_Relationship = models.CharField(max_length=100)
    Reference2_Employer = models.CharField(max_length=100)
    Reference2_Job_Title = models.CharField(max_length=100)
    Reference2_Contact_Number = models.CharField(max_length=20, help_text="e.g., 246-555-1234 or +12465551234", blank=False, null=False, default="+12465645676")
    Reference2_Len_Time_Known = models.IntegerField(choices=NumberOptions)
    Reference2_Address = models.CharField(max_length=100)

    #File Fields
    #Identification
    Identification = models.FileField(upload_to=Essco_Functions.id_upload_path)
    #Proof of Income
    Payslip = models.FileField(upload_to=Essco_Functions.Payslip_upload_path, blank=True, null=True)
    Job_Letter = models.FileField(upload_to=Essco_Functions.Job_Letter_upload_path, blank=True, null=True)
    #Self-Employed Applicants
    Financial_Statement = models.FileField(upload_to=Essco_Functions.Financial_Statement_upload_path, blank=True, null=True)
    Bank_Statement = models.FileField(upload_to=Essco_Functions.Bank_Statement_upload_path, blank=True, null=True)
    Business_Registration = models.FileField(upload_to=Essco_Functions.Business_Registration_upload_path, blank=True, null=True)
    #Proof of Address
    Statement = models.FileField(upload_to=Essco_Functions.Statement_upload_path, blank=True, null=True)
    Utility_Bill = models.FileField(upload_to=Essco_Functions.Utility_Bill_upload_path, blank=True, null=True)
    #Additional Verification
    Selfie = models.FileField(upload_to=Essco_Functions.Selfie_upload_path)

    #Consent Fields
    accept_terms = models.BooleanField(default=False)

    #Fields Populated From Wordpress
    item_name = models.CharField(max_length=255, default=get_default_empty_string, help_text="Product name from WordPress")
    item_sku = models.CharField(max_length=100, default=get_default_empty_string, help_text="Product SKU from WordPress")
    Purchase_Value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Calculated
    Total_Monthly_living_expenses = models.DecimalField(max_digits=10, decimal_places=2)
    Total_Monthly_debt = models.DecimalField(max_digits=10, decimal_places=2)
    Monthly_Obligations = models.DecimalField(max_digits=10, decimal_places=2)
    Disposable_Income = models.DecimalField(max_digits=10, decimal_places=2)
    Debt_To_Income_Ratio = models.DecimalField(max_digits=10, decimal_places=2)
    Living_Expense_Ratio = models.DecimalField(max_digits=10, decimal_places=2)
    Total_Debt_Service_Ratio = models.DecimalField(max_digits=10, decimal_places=2)
    Approval_Status = models.CharField(max_length=100, default = 'Rejected')
    Total_Credit_Allowed = models.DecimalField(max_digits=10, decimal_places=2)
    Deposit = models.DecimalField(max_digits=10, decimal_places=2)
    Six = models.DecimalField(max_digits=10, decimal_places=2)
    Twelve = models.DecimalField(max_digits=10, decimal_places=2)
    Eighteen = models.DecimalField(max_digits=10, decimal_places=2)
    Twenty_Four = models.DecimalField(max_digits=10, decimal_places=2)
    Thirty = models.DecimalField(max_digits=10, decimal_places=2)
    Thirty_Six = models.DecimalField(max_digits=10, decimal_places=2)
    RR = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Resilience & Regeneration (0.25% of gross)")   #Resilence & Regenration
    NIS = models.DecimalField(max_digits=10, decimal_places=2)
    PAYE = models.DecimalField(max_digits=10, decimal_places=2)
    Gross_Monthly_Income_AT = models.DecimalField(max_digits=10, decimal_places=2)
    Financed_Amt = models.DecimalField(max_digits=10, decimal_places=2)

    # After Essco Fields
    Disposable_Income_After = models.DecimalField(max_digits=10, decimal_places=2)################################

    created = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_application')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='updated_application')

    #Human Review
    FA_Options = [ ('Human Approved', 'Human Approved'), ('Human Rejected', 'Human Rejected'), ('other', 'other')]
    Final_Approval = models.CharField(max_length=50, choices = FA_Options, default = 'other', null=True, blank=True,)
    Identification_Check = models.CharField(max_length=50, choices = YNOptions, default = 'No', null=True, blank=True,)
    Term_Options = [ ('Six', 'Six'), ('Twelve', 'Twelve'), ('Eighteen', 'Eighteen'), ('Twenty Four' , 'Twenty Four'), ('Thirty','Thirty'),('Thirty Six','Thirty Six'), ('other', 'other') ]
    Term = models.CharField(max_length=50, choices = Term_Options, default = 'Twenty Four', null=True, blank=True,)
    Notes = models.TextField(null=True, blank=True,)

    # ============================================================
    # DEPOSIT TRACKING FIELDS
    # ============================================================
    deposit_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Deposit amount paid")
    deposit_paid_date = models.DateTimeField(null=True, blank=True, help_text="When deposit was paid")
    deposit_payment_method = models.CharField(max_length=50, blank=True, null=True, help_text="How deposit was paid (Cash, POS, Bank Transfer, etc.)")
    deposit_receipt_number = models.CharField(max_length=50, blank=True, null=True, help_text="Receipt number for deposit payment")
    deposit_status_choices = [ ('PENDING', 'Pending'), ('PAID', 'Paid - Awaiting Loan Creation'), ('TRANSFERRED', 'Transferred to Loan'), ('REFUNDED', 'Refunded') ]
    deposit_status = models.CharField(max_length=20, choices = deposit_status_choices, default='PENDING', help_text="Status of the deposit payment")
    deposit_payment = models.ForeignKey('payments.PaymentRecord', on_delete=models.SET_NULL, null=True, blank=True, related_name='application_deposit')

    @property
    def loan(self):
        """Return the loan associated with this application, if any."""
        return LoanProduct.objects.filter(application=self).first()

    def __str__(self):
        """This defines what shows up in the admin list"""
        return f"{self.Fname} {self.Lname} {self.email}"

    def calculate_age(self):
        """Calculate age from DOB"""
        if not self.DOB:
            return None

        today = date.today()
        age = (
            today.year
            - self.DOB.year
            - ((today.month, today.day) < (self.DOB.month, self.DOB.day))
        )
        return age

    def get_rate_for_status(self):
        """
        Get the appropriate rate based on Approval_Status
        """
        from .models import InterestRate

        # Get rates based on status
        if self.Approval_Status == "Approved Pending":
            # Use LOW rate
            rate = InterestRate.objects.filter(
                name__iexact='low',
                is_active=True
            ).first()
        else:
            # Use HIGH rate for all other statuses
            rate = InterestRate.objects.filter(
                name__iexact='high',
                is_active=True
            ).first()

        # If specific rate not found, use default
        if not rate:
            rate = InterestRate.objects.filter(is_active=True).first()

        return rate


    def save(self, *args, **kwargs):

        if self.DOB:
            self.age = self.calculate_age()
        # ⭐ STEP 0: Calculate payroll FIRST (before any other calculations)
        if self.Gross_Monthly_Income and self.Gross_Monthly_Income > 0:
            try:
                payroll = PayrollService.calculate_payroll(self.Gross_Monthly_Income)
                self.PAYE = payroll['paye']['monthly_paye']
                self.NIS = payroll['nis']['monthly_nis']
                self.RR = payroll['rr']['monthly_rr']
                self.Gross_Monthly_Income_AT = payroll['gross_monthly_income_at']
            except Exception as e:
                logger.error(f"Error calculating payroll for {self}: {e}")
                self.PAYE = Decimal('0.00')
                self.NIS = Decimal('0.00')
                self.RR = Decimal('0.00')
                self.Gross_Monthly_Income_AT = self.Gross_Monthly_Income or Decimal('0.00')
        else:
            self.PAYE = Decimal('0.00')
            self.NIS = Decimal('0.00')
            self.RR = Decimal('0.00')
            self.Gross_Monthly_Income_AT = Decimal('0.00')

        #STEP 1: TOTAL MONTHLY LIVING EXPENSES
        self.Total_Monthly_living_expenses = ((self.food or Decimal("0.00")) + (self.utilities or Decimal("0.00")) + (self.Rent or Decimal("0.00"))
                                            + (self.Insurance or Decimal("0.00")) + (self.Other_Living_Expenses or Decimal("0.00")) + (self.Transportation or Decimal("0.00")))

        #STEP 2: TOTAL MONTHLY DEBT
        self.Total_Monthly_debt = ((self.Loan_mortgages_payments or Decimal("0.00")) + (self.CCPayments or Decimal("0.00")) + (self.Other_Debt_Payments or Decimal("0.00")))

        #STEP 3: MONTHLY OBLIGATIONS
        self.Monthly_Obligations = (self.Total_Monthly_debt + self.Total_Monthly_living_expenses)

        #STEP 4: DISPOSABLE INCOME
        self.Disposable_Income = ((self.Gross_Monthly_Income_AT or Decimal("0.00")) - self.Monthly_Obligations)

        # STEP 5-7: FINANCIAL RATIOS - DEBT-TO-INCOME RATIO, LIVING EXPENSES RATIO and TOTAL DEBT SERVICE RATIO

        income = self.Gross_Monthly_Income or Decimal("0.00")

        # ✅ Convert income to Decimal before using it
        income = self.Gross_Monthly_Income or Decimal("0.00")
        income = Decimal(str(income))  # ✅ Convert to Decimal

        if income > 0:
            self.Debt_To_Income_Ratio = (self.Total_Monthly_debt / income) * Decimal("100")
            self.Living_Expense_Ratio = (self.Total_Monthly_living_expenses / income) * Decimal("100")
            self.Total_Debt_Service_Ratio = ((self.Total_Monthly_debt + self.Total_Monthly_living_expenses) / income) * Decimal("100")
        else:
            self.Debt_To_Income_Ratio = Decimal("0.00")
            self.Living_Expense_Ratio = Decimal("0.00")
            self.Total_Debt_Service_Ratio = Decimal("0.00")

        ########### this is where step 8 was I had to move it because variables it needed are calculated in steps 13 and 14
        ########### this is where step 9 was It was dependent on the outcome of step 8

        #STEP 10: DEPOSIT
        purchase_value = Decimal(str(self.Purchase_Value or 0))
        self.Deposit = purchase_value * Decimal("0.20")

        #STEP 11: FINANCED AMOUNT
        self.Financed_Amt = purchase_value - self.Deposit

        #Step 12: TRA - Total Repayable Amount (Including Interest) for all plans 6-36
        #Formula: Interest = Financed Amount × Annual Interest Rate × Term (in years) -> Interest is calculated on the full finance amount
        #Formula: TRA = Financed Amount + Interest
        Rate_obj = self.get_rate_for_status()
        if Rate_obj:
            Rate = Rate_obj.rate / 100
        else:
            Rate = Decimal("0.00")  # Default if no rate found

        Six_Interest = self.Financed_Amt * Rate * Decimal("0.5")
        Twelve_Interest = self.Financed_Amt * Rate * Decimal("1")
        Eighteen_Interest = self.Financed_Amt * Rate * Decimal("1.5")
        Twenty_Four_Interest = self.Financed_Amt * Rate * Decimal("2")
        Thirty_Interest = self.Financed_Amt * Rate * Decimal("2.5")
        Thirty_Six_Interest = self.Financed_Amt * Rate * Decimal("3")

        TRA6 = self.Financed_Amt + Six_Interest
        TRA12 = self.Financed_Amt + Twelve_Interest
        TRA18 = self.Financed_Amt + Eighteen_Interest
        TRA24 = self.Financed_Amt + Twenty_Four_Interest
        TRA30 = self.Financed_Amt + Thirty_Interest
        TRA36 = self.Financed_Amt + Thirty_Six_Interest

        #STEP 13: Monthly Payment plans and thier respective amounts
        #Formula: Monthly Payment = Total Repayable ÷ Number of Months -> The total repayable amount is divided equally across the repayment term.
        self.Six = TRA6/Decimal(6)
        self.Twelve = TRA12/Decimal(12)
        self.Eighteen = TRA18/Decimal(18)
        self.Twenty_Four = TRA24/Decimal(24)
        self.Thirty = TRA30/Decimal(30)
        self.Thirty_Six = TRA36/Decimal(36)

        #Step 14: Disposable income after essco |::| This is the subtraction of the monthly payment from the disposable income
        disposable = self.Disposable_Income or Decimal("0.00")

        if self.Term == "Six":
            self.Disposable_Income_After = disposable - self.Six
        elif self.Term == "Twelve":
            self.Disposable_Income_After = disposable - self.Twelve
        elif self.Term == "Eighteen":
            self.Disposable_Income_After = disposable - self.Eighteen
        elif self.Term == "Twenty Four":
            self.Disposable_Income_After = disposable - self.Twenty_Four
        elif self.Term == "Thirty":
            self.Disposable_Income_After = disposable - self.Thirty
        elif self.Term == "Thirty Six":
            self.Disposable_Income_After = disposable - self.Thirty_Six
        else:
            self.Disposable_Income_After = disposable

        print("DTI:", self.Debt_To_Income_Ratio)
        print("Living:", self.Living_Expense_Ratio)
        print("TDS:", self.Total_Debt_Service_Ratio)
        print("Disposable After:", self.Disposable_Income_After)
        print("Income:", self.Gross_Monthly_Income)

        logger.info(
            "Approval check | DTI=%s | Living=%s | TDS=%s | Disposable=%s | Income=%s",
            self.Debt_To_Income_Ratio,
            self.Living_Expense_Ratio,
            self.Total_Debt_Service_Ratio,
            self.Disposable_Income_After,
            self.Gross_Monthly_Income,
        )


        #STEP 8: APPROVAL STATUS
        # Check for automatic rejection
        #if (self.Debt_To_Income_Ratio > 50 or self.Living_Expense_Ratio > 45 or self.Total_Debt_Service_Ratio > 95 or self.Disposable_Income_After < 350 or
              #(self.Gross_Monthly_Income or Decimal("0.00")) <= 1999):
                  #self.Approval_Status = 'Rejected'

        # Check for automatic rejection
        if (self.Disposable_Income_After < 350 or (self.Gross_Monthly_Income or Decimal("0.00")) <= 1999):
            self.Approval_Status = 'Rejected'

        # Check for Approved Pending
        elif (self.Debt_To_Income_Ratio <= 40 and self.Living_Expense_Ratio <= 35 and self.Total_Debt_Service_Ratio <= 75 and
            self.Disposable_Income_After >= 350 and self.Employer_Type == 'Permanent' and (self.Gross_Monthly_Income or Decimal("0.00")) >= 2000):
                self.Approval_Status = 'Approved Pending'

        # Everything else goes to Human Review
        else:
            self.Approval_Status = 'Human Review'

        # ✅ Fixed - Convert to Decimal first
        income = Decimal(str(self.Gross_Monthly_Income or 0))

        if self.Approval_Status == 'Approved Pending':
            self.Total_Credit_Allowed = income * Decimal("2.5")
        elif self.Approval_Status == 'Human Review':
            self.Total_Credit_Allowed = income * Decimal("1.5")
        else:
            self.Total_Credit_Allowed = Decimal("0.00")


        super().save(*args, **kwargs)


#########################################################################################################################################################
#########################################
###########################################################################################################################################################

class EmailLog(models.Model):
    EMAIL_TYPES = [
        ('APPROVAL', 'Approval Email'),
        ('STAFF_NOTIFICATION', 'Staff Notification'),
        ('APPLICATION_CONFIRMATION', 'Application Confirmation'),
        ('REMINDER', 'Payment Reminder'),
        ('REGISTRATION', 'Registration Link'),
        ('REJECTION', 'Rejection Email'),
    ]

    email_type = models.CharField(max_length=50, choices=EMAIL_TYPES)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='sent')
    message_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['sent_at']),
            models.Index(fields=['email_type']),
        ]

    def __str__(self):
        return f"{self.email_type} to {self.recipient} at {self.sent_at}"