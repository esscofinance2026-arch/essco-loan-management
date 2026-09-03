from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.db import transaction


class LoanProduct(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('DELINQUENT', 'Delinquent'),
        ('DEFAULTED', 'Defaulted'),
        ('PAID_OFF', 'Paid Off'),
        ('WRITTEN_OFF', 'Written Off'),
        ('CLOSED', 'Closed'),
        ('CANCELLED', 'Cancelled'),
    ]

    # Identification
    loan_id = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='loans', null=True, blank=True)
    application = models.ForeignKey('applications.ApplicationModel', on_delete=models.SET_NULL, null=True, blank=True)

    # Deposit info
    deposit_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_paid_date = models.DateTimeField(null=True, blank=True)
    deposit_payment_method = models.CharField(max_length=50, blank=True, null=True)
    deposit_receipt_number = models.CharField(max_length=50, blank=True, null=True)
    deposit_payment = models.ForeignKey('payments.PaymentRecord', on_delete=models.SET_NULL, null=True, blank=True)
    deposit_complete = models.BooleanField(default=False, help_text="True when deposit_paid >= deposit_target")
    deposit_target = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Total deposit required to activate the loan (e.g., 10% of principal)")

    # Loan terms
    principal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    tenure_months = models.IntegerField()
    monthly_installment = models.DecimalField(max_digits=12, decimal_places=2)

    # Financials
    total_interest = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_payable = models.DecimalField(max_digits=12, decimal_places=2)
    outstanding_balance = models.DecimalField(max_digits=12, decimal_places=2)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_principal_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_interest_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    creation_method = models.CharField(max_length=20, default='AUTO')

    # Dates
    start_date = models.DateField(null=True, blank=True)
    first_payment_date = models.DateField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # QuickBooks
    quickbooks_customer_id = models.CharField(max_length=100, blank=True, null=True)
    quickbooks_invoice_id = models.CharField(max_length=100, blank=True, null=True)
    quickbooks_payment_id = models.CharField(max_length=100, blank=True, null=True)
    quickbooks_synced_at = models.DateTimeField(null=True, blank=True)

    # Audit
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_loans')
    internal_notes = models.TextField(blank=True, null=True)  # Rename from 'notes'

    notes = models.TextField(blank=True, null=True)



    def __str__(self):
         # safely handle None customer
        if self.customer:
            customer_name = self.customer.get_full_name() or self.customer.username
        elif self.application:
            customer_name = f"{self.application.Fname} {self.application.Lname}"
        elif hasattr(self, 'customer_name') and self.customer_name:
            customer_name = self.customer_name
        else:
            customer_name = "Unknown Customer"

        return f"{self.loan_id} - {customer_name}"

    # loans/models.py - Replace these methods in LoanProduct

    def mark_installments_as_paid_if_zero(self):
        """
        If the loan outstanding balance is <= 0, mark all pending installments as PAID.
        This should be called after every payment or reversal.
        """
        # ✅ FIX: Use outstanding_balance field
        if self.outstanding_balance <= 0:
            pending_installments = self.payment_schedule.filter(status='PENDING')
            if pending_installments.exists():
                pending_installments.update(status='PAID')
                return True
        return False

    def unmark_installments_if_negative(self):
        """
        If the loan outstanding balance is > 0 after a reversal,
        set the last N installments back to PENDING.
        """
        # ✅ FIX: Use outstanding_balance field
        if self.outstanding_balance > 0:
            # Find installments that were auto-marked as PAID after the last payment
            pending_count = self.payment_schedule.filter(status='PENDING').count()
            if pending_count > 0:
                # Already has pending installments - don't change
                return False

            # Get the most recent paid installments and revert them
            paid_installments = self.payment_schedule.filter(status='PAID').order_by('-due_date')
            if paid_installments.exists():
                # Revert the last one (or more) based on the reversal amount
                installment = paid_installments.first()
                installment.status = 'PENDING'
                installment.save()
                return True
        return False

    @property
    def outstanding_principal(self):
        """Calculate remaining principal after payments"""
        return self.principal_amount - self.total_principal_paid

    @property
    def deposit_remaining(self):
        """Calculate remaining deposit needed"""
        if self.deposit_target is None:
            return Decimal('0.00')
        remaining = self.deposit_target - self.deposit_paid
        return max(remaining, Decimal('0.00'))

    @property
    def deposit_percentage(self):
        """Calculate deposit percentage paid"""
        if self.deposit_target == 0:
            return 0
        return float((self.deposit_paid / self.deposit_target) * 100)

    @property
    def total_deposit_from_payments(self):
        """Calculate total deposit from all confirmed payments"""
        total = Decimal('0.00')
        payments = self.payments.filter(
            status='CONFIRMED',
            is_reversed=False
        )
        for payment in payments:
            if payment.deposit_portion:
                total += payment.deposit_portion
        return total

    @property
    def total_loan_amount_from_payments(self):
        """Calculate total loan amount using Financed_Amt + deposit from payments"""
        if self.application:
            financed = Decimal(str(self.application.Financed_Amt or 0))
        else:
            financed = Decimal(str(self.principal_amount or 0))

        deposit = self.total_deposit_from_payments
        return financed + deposit

    @property
    def total_deposit_breakdown(self):
        """Get detailed breakdown of deposits by payment"""
        breakdown = []
        payments = self.payments.filter(
            status='CONFIRMED',
            is_reversed=False,
            deposit_portion__gt=0
        ).order_by('payment_date')

        for payment in payments:
            breakdown.append({
                'date': payment.payment_date,
                'amount': float(payment.deposit_portion),
                'receipt': payment.receipt_number,
                'payment_id': payment.id
            })
        return breakdown

    @property
    def has_active_deposit(self):
        """Check if there's an active (non-reversed) deposit"""
        return self.deposit_complete and not self.deposit_payment.is_reversed if self.deposit_payment else False

    def get_complete_deposit_record(self):
        """Get full deposit record as a dictionary"""
        return {
            'amount': self.deposit_paid,
            'date': self.deposit_paid_date,
            'method': self.deposit_payment_method,
            'receipt': self.deposit_receipt_number,
            'target': self.deposit_target,
            'complete': self.deposit_complete,
            'remaining': self.deposit_remaining,
            'percentage': self.deposit_percentage,
        }
    @property
    def deposit_status(self):
        """Simple deposit status string"""
        if self.deposit_complete:
            return 'complete'
        elif self.deposit_paid > 0:
            return 'partial'
        else:
            return 'none'

    def apply_deposit_payment(self, amount, payment_record):
        """
        ✅ ONE PLACE to handle deposit payments
        Updates deposit tracking and returns excess amount
        """
        if self.deposit_complete:
            # Deposit already complete - all goes to installment
            return amount

        # Calculate what goes to deposit
        remaining = self.deposit_remaining
        deposit_amount = min(amount, remaining)
        excess = amount - deposit_amount

        # Update deposit
        self.deposit_paid += deposit_amount
        self.deposit_paid_date = payment_record.payment_date
        self.deposit_payment_method = payment_record.payment_method.name if payment_record.payment_method else None
        self.deposit_receipt_number = payment_record.receipt_number
        self.deposit_payment = payment_record

        # Check if complete
        if self.deposit_paid >= self.deposit_target:
            self.deposit_complete = True
            if self.status == 'DRAFT':
                self.status = 'ACTIVE'

        self.save()
        return excess

    def reset_deposit(self):
        """
        ✅ ONE PLACE to reset deposit (for reversals)
        """
        self.deposit_paid = Decimal('0.00')
        self.deposit_paid_date = None
        self.deposit_payment_method = None
        self.deposit_receipt_number = None
        self.deposit_payment = None
        self.deposit_complete = False
        self.save()

    def recalculate_totalsold(self):
        """✅ ONE PLACE to recalculate loan totals from payments"""
        from decimal import Decimal

        active_payments = self.payments.filter(is_reversed=False, status='CONFIRMED')

        self.total_paid = sum(p.amount for p in active_payments) or Decimal('0.00')

        # ✅ Recalculate deposit from confirmed deposits (capped at target)
        active_deposits = active_payments.filter(category='DEPOSIT')
        total_deposit_paid = sum(p.amount for p in active_deposits) or Decimal('0.00')

        if self.deposit_target > 0:
            deposit_excess = Decimal('0.00')
            if total_deposit_paid > self.deposit_target:
                deposit_excess = total_deposit_paid - self.deposit_target
                total_deposit_paid = self.deposit_target  # Cap at target
        else:
            deposit_excess = Decimal('0.00')

        self.deposit_paid = total_deposit_paid
        self.deposit_complete = self.deposit_paid >= self.deposit_target if self.deposit_target > 0 else False

        # ✅ Calculate outstanding principal = principal - first installment principal
        # First installment principal is what the excess paid
        first_installment_principal = Decimal('0.00')
        if deposit_excess > 0:
            first_schedule = self.payment_schedule.filter(
                status='PAID'
            ).order_by('due_date').first()

            if first_schedule:
                first_installment_principal = first_schedule.principal_paid

        # ✅ Outstanding = principal - first installment principal
        self.outstanding_balance = self.principal_amount - first_installment_principal
        if self.outstanding_balance < 0:
            self.outstanding_balance = Decimal('0.00')

        # Status logic
        if self.outstanding_balance <= 0:
            self.status = 'PAID_OFF'
        elif self.deposit_target > 0 and not self.deposit_complete:
            self.status = 'DRAFT'
        elif self.total_paid == 0:
            self.status = 'DRAFT'
        else:
            self.status = 'ACTIVE'

        self.save()
        return self.total_paid

    # loans/models.py

    def recalculate_totals(self):
        """✅ ONE PLACE to recalculate loan totals from payments"""
        from loans.services.loan_calculator import LoanCalculator
        return LoanCalculator.update_loan(self)
