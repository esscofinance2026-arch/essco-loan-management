# payments/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.db import transaction
from audit.services import log_action
from loans.views import apply_payment_to_schedule
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

# Create your models here.

class PaymentMethod(models.Model):
    METHOD_TYPES = [
        ('CASH', 'Cash'),
        ('POS', 'POS/Card'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('MOBILE_MONEY', 'Mobile Money'),
    ]

    name = models.CharField(max_length=50)
    method_type = models.CharField(max_length=20, choices=METHOD_TYPES)
    is_active = models.BooleanField(default=True)
    requires_manual_confirmation = models.BooleanField(default=False)
    settlement_days = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.method_type})"


class PaymentRecord(models.Model):
    PAYMENT_CATEGORIES = [
        ('DEPOSIT', 'Deposit'),
        ('INSTALLMENT', 'Installment'),
        ('LATE_FEE', 'Late Fee'),
        ('FULL_SETTLEMENT', 'Full Settlement'),
        ('PARTIAL', 'Partial Payment'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending Confirmation'),
        ('CONFIRMED', 'Confirmed'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
        ('REVERSED', 'Reversed'),
    ]
    #######
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reversed_payments'
    )
    reversal_reason = models.CharField(max_length=255, blank=True, null=True)

    # Relationships
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payments', null=True, blank=True)
    application = models.ForeignKey('applications.ApplicationModel', on_delete=models.SET_NULL, null=True, blank=True)

    loan = models.ForeignKey('loans.LoanProduct', on_delete=models.SET_NULL, null=True, blank=True,related_name='payments')

    # Payment details
    receipt_number = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=20, choices=PAYMENT_CATEGORIES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    #payment_date = models.DateTimeField(auto_now_add=True)
    payment_date = models.DateTimeField(default=timezone.now)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_payments')
    confirmed_at = models.DateTimeField(null=True, blank=True)

    # Additional fields
    auto_create_loan = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    # Allocation
    principal_applied = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    interest_applied = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fees_applied = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_applied = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Deposit portion applied at confirmation time")

    # Audit
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='recorded_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    quickbooks_payment_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.receipt_number} - {self.category} - ${self.amount}"

    @property
    def has_split(self):
        """Return True if this payment was split internally."""
        # Check if the payment has any excess applied to an installment
        if self.category == 'DEPOSIT' and self.loan:
            # Check if the notes mention "Installment portion"
            return 'Installment portion' in self.notes
        return False

    @property
    def split_details(self):
        """Return a dict with split allocation details."""
        if not self.has_split:
            return None

        # Calculate deposit amount applied
        deposit_portion = self.amount - self.principal_applied
        installment_portion = self.principal_applied

        return {
            'total_amount': self.amount,
            'deposit_portion': deposit_portion,
            'installment_portion': installment_portion,
            'deposit_complete': self.loan.deposit_complete if self.loan else False,
            'outstanding_balance': self.loan.outstanding_balance if self.loan else 0,
        }

    # payments/models.py - Update the PaymentRecord model

    @property
    def deposit_portion(self):
        """
        Get deposit portion - uses stored deposit_applied if available,
        otherwise calculates dynamically.
        """
        # ✅ If deposit_applied is set, use it
        if self.deposit_applied > 0:
            return self.deposit_applied

        # Fallback to dynamic calculation
        remaining = self.amount - self.principal_applied - self.interest_applied - self.fees_applied

        if remaining <= 0:
            return Decimal('0.00')

        if self.loan:
            deposit_target = Decimal(str(self.loan.deposit_target or 0))
            if deposit_target == 0:
                return Decimal('0.00')

            # Calculate deposit already paid (EXCLUDING this payment)
            deposit_paid = Decimal('0.00')
            for payment in self.loan.payments.filter(
                status='CONFIRMED',
                is_reversed=False
            ).exclude(id=self.id):
                deposit_paid += payment.deposit_portion

            if deposit_paid >= deposit_target:
                return Decimal('0.00')

            remaining_deposit_needed = deposit_target - deposit_paid
            return min(remaining, remaining_deposit_needed)

        return Decimal('0.00')

    def _calculate_deposit_portion(self):
        """
        Calculate deposit portion without using stored value.
        Used at confirmation time to capture the correct amount.
        """
        remaining = self.amount - self.principal_applied - self.interest_applied - self.fees_applied

        if remaining <= 0:
            return Decimal('0.00')

        if self.loan:
            deposit_target = Decimal(str(self.loan.deposit_target or 0))
            if deposit_target == 0:
                return Decimal('0.00')

            # Calculate deposit already paid (EXCLUDING this payment)
            deposit_paid = Decimal('0.00')
            for payment in self.loan.payments.filter(
                status='CONFIRMED',
                is_reversed=False
            ).exclude(id=self.id):
                deposit_paid += payment.deposit_applied  # Use stored value

            if deposit_paid >= deposit_target:
                return Decimal('0.00')

            remaining_deposit_needed = deposit_target - deposit_paid
            return min(remaining, remaining_deposit_needed)

        return Decimal('0.00')

    def update_loan_deposit_status(self):
        """Update the loan's deposit status based on all confirmed payments"""
        if not self.loan:
            return

        loan = self.loan

        # Calculate total deposit paid from all confirmed payments
        total_deposit_paid = Decimal('0.00')
        for payment in loan.payments.filter(
            status='CONFIRMED',
            is_reversed=False
        ):
            # Use the deposit_portion property
            total_deposit_paid += payment.deposit_portion

        # Update loan deposit fields
        loan.deposit_paid = total_deposit_paid

        # Check if deposit target is met
        deposit_target = Decimal(str(loan.deposit_target or 0))
        if deposit_target > 0 and total_deposit_paid >= deposit_target:
            loan.deposit_complete = True
        else:
            loan.deposit_complete = False

        loan.save()


    # payments/models.py - Fixed _update_loan_totals

    def update_loan_totals(self):
        """Update loan totals from all active payments"""
        if not self.loan:
            return

        loan = self.loan
        active_payments = loan.payments.filter(
            is_reversed=False,
            status='CONFIRMED'
        )

        # ✅ Total paid = sum of all payments (including deposits)
        total_paid = sum(p.amount for p in active_payments) or Decimal('0.00')
        loan.total_paid = total_paid

        # ✅ Calculate total principal paid from ALL payments
        total_principal_paid = Decimal('0.00')
        for payment in active_payments:
            total_principal_paid += payment.principal_applied

        # ✅ Outstanding principal = Financed Amount - Principal Paid
        # Use Financed_Amt from application, or principal_amount as fallback
        if loan.application and loan.application.Financed_Amt:
            financed_amount = Decimal(str(loan.application.Financed_Amt))
        else:
            financed_amount = loan.principal_amount

        loan.outstanding_balance = financed_amount - total_principal_paid
        if loan.outstanding_balance < 0:
            loan.outstanding_balance = Decimal('0.00')

        # ✅ Calculate total deposit paid
        total_deposit_paid = Decimal('0.00')
        for payment in active_payments:
            if payment.category == 'DEPOSIT':
                total_deposit_paid += payment.amount

        loan.deposit_paid = total_deposit_paid

        # ✅ Check if deposit is complete
        deposit_target = Decimal(str(loan.deposit_target or 0))
        if deposit_target > 0 and total_deposit_paid >= deposit_target:
            loan.deposit_complete = True
        else:
            loan.deposit_complete = False

        # ✅ Update status
        if loan.outstanding_balance <= 0:
            loan.status = 'PAID_OFF'
        elif not loan.deposit_complete and loan.deposit_target > 0:
            loan.status = 'DRAFT'
        elif total_paid == 0:
            loan.status = 'DRAFT'
        else:
            loan.status = 'ACTIVE'

        loan.save()

    @transaction.atomic
    def confirm(self, user):
        """Confirm payment and trigger loan creation"""
        print(f"🔍 DEBUG: confirm() called for payment {self.receipt_number}")
        print(f"   Payment status: {self.status}")
        print(f"   Has application: {self.application}")
        print(f"   Application email: {self.application.email if self.application else 'None'}")
        if self.status != 'PENDING':
            raise ValueError(f"Cannot confirm payment with status: {self.status}")

        self.status = 'CONFIRMED'
        self.confirmed_by = user
        self.confirmed_at = timezone.now()
        self.save()

        # ==========================================
        # ✅ CUSTOMER ACCOUNT CREATION (IF NEEDED)
        # ==========================================
        # Get customer email from application
        if self.application and self.application.email:
            # Check if User already exists
            User = get_user_model()

            existing_user = User.objects.filter(email=self.application.email).first()

            if existing_user:
                # Link existing user to payment
                self.customer = existing_user
                self.save()
            else:
                # Create new user
                new_user = User.objects.create_user(
                    username=self.application.email,
                    email=self.application.email,
                    first_name=self.application.Fname,
                    last_name=self.application.Lname,
                    role='customer'
                )
                # Link to payment
                self.customer = new_user
                self.save()

            # Generate customer_id if not exists
            if self.customer and not self.customer.customer_id:
                from applications.utils import generate_customer_id
                self.customer.customer_id = generate_customer_id(
                    self.customer.first_name,
                    self.customer.last_name
                )
                self.customer.save()

        # ✅ Store the deposit portion at confirmation time
        if self.loan:
            # Calculate deposit portion BEFORE updating loan
            deposit_calc = self._calculate_deposit_portion()
            self.deposit_applied = deposit_calc
            self.save()

        # Update loan total paid
        if self.loan:
            self.update_loan_totals()
            self.update_loan_deposit_status()

        # If this is a deposit with auto_create_loan, trigger loan creation
        if self.category == 'DEPOSIT' and self.auto_create_loan:
            try:
                from loans.services.loan_creation_service import LoanCreationService
                loan = LoanCreationService.handle_deposit_confirmation(self)
                if loan:
                    # Update the payment with the loan reference
                    self.loan = loan
                    self.save()
                    # Update loan totals again after loan is created
                    self._update_loan_totals()
            except Exception as e:
                # Log but don't fail - let the user try again
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Loan creation failed on confirm: {str(e)}")

        # ==========================================
        # ✅ LOG THE CONFIRMATION
        # ==========================================

        log_action(
            request=None,
            user=user,
            action='PAYMENT_CONFIRMED',
            description=(
                f"Payment {self.receipt_number} confirmed. "
                f"Amount: ${self.amount}. "
                f"Category: {self.category}. "
                f"Loan: {self.loan.loan_id if self.loan else 'N/A'}"
            ),
            loan=self.loan,
            ip_address=None
        )

        return self

class PaymentReversal(models.Model):
    """
    Track payment reversals for audit purposes
    """
    REASON_CHOICES = [
        ('DUPLICATE', 'Duplicate Payment'),
        ('WRONG_AMOUNT', 'Wrong Amount'),
        ('CUSTOMER_REQUEST', 'Customer Request'),
        ('ERROR', 'System Error'),
        ('FRAUD', 'Suspected Fraud'),
        ('OTHER', 'Other'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
    ]

    original_payment = models.ForeignKey(
        'PaymentRecord',
        on_delete=models.CASCADE,
        related_name='reversals'
    )

    # Reversal details
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    reason_notes = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    # Reversal status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    # Audit
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='requested_reversals'
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_reversals'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_reversals'
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    # Reversal notes
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Payment Reversal"
        verbose_name_plural = "Payment Reversals"

    def __str__(self):
        return f"Reversal of {self.original_payment.receipt_number} - {self.amount}"

    @transaction.atomic
    def complete_reversal(self, user):
        """Complete the reversal"""
        if self.status != 'APPROVED':
            raise ValueError(f"Cannot complete reversal with status: {self.status}")

        payment = self.original_payment

        # Reverse the payment
        payment.is_reversed = True
        payment.status = 'REVERSED'
        payment.reversed_at = timezone.now()
        payment.reversed_by = user
        payment.reversal_reason = self.reason_notes or self.reason
        payment.save()

        # ==========================================
        # ✅ UPDATE LOAN AND RESTORE SCHEDULE
        # ==========================================
        if payment.loan:
            loan = payment.loan

            # ✅ Handle deposit reversal
            if payment.category == 'DEPOSIT':
                # Reset deposit fields
                loan.deposit_paid -= payment.amount
                if loan.deposit_paid < 0:
                    loan.deposit_paid = Decimal('0.00')

                if loan.deposit_complete:
                    loan.deposit_complete = False

                if loan.deposit_payment and loan.deposit_payment.id == payment.id:
                    loan.deposit_payment = None
                    loan.deposit_receipt_number = None
                    loan.deposit_paid_date = None
                    loan.deposit_payment_method = None

                loan.save()

                # ✅ Recalculate totals from remaining payments
                loan.recalculate_totals()

            # ✅ Handle installment reversal - RESTORE SCHEDULE
            elif payment.category == 'INSTALLMENT':
                from payments.views import reverse_payment_allocations
                reverse_payment_allocations(payment, user)

            # ✅ Fallback - just recalculate
            else:
                loan.recalculate_totals()

        # Update reversal status
        self.status = 'COMPLETED'
        self.completed_by = user
        self.completed_at = timezone.now()
        self.save()

        # ==========================================
        # ✅ LOG THE REVERSAL
        # ==========================================
        log_action(
            request=None,
            user=user,
            action='PAYMENT_REVERSED',
            description=(
                f"Payment {payment.receipt_number} reversed. "
                f"Amount: ${payment.amount}. "
                f"Category: {payment.category}. "
                f"Reason: {self.reason_notes or self.reason}. "
                f"Loan: {payment.loan.loan_id if payment.loan else 'N/A'}"
            ),
            loan=payment.loan,
            ip_address=None
        )

        # ==========================================
        # DEBUG: Show state AFTER reversal
        # ==========================================
        print("=" * 50)
        print("AFTER REVERSAL")
        print(f"Payment: {payment.receipt_number} - ${payment.amount} - {payment.status}")
        if payment.loan:
            print(f"Loan: {payment.loan.loan_id}")
            print(f"  Total Paid: ${payment.loan.total_paid}")
            print(f"  Outstanding: ${payment.loan.outstanding_balance}")
            print(f"  Status: {payment.loan.status}")
            print("\nActive Payments:")
            active = payment.loan.payments.filter(is_reversed=False, status='CONFIRMED')
            for p in active:
                print(f"  ${p.amount} - {p.category} - {p.receipt_number}")
        print("=" * 50)

        return True



    @transaction.atomic
    def un_reverse_payment(self, user):
        """
        Reverse a reversal - restore the payment like nothing happened.
        This is the "undo" for a reversal.
        """
        if self.status != 'COMPLETED':
            raise ValueError(f"Cannot un-reverse reversal with status: {self.status}")

        payment = self.original_payment

        if not payment.is_reversed:
            raise ValueError("Payment is not currently reversed")

        # 1. Restore the payment
        payment.is_reversed = False
        payment.status = 'CONFIRMED'
        payment.reversed_at = None
        payment.reversed_by = None
        payment.reversal_reason = None
        payment.save()

        # 2. Restore the schedule (re-apply payment)
        if payment.loan:
            #apply_payment_to_schedule(payment.loan, payment)
            #payment.loan.recalculate_totals()
################################################################################################################################
            logger.info(f"🔍 Loan found: {payment.loan.loan_id}")
            logger.info("🔍 Calling apply_payment_to_schedule...")
            apply_payment_to_schedule(payment.loan, payment)
            logger.info("🔍 apply_payment_to_schedule finished")
            payment.loan.recalculate_totals()
            logger.info("🔍 recalculate_totals finished")

        # 3. Update reversal status
        self.delete()

        # ==========================================
        # ✅ LOG THE UN-REVERSAL
        # ==========================================
        log_action(
            request=None,
            user=user,
            action='PAYMENT_UNREVERSED',
            description=(
                f"Payment {payment.receipt_number} un-reversed (restored). "
                f"Amount: ${payment.amount}. "
                f"Category: {payment.category}. "
                f"Loan: {payment.loan.loan_id if payment.loan else 'N/A'}"
            ),
            loan=payment.loan,
            ip_address=None
        )

        return True