##############################################################################################################################################################

    def auto_repair(self, user=None, dry_run=False):
        """
        🔧 Auto-repair loan - scan all payments and recalculate everything.
        Completely rebuilds the schedule from payments.

        Args:
            user: The user performing the repair (for audit)
            dry_run: If True, only log what would change, don't save

        Returns:
            dict: Summary of changes made
        """
        from decimal import Decimal


        # ==========================================
        # 1. GET ALL PAYMENTS
        # ==========================================
        all_payments = self.payments.all().order_by('created_at')

        # Active payments (confirmed, not reversed)
        active_payments = all_payments.filter(
            status='CONFIRMED',
            is_reversed=False
        )

        # Reversed payments
        reversed_payments = all_payments.filter(
            is_reversed=True
        )

        # Deposits
        active_deposits = active_payments.filter(category='DEPOSIT')
        reversed_deposits = reversed_payments.filter(category='DEPOSIT')

        # ==========================================
        # 2. CALCULATE CORRECT TOTALS
        # ==========================================
        total_paid = sum(p.amount for p in active_payments) or Decimal('0.00')
        total_deposit_paid = sum(p.amount for p in active_deposits) or Decimal('0.00')

        # ✅ FIX: Cap deposit at target
        if self.deposit_target > 0:
            deposit_excess = Decimal('0.00')
            if total_deposit_paid > self.deposit_target:
                deposit_excess = total_deposit_paid - self.deposit_target
                total_deposit_paid = self.deposit_target  # Cap at target
        else:
            deposit_excess = Decimal('0.00')

        # ✅ Calculate deposit_complete correctly
        deposit_complete = total_deposit_paid >= self.deposit_target if self.deposit_target > 0 else total_deposit_paid > 0

        # ✅ Apply deposit excess to principal
        principal_reduction = deposit_excess

        # ✅ Calculate new outstanding
        outstanding_balance = self.principal_amount - principal_reduction
        if outstanding_balance < 0:
            outstanding_balance = Decimal('0.00')

        # ==========================================
        # 3. DETERMINE CORRECT STATUS
        # ==========================================
        if outstanding_balance <= 0:
            new_status = 'PAID_OFF'
        elif not deposit_complete and self.deposit_target > 0:
            new_status = 'DRAFT'
        elif total_paid == 0:
            new_status = 'DRAFT'
        else:
            new_status = 'ACTIVE'

        # ==========================================
        # 4. FIND LATEST DEPOSIT PAYMENT
        # ==========================================
        latest_deposit = active_deposits.order_by('-created_at').first()

        # ==========================================
        # 5. BUILD SUMMARY
        # ==========================================
        summary = {
            'loan_id': self.loan_id,
            'old_status': self.status,
            'new_status': new_status,
            'old_total_paid': self.total_paid,
            'new_total_paid': total_paid,
            'old_outstanding': self.outstanding_balance,
            'new_outstanding': outstanding_balance,
            'old_deposit_paid': self.deposit_paid,
            'new_deposit_paid': total_deposit_paid,
            'deposit_complete': deposit_complete,
            'deposit_excess': deposit_excess,
            'old_deposit_complete': self.deposit_complete,
            'active_payments_count': active_payments.count(),
            'reversed_payments_count': reversed_payments.count(),
            'total_payments_count': all_payments.count(),
            'total_reversed_amount': sum(p.amount for p in reversed_payments) or Decimal('0.00'),
            'dry_run': dry_run,
        }

        # ==========================================
        # 6. COMPLETELY REBUILD THE SCHEDULE
        # ==========================================
        if not dry_run:
            with transaction.atomic():
                # Get all schedules
                schedules = self.payment_schedule.all().order_by('due_date')

                # Reset ALL schedules to PENDING with 0 paid
                for schedule in schedules:
                    schedule.principal_paid = Decimal('0.00')
                    schedule.interest_paid = Decimal('0.00')
                    schedule.total_paid = Decimal('0.00')
                    schedule.status = 'PENDING'
                    schedule.payment_reference = None
                    schedule.save()

                # Get installment payments (not deposits)
                installment_payments = active_payments.filter(
                    category='INSTALLMENT'
                ).order_by('created_at')

                # Re-apply each installment payment to the schedule
                for payment in installment_payments:
                    remaining = payment.amount

                    for schedule in schedules:
                        if remaining <= 0:
                            break

                        # Calculate remaining due on this schedule
                        remaining_due = schedule.total_due - schedule.total_paid
                        if remaining_due <= 0:
                            continue

                        # Determine how much to apply
                        amount_to_apply = min(remaining, remaining_due)

                        # Allocate between principal and interest (interest first)
                        interest_remaining = schedule.interest_due - schedule.interest_paid
                        if amount_to_apply <= interest_remaining:
                            interest_applied = amount_to_apply
                            principal_applied = Decimal('0.00')
                        else:
                            interest_applied = interest_remaining
                            principal_applied = amount_to_apply - interest_remaining

                        # Update schedule
                        schedule.interest_paid += interest_applied
                        schedule.principal_paid += principal_applied
                        schedule.total_paid += amount_to_apply
                        schedule.payment_reference = payment

                        # Update payment allocation
                        payment.interest_applied += interest_applied
                        payment.principal_applied += principal_applied

                        # Update status
                        if schedule.total_paid >= schedule.total_due:
                            schedule.status = 'PAID'
                        elif schedule.total_paid > 0:
                            schedule.status = 'PARTIAL'
                        else:
                            schedule.status = 'PENDING'

                        schedule.save()
                        remaining -= amount_to_apply

                    # Save payment with updated allocations
                    payment.save()

                # ==========================================
                # 7. UPDATE LOAN
                # ==========================================
                self.status = new_status
                self.total_paid = total_paid

                # ✅ FIX: Cap deposit at target
                if self.deposit_target > 0:
                    self.deposit_paid = min(total_deposit_paid, self.deposit_target)
                else:
                    self.deposit_paid = total_deposit_paid

                self.deposit_complete = deposit_complete

                # ✅ SET OUTSTANDING TO PRINCIPAL FIRST
                self.outstanding_balance = self.principal_amount

                # ✅ APPLY DEPOSIT EXCESS TO FIRST INSTALLMENT
                if deposit_excess > 0:
                    first_schedule = self.payment_schedule.filter(
                        status='PENDING'
                    ).order_by('due_date').first()

                    if first_schedule:
                        # Calculate remaining amounts
                        principal_remaining = first_schedule.principal_due - first_schedule.principal_paid
                        interest_remaining = first_schedule.interest_due - first_schedule.interest_paid

                        # Apply excess to first installment
                        principal_part = min(deposit_excess, principal_remaining)
                        interest_part = min(deposit_excess - principal_part, interest_remaining)

                        first_schedule.principal_paid += principal_part
                        first_schedule.interest_paid += interest_part
                        first_schedule.total_paid += principal_part + interest_part

                        # Check status
                        if first_schedule.total_paid >= first_schedule.total_due:
                            first_schedule.status = 'PAID'
                        else:
                            first_schedule.status = 'PARTIAL'

                        first_schedule.save()

                        # ✅ REDUCE OUTSTANDING BY PRINCIPAL PORTION
                        self.outstanding_balance -= principal_part

                        # Calculate remaining excess after first installment
                        remaining_excess = deposit_excess - (principal_part + interest_part)

                        # ✅ Apply remaining excess to principal
                        if remaining_excess > 0:
                            self.outstanding_balance -= remaining_excess
                            if self.outstanding_balance < 0:
                                self.outstanding_balance = Decimal('0.00')
                    else:
                        # No installment - apply all to principal
                        self.outstanding_balance -= deposit_excess
                        if self.outstanding_balance < 0:
                            self.outstanding_balance = Decimal('0.00')

                # Update deposit fields
                if latest_deposit:
                    self.deposit_payment = latest_deposit
                    self.deposit_paid_date = latest_deposit.payment_date
                    self.deposit_payment_method = latest_deposit.payment_method.name if latest_deposit.payment_method else None
                    self.deposit_receipt_number = latest_deposit.receipt_number
                else:
                    self.deposit_payment = None
                    self.deposit_paid_date = None
                    self.deposit_payment_method = None
                    self.deposit_receipt_number = None

                self.save()

                # Log the repair
                if user:
                    from audit.services import log_action
                    log_action(
                        request=None,
                        user=user,
                        action='LOAN_REPAIRED',
                        description=(
                            f"Auto-repair: {summary['old_status']} → {summary['new_status']}, "
                            f"Total Paid: ${summary['old_total_paid']} → ${summary['new_total_paid']}, "
                            f"Deposit: ${summary['old_deposit_paid']} → ${summary['new_deposit_paid']}, "
                            f"Deposit Excess: ${summary['deposit_excess']}"
                        ),
                        loan=self,
                        ip_address=None
                    )

        return summary
#########################################################################################################################################################

class PaymentSchedule(models.Model):
    loan = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='payment_schedule')
    installment_number = models.IntegerField()
    due_date = models.DateField()

    principal_due = models.DecimalField(max_digits=12, decimal_places=2)
    interest_due = models.DecimalField(max_digits=12, decimal_places=2)
    total_due = models.DecimalField(max_digits=12, decimal_places=2)

    principal_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    interest_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    grace_period_end = models.DateField(null=True, blank=True)
    late_fee_assessed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    late_fee_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.ForeignKey(
        'payments.PaymentRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='installment_paid'
    )

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partial'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['installment_number']

class LoanStatusHistory(models.Model):
    """Track all status changes for a loan"""
    loan = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='status_history')

    previous_status = models.CharField(max_length=20, choices=LoanProduct.STATUS_CHOICES)
    new_status = models.CharField(max_length=20, choices=LoanProduct.STATUS_CHOICES)
    reason = models.TextField(blank=True, null=True)

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='loan_status_changes'
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-changed_at']
        verbose_name = "Loan Status History"
        verbose_name_plural = "Loan Status Histories"

    def __str__(self):
        return f"{self.loan.loan_id}: {self.previous_status} → {self.new_status}"

class LoanFee(models.Model):
    """Fees associated with a loan"""
    loan = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='fees')

    FEE_TYPES = [
        ('LATE', 'Late Payment Fee'),
        ('PROCESSING', 'Processing Fee'),
        ('MAINTENANCE', 'Maintenance Fee'),
        ('ADMIN', 'Administrative Fee'),
        ('OTHER', 'Other'),
    ]

    fee_type = models.CharField(max_length=20, choices=FEE_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)

    assessed_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField()

    is_paid = models.BooleanField(default=False)
    paid_date = models.DateTimeField(null=True, blank=True)
    payment_reference = models.ForeignKey(
        'payments.PaymentRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fee_paid'
    )

    is_waived = models.BooleanField(default=False)
    waived_date = models.DateTimeField(null=True, blank=True)
    waived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='waived_fees'
    )
    waiver_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date']
        verbose_name = "Loan Fee"
        verbose_name_plural = "Loan Fees"

    def __str__(self):
        return f"{self.loan.loan_id} - {self.fee_type}: ${self.amount}"

class CollectionActivity(models.Model):
    """Track collection efforts on delinquent loans"""
    loan = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='collection_activities')

    ACTIVITY_TYPES = [
        ('PHONE_CALL', 'Phone Call'),
        ('EMAIL', 'Email'),
        ('SMS', 'SMS'),
        ('LETTER', 'Letter'),
        ('VISIT', 'Visit'),
        ('OTHER', 'Other'),
    ]

    CONTACT_STATUS = [
        ('CONTACTED', 'Contacted'),
        ('NO_ANSWER', 'No Answer'),
        ('WRONG_NUMBER', 'Wrong Number'),
        ('PROMISE_TO_PAY', 'Promise to Pay'),
        ('DISPUTE', 'Dispute'),
        ('ESCALATED', 'Escalated'),
    ]

    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    contact_status = models.CharField(max_length=20, choices=CONTACT_STATUS)
    summary = models.TextField()
    notes = models.TextField(blank=True, null=True)

    promise_date = models.DateField(null=True, blank=True)
    promise_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    promise_fulfilled = models.BooleanField(default=False)

    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_required = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='collection_activities'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Collection Activity"
        verbose_name_plural = "Collection Activities"

    def __str__(self):
        return f"{self.loan.loan_id} - {self.activity_type} ({self.created_at.date()})"

class LoanNote(models.Model):
    """Internal notes/comments on a loan"""
    loan = models.ForeignKey(LoanProduct, on_delete=models.CASCADE, related_name='loan_notes')

    NOTE_TYPES = [
        ('GENERAL', 'General Note'),
        ('COLLECTION', 'Collection Note'),
        ('CUSTOMER_REQUEST', 'Customer Request'),
        ('INTERNAL', 'Internal Note'),
        ('DISPUTE', 'Dispute'),
        ('RESOLUTION', 'Resolution'),
    ]

    content = models.TextField()
    note_type = models.CharField(max_length=50, choices=NOTE_TYPES, default='GENERAL')
    is_internal = models.BooleanField(default=True, help_text="If True, customer cannot see this note")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='loan_notes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_notes'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Loan Note"
        verbose_name_plural = "Loan Notes"

    def __str__(self):
        return f"{self.loan.loan_id} - {self.note_type} ({self.created_at.date()})"