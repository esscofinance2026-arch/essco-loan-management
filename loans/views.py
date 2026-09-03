# loans/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from decimal import Decimal
from datetime import timedelta, datetime
import logging
from audit.services import log_action
from django.db import IntegrityError
from .models import LoanProduct, PaymentSchedule, LoanFee, LoanStatusHistory, CollectionActivity
from applications.models import ApplicationModel
#from payments.models import PaymentRecord, PaymentMethod
from audit.services import AuditService
from django.db import transaction
from django.http import JsonResponse
from loans.utils import apply_payment_to_schedule
from loans.utils import get_payment_record_model, get_payment_method_model


logger = logging.getLogger(__name__)

# ============================================================
# LOAN MANAGEMENT - CORE
# ============================================================
@transaction.atomic
@login_required
def create_loan_from_application(request, application_id):
    """
    Create a loan from an approved application.
    This is the CORE loan creation logic - NO QuickBooks sync here.
    """
    application = get_object_or_404(ApplicationModel, id=application_id)

    # Security: Check if user has permission
    if request.user != application.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to create a loan from this application.")
        #return redirect('customer_dashboard', application_id=application.id)
        return redirect('customer_dashboard')
    # Security: Check if application is approved
    if application.Approval_Status not in ['Approved Pending', 'Human Approved']:
        messages.error(request, "Only approved applications can be converted to loans.")
        #return redirect('applications:application_detail', application_id=application.id)
        return redirect('customer_dashboard')

    # Security: Check if loan already exists
    existing_loan = LoanProduct.objects.filter(application=application).first()
    if existing_loan:
        messages.warning(request, f"A loan already exists for this application: {existing_loan.loan_id}")
        return redirect('loans:loan_detail', loan_id=existing_loan.id)

    # Security: Check if deposit is paid
    if not application.has_valid_deposit():
        messages.error(request, "Deposit must be paid before creating a loan.")
        return redirect('applications:application_detail', application_id=application.id)

    # GET request - show confirmation form
    if request.method == 'GET':
        # Calculate loan terms for preview
        principal = application.Financed_Amt or application.Purchase_Value or 0
        interest_rate = application.get_rate_for_status().rate if application.get_rate_for_status() else 12.0
        tenure_months = 24  # Default or get from application.Term

        monthly_installment = calculate_installment(principal, interest_rate, tenure_months)
        total_payable = monthly_installment * tenure_months

        context = {
            'application': application,
            'principal': principal,
            'interest_rate': interest_rate,
            'tenure_months': tenure_months,
            'monthly_installment': monthly_installment,
            'total_payable': total_payable,
            'deposit_amount': application.deposit_paid,
        }
        return render(request, 'loans/create_loan_confirmation.html', context)

    # POST request - create the loan
    if request.method == 'POST':
        try:
            # Get or calculate loan terms
            principal = Decimal(request.POST.get('principal', application.Financed_Amt or application.Purchase_Value or 0))
            interest_rate = Decimal(request.POST.get('interest_rate', application.get_rate_for_status().rate if application.get_rate_for_status() else 12.0))
            tenure_months = int(request.POST.get('tenure_months', 24))

            # Create loan
            loan = LoanProduct(
                customer=application.customer,
                application=application,
                principal_amount=principal,
                interest_rate=interest_rate,
                tenure_months=tenure_months,
                deposit_paid=application.deposit_paid,
                deposit_paid_date=application.deposit_paid_date,
                deposit_payment_method=application.deposit_payment_method,
                deposit_receipt_number=application.deposit_receipt_number,
                deposit_payment=application.deposit_payment,
                deposit_transferred_from_application=application,
                status='DRAFT',
                creation_method='MANUAL' if request.user.is_staff else 'AUTO',
                created_by=request.user,
                notes=f"Created from application #{application.application_id or application.id}"
            )

            # Generate loan ID
            loan.loan_id = generate_loan_id()

            # Calculate installment
            loan.monthly_installment = calculate_installment(principal, interest_rate, tenure_months)
            loan.total_interest = (loan.monthly_installment * tenure_months) - principal
            loan.total_payable = loan.monthly_installment * tenure_months
            loan.outstanding_balance = loan.total_payable

            # Set dates
            today = timezone.now().date()
            loan.start_date = today
            loan.first_payment_date = today + timedelta(days=30)
            loan.maturity_date = today + timedelta(days=30 * tenure_months)

            loan.save()

            # Generate payment schedule
            generate_payment_schedule(loan)

            # Transfer deposit from application
            application.deposit_status = 'TRANSFERRED'
            application.save()

            # Log audit
            log_action(
                request=request,
                user=request.user,
                action='LOAN_CREATED',
                description=f"Loan {loan.loan_id} created",
                application=application,
                loan=loan,  # ✅ ADD THIS
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, f"✅ Loan {loan.loan_id} created successfully!")
            return redirect('loans:loan_detail', loan_id=loan.id)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Loan creation failed: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to create loan: {str(e)}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Failed to create loan from application {application.reference_number}: {error_msg}",
                application = application,
                loan=None,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return redirect('applications:application_detail', application_id=application.id)

########################################################################################################################################################

# loans/views.py

@login_required
def loan_detail(request, loan_id):
    """View loan details for customers"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    # Security: Check access
    if request.user != loan.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to view this loan.")
        return redirect('dashboard')

    # Get payment schedule
    schedule = loan.payment_schedule.all().order_by('due_date')

    # Get payments
    payments = loan.payments.all().order_by('-created_at')

    # Get fees
    fees = loan.fees.all().order_by('-assessed_date')

    # Calculate remaining interest
    remaining_interest = loan.total_interest - loan.total_interest_paid

    # ==========================================
    # ✅ DEPOSIT INFORMATION
    # ==========================================
    deposit_target = loan.deposit_target or 0
    deposit_paid = loan.deposit_paid or 0
    deposit_complete = loan.deposit_complete
    deposit_remaining = max(deposit_target - deposit_paid, 0)

    if deposit_target > 0:
        deposit_percentage = (deposit_paid / deposit_target) * 100
    else:
        deposit_percentage = 0

    # Check if deposit was reversed
    deposit_reversed = False
    if loan.deposit_payment and loan.deposit_payment.is_reversed:
        deposit_reversed = True

    # Check if loan is overdue
    days_overdue = loan.get_days_overdue() if hasattr(loan, 'get_days_overdue') else 0

    # ==========================================
    # ✅ CUSTOMER ACTIONS
    # ==========================================
    can_pay_deposit = not deposit_complete and not deposit_reversed and loan.status in ['DRAFT', 'ACTIVE']
    can_pay_installment = deposit_complete and loan.status == 'ACTIVE'
    can_make_payment = can_pay_deposit or can_pay_installment

    # ✅ Recalculate totals before displaying
    loan.recalculate_totals()

    context = {
        'loan': loan,
        'schedule': schedule,
        'payments': payments,
        'fees': fees,
        'days_overdue': days_overdue,
        'is_synced': loan.quickbooks_customer_id is not None,
        'customer_name': loan.customer.get_full_name() or loan.customer.username,
        'next_payment': schedule.filter(status='PENDING').first(),
        'remaining_interest': remaining_interest,

        # ✅ Deposit context
        'deposit_target': deposit_target,
        'deposit_paid': deposit_paid,
        'deposit_complete': deposit_complete,
        'deposit_remaining': deposit_remaining,
        'deposit_percentage': deposit_percentage,
        'deposit_reversed': deposit_reversed,
        'can_pay_deposit': can_pay_deposit,
        'can_pay_installment': can_pay_installment,
        'can_make_payment': can_make_payment,
    }
    return render(request, 'loans/loan_detail.html', context)


@login_required
def loan_detail1(request, loan_id):
    """View loan details"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    # Security: Check access
    if request.user != loan.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to view this loan.")
        return redirect('dashboard')

    # Get payment schedule
    schedule = loan.payment_schedule.all().order_by('due_date')

    # Get payments
    payments = loan.payments.all().order_by('-created_at')

    # Get fees
    fees = loan.fees.all().order_by('-assessed_date')

    # Check if loan is overdue
    days_overdue = loan.get_days_overdue() if hasattr(loan, 'get_days_overdue') else 0

    context = {
        'loan': loan,
        'schedule': schedule,
        'payments': payments,
        'fees': fees,
        'days_overdue': days_overdue,
        'is_synced': loan.quickbooks_customer_id is not None,
        'customer_name': loan.customer.get_full_name() or loan.customer.username,
        'next_payment': schedule.filter(status='PENDING').first(),
    }
    return render(request, 'loans/loan_detail.html', context)


@login_required
def activate_loan(request, loan_id):
    """Activate a loan (move from DRAFT to ACTIVE)"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    if not request.user.is_staff:
        messages.error(request, "Only staff can activate loans.")
        return redirect('loans:loan_detail', loan_id=loan.id)

    if loan.status != 'DRAFT':
        messages.warning(request, f"Loan is already in {loan.status} status.")
        return redirect('loans:loan_detail', loan_id=loan.id)

    if request.method == 'POST':
        try:
            loan.activate_loan(user=request.user)
            messages.success(request, f"✅ Loan {loan.loan_id} activated successfully!")
            log_action(
                request=request,
                user=request.user,
                action='LOAN_ACTIVATED',
                description=f"Loan {loan.loan_id} activated",
                loan=loan,  # ✅ ADD THIS
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('loans:loan_detail', loan_id=loan.id)
        except Exception as e:
            error_msg = str(e)
            messages.error(request, f"Failed to activate loan: {str(e)}")

            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Failed to activate loan {loan.loan_id}: {error_msg}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )
    context = {
        'loan': loan,
    }
    return render(request, 'loans/activate_loan.html', context)


@login_required
def close_loan(request, loan_id):
    """Close a loan (Paid Off or Closed)"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    if not request.user.is_staff:
        messages.error(request, "Only staff can close loans.")
        return redirect('loans:loan_detail', loan_id=loan.id)

    if loan.status in ['CLOSED', 'PAID_OFF']:
        messages.warning(request, f"Loan is already {loan.status}.")
        return redirect('loans:loan_detail', loan_id=loan.id)

    if loan.outstanding_balance > 0:
        messages.error(request, f"Cannot close loan with outstanding balance of ${loan.outstanding_balance}.")
        return redirect('loans:loan_detail', loan_id=loan.id)

    if request.method == 'POST':
        try:
            loan.status = 'PAID_OFF' if loan.outstanding_balance <= 0 else 'CLOSED'
            loan.closed_date = timezone.now()
            loan.save()

            # Log status change
            LoanStatusHistory.objects.create(
                loan=loan,
                previous_status=loan.status,
                new_status=loan.status,
                reason=request.POST.get('reason', 'Loan closed'),
                changed_by=request.user
            )

            messages.success(request, f"✅ Loan {loan.loan_id} closed successfully!")
            log_action(
                request=request,
                user=request.user,
                action='LOAN_CLOSED',
                description=f"Loan {loan.loan_id} closed",
                loan=loan,  # ✅ ADD THIS
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('loans:loan_detail', loan_id=loan.id)
        except Exception as e:
            error_msg = str(e)
            messages.error(request, f"Failed to close loan: {str(e)}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Failed to close loan {loan.loan_id}: {error_msg}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

    context = {
        'loan': loan,
    }
    return render(request, 'loans/close_loan.html', context)


# ============================================================
# PAYMENT PROCESSING
# ============================================================
# loans/views.py

def process_payment(request, loan_id):
    """
    Customer view to process a payment (deposit or installment).
    ✅ Supports partial payments (any amount up to max).
    ✅ Automatically determines if payment goes to deposit or installment.
    """
    loan = get_object_or_404(LoanProduct, id=loan_id)

    PaymentRecord = get_payment_record_model()
    PaymentMethod = get_payment_method_model()

    # ✅ Call the auto-mark method
    if loan.mark_installments_as_paid_if_zero():
        logger.info(f"✅ Auto-marked remaining installments as PAID for loan {loan.loan_id}")

    # Security: Check access
    if request.user != loan.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to make payments on this loan.")
        return redirect('loans:loan_detail', loan_id=loan.id)

    # ==========================================
    # ✅ CHECK DEPOSIT STATUS
    # ==========================================
    deposit_complete = loan.deposit_complete
    deposit_target = loan.deposit_target or 0
    deposit_paid = loan.deposit_paid or 0
    deposit_remaining = max(deposit_target - deposit_paid, 0)

    # Determine if this payment should be a deposit
    is_deposit = not deposit_complete and deposit_target > 0 and deposit_remaining > 0

    # Determine max payment amount
    if is_deposit:
        max_payment = deposit_remaining
    else:
        max_payment = loan.outstanding_balance

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))
        payment_method_id = request.POST.get('payment_method')
        notes = request.POST.get('notes', '')

        # ✅ Validation
        if amount <= 0:
            messages.error(request, "Payment amount must be greater than 0.")
            return redirect('loans:process_payment', loan_id=loan.id)

        if amount > max_payment:
            messages.error(
                request,
                f"Payment amount exceeds maximum of ${max_payment:,.2f}."
            )
            return redirect('loans:process_payment', loan_id=loan.id)

        try:
            payment_method = get_object_or_404(PaymentMethod, id=payment_method_id)

            # ==========================================
            # ✅ DETERMINE CATEGORY
            # ==========================================
            category = 'DEPOSIT' if is_deposit else 'INSTALLMENT'

            with transaction.atomic():
                # ✅ FINAL SAFETY CHECK (stale tab / double submission)
                if is_deposit and loan.deposit_complete:
                    messages.error(
                        request,
                        "Deposit is already complete. Please refresh and try again."
                    )
                    return redirect('loans:loan_detail', loan_id=loan.id)

                # ==========================================
                # ✅ CREATE PAYMENT
                # ==========================================
                payment = PaymentRecord.objects.create(
                    customer=request.user,
                    loan=loan,
                    recorded_by=request.user,
                    category=category,
                    amount=amount,
                    payment_method=payment_method,
                    receipt_number=f"PY-{timezone.now().strftime('%H%M%S')}-{PaymentRecord.objects.count() + 1:03d}",
                    status='PENDING',
                    confirmed_by=request.user,
                    confirmed_at=timezone.now(),
                    notes=f"Customer payment. {notes}"
                )

                # Call confirm() to trigger customer creation
                payment.confirm(request.user)

                logger.info(f"✅ Payment created: {payment.receipt_number} - Category: {category} - Amount: ${amount}")

                # ==========================================
                # ✅ APPLY PAYMENT (DEPOSIT)
                # ==========================================
                if category == 'DEPOSIT':
                    from payments.utils import record_deposit_payment_for_loan

                    # Call the centralized helper
                    payment, deposit_complete = record_deposit_payment_for_loan(
                        loan=loan,
                        amount=amount,
                        payment_method=payment_method,
                        receipt_number=payment.receipt_number,
                        recorded_by=request.user,
                        payment_date=payment.payment_date,
                        notes=notes
                    )

                    # ✅ APPLY EXCESS TO INSTALLMENT
                    # Calculate how much was overpaid on deposit
                    excess = amount - loan.deposit_remaining
                    if excess > 0:
                        from loans.utils import apply_excess_to_installment
                        apply_excess_to_installment(loan, payment, excess)
                        messages.info(request, f"${excess:,.2f} excess applied to first installment.")

                    # ✅ Show appropriate message
                    if deposit_complete:
                        messages.success(
                            request,
                            f"🎉 Deposit complete! Your loan is now ACTIVE. "
                            f"Total deposit: ${loan.deposit_paid:,.2f}"
                        )
                    else:
                        remaining = loan.deposit_target - loan.deposit_paid
                        messages.info(
                            request,
                            f"✅ Partial deposit of ${amount:,.2f} received. "
                            f"Remaining deposit: ${remaining:,.2f} "
                            f"({loan.deposit_percentage:.0f}% complete)"
                        )

                else:
                    # ✅ Apply to schedule (installment)
                    apply_payment_to_schedule(loan, payment)

                    # Update loan totals
                    loan.total_paid += amount
                    loan.outstanding_balance -= amount

                    # Check if loan is now paid off
                    if loan.outstanding_balance <= 0:
                        loan.status = 'PAID_OFF'
                        messages.success(
                            request,
                            f"🎉 Loan fully paid off! Congratulations!"
                        )
                    else:
                        messages.success(
                            request,
                            f"✅ Payment of ${amount:,.2f} applied to your loan. "
                            f"Remaining balance: ${loan.outstanding_balance:,.2f}"
                        )

                loan.save()

                # ==========================================
                # ✅ AUDIT LOG
                # ==========================================
                log_action(
                    request=request,
                    user=request.user,
                    action='PAYMENT_MADE',
                    description=f"Customer {request.user.username} made {category} payment of ${amount} on loan {loan.loan_id}",
                    loan=loan,
                    ip_address=request.META.get('REMOTE_ADDR')
                )

            return redirect('loans:loan_detail', loan_id=loan.id)

        except Exception as e:
            logger.error(f"❌ Payment processing failed: {str(e)}", exc_info=True)
            messages.error(request, f"Payment failed: {str(e)}")
            return redirect('loans:process_payment', loan_id=loan.id)

    # ==========================================
    # ✅ GET REQUEST - SHOW FORM
    # ==========================================
    deposit_percentage = 0
    if deposit_target > 0:
        deposit_percentage = (deposit_paid / deposit_target) * 100

    # ✅ Suggested payment amounts
    if is_deposit:
        suggested_amounts = [
            min(deposit_remaining * Decimal('0.25'), Decimal('500')),
            min(deposit_remaining * Decimal('0.50'), Decimal('500')),
            min(deposit_remaining * Decimal('0.75'), Decimal('500')),
            deposit_remaining,
        ]
        suggested_amounts = sorted(set([round(a, 2) for a in suggested_amounts if a > 0]))
    else:
        monthly = loan.monthly_installment
        suggested_amounts = [
            min(monthly, loan.outstanding_balance),
            min(monthly * Decimal('2'), loan.outstanding_balance),
            min(monthly * Decimal('3'), loan.outstanding_balance),
            loan.outstanding_balance,
        ]
        suggested_amounts = sorted(set([round(a, 2) for a in suggested_amounts if a > 0]))

    context = {
        'loan': loan,
        'payment_methods': PaymentMethod.objects.filter(is_active=True),
        'max_payment': max_payment,
        'is_deposit': is_deposit,
        'deposit_complete': deposit_complete,
        'deposit_target': deposit_target,
        'deposit_paid': deposit_paid,
        'deposit_remaining': deposit_remaining,
        'deposit_percentage': deposit_percentage,
        'suggested_payment': min(monthly, max_payment) if not is_deposit else min(deposit_remaining, 500),
        'suggested_amounts': suggested_amounts,
        'customer_name': loan.customer.get_full_name() or loan.customer.username,
    }
    return render(request, 'loans/process_payment.html', context)



@login_required
def process_payment1(request, loan_id):
    """Process a payment for a loan"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    PaymentRecord = get_payment_record_model()
    PaymentMethod = get_payment_method_model()

    if request.user != loan.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to make payments on this loan.")
        return redirect('loans:loan_detail', loan_id=loan.id)

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))
        payment_method_id = request.POST.get('payment_method')

        if amount <= 0:
            messages.error(request, "Payment amount must be greater than 0.")
            return redirect('loans:process_payment', loan_id=loan.id)

        if amount > loan.outstanding_balance:
            messages.error(request, f"Payment amount exceeds outstanding balance of ${loan.outstanding_balance}.")
            return redirect('loans:process_payment', loan_id=loan.id)

        try:
            # Get payment method
            payment_method = get_object_or_404(PaymentMethod, id=payment_method_id)

            # Create payment record
            payment = PaymentRecord.objects.create(
                customer=request.user,
                loan=loan,
                recorded_by=request.user,
                category='INSTALLMENT',
                amount=amount,
                payment_method=payment_method,
                receipt_number=f"PAY-{timezone.now().strftime('%Y%m%d')}-{PaymentRecord.objects.count() + 1:06d}",
                status='CONFIRMED' if not payment_method.requires_manual_confirmation else 'PENDING',
                confirmed_by=request.user if not payment_method.requires_manual_confirmation else None,
                confirmed_at=timezone.now() if not payment_method.requires_manual_confirmation else None,
                notes=request.POST.get('notes', '')
            )
            logger.info(f"✅ Payment created: {payment.receipt_number}")

            # Apply payment to schedule
            try:
                apply_payment_to_schedule(loan, payment)
                logger.info(f"✅ Payment applied to schedule")
            except Exception as e:
                logger.error(f"❌ Failed to apply payment to schedule: {e}")
                # Payment was created but not applied - mark as failed
                payment.status = 'FAILED'
                payment.notes = f"{payment.notes}\nFailed to apply to schedule: {str(e)}"
                payment.save()
                raise  # Re-raise to be caught by outer try

            # Check if loan is now paid off
            if loan.outstanding_balance <= 0:
                loan.status = 'PAID_OFF'
                loan.closed_date = timezone.now()
                loan.save()
                logger.info("✅ Loan marked as PAID_OFF")

            # Audit log
            log_action(
                request=request,
                loan=loan,
                user=request.user,
                action='PAYMENT_MADE',
                description=f"Payment of ${amount} made on loan {loan.loan_id}",
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, f"✅ Payment of ${amount} processed successfully!")
            return redirect('loans:loan_detail', loan_id=loan.id)

        except IntegrityError as e:
            logger.error(f"❌ Payment integrity error: {e}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Payment of ${amount} failed on loan {loan.loan_id}: IntegrityError",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.error(request, "Payment failed due to a database error. Please try again.")
            return redirect('loans:process_payment', loan_id=loan.id)

        except ValueError as e:
            logger.error(f"❌ Payment validation error: {e}")
            messages.error(request, f"Invalid payment data: {str(e)}")
            return redirect('loans:process_payment', loan_id=loan.id)

        except PaymentMethod.DoesNotExist:
            logger.error(f"❌ Payment method not found: {payment_method_id}")
            messages.error(request, "Selected payment method is invalid. Please try again.")
            return redirect('loans:process_payment', loan_id=loan.id)

        except TimeoutError as e:
            logger.error(f"❌ Payment timeout error: {e}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Payment of ${amount} timed out on loan {loan.loan_id}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.error(request, "Payment processing timed out. Please try again.")
            return redirect('loans:process_payment', loan_id=loan.id)

        except Exception as e:
            logger.error(f"❌ Payment processing failed: {str(e)}", exc_info=True)
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Payment of ${amount} failed on loan {loan.loan_id}: {str(e)}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.error(request, f"Payment failed: {str(e)}")
            return redirect('loans:process_payment', loan_id=loan.id)

    # GET request - show payment form
    logger.info("🔍 GET request - showing form")
    context = {
        'loan': loan,
        'payment_methods': PaymentMethod.objects.filter(is_active=True),
        'max_payment': loan.outstanding_balance,
        'min_payment': loan.monthly_installment,
        'suggested_payment': min(loan.monthly_installment, loan.outstanding_balance),
    }
    return render(request, 'loans/process_payment.html', context)

################################################# Suspected bloat code ############################################################################
@transaction.atomic
@login_required
def reverse_payment(request, payment_id):
    """Reverse a payment"""

    PaymentRecord = get_payment_record_model()
    #PaymentMethod = get_payment_method_model()

    payment = get_object_or_404(PaymentRecord, id=payment_id)

    if not request.user.is_staff:
        messages.error(request, "Only staff can reverse payments.")
        return redirect('loans:loan_detail', loan_id=payment.loan.id)

    if payment.is_reversed:
        messages.warning(request, "This payment has already been reversed.")
        return redirect('loans:loan_detail', loan_id=payment.loan.id)

    if request.method == 'POST':
        try:
            # Reverse the payment
            payment.is_reversed = True
            payment.save()

            # Reverse the payment in the schedule
            loan = payment.loan

            # Find the installment this payment was applied to
            if payment.principal_applied > 0 or payment.interest_applied > 0:
                # Find the schedule entry that was paid
                schedule_entries = loan.payment_schedule.filter(
                    status__in=['PAID', 'PARTIAL']
                ).order_by('-paid_at')

            # ADJUST SCHEDULE
            apply_payment_to_schedule(loan, payment)

            # Update loan outstanding balance
            loan.outstanding_balance += payment.amount
            loan.total_paid -= payment.amount
            loan.save()

            # Log audit
            AuditService.log_hp_operation(
                user=request.user,
                action='PAYMENT_REVERSED',
                description=f"Payment {payment.receipt_number} reversed for ${payment.amount}",
                account_id=loan.id,
                amount=-payment.amount,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, f"✅ Payment {payment.receipt_number} reversed successfully!")

            log_action(
                request=request,
                user=request.user,
                action='PAYMENT_REVERSED',
                description=f"Payment {payment.receipt_number} reversed",
                loan=loan,  # ✅ ADD THIS
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('loans:loan_detail', loan_id=loan.id)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Payment reversal failed: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to reverse payment: {str(e)}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Failed to reverse payment {payment.receipt_number}: {error_msg}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

    context = {
        'payment': payment,
        'loan': payment.loan,
    }
    return render(request, 'loans/reverse_payment.html', context)

################################################# Suspected bloat code ############################################################################
# ============================================================
# QUICKBOOKS SYNC (Separate from core logic)
# ============================================================

@login_required
def sync_to_quickbooks(request, loan_id):
    """Sync an existing loan to QuickBooks"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    # Security: Check access
    if request.user != loan.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to sync this loan.")
        return redirect('applications:staff_loan_detail', loan_id=loan.id)

    # Check if already synced
    if loan.quickbooks_customer_id:
        messages.warning(request, f"This loan is already synced to QuickBooks (Customer: {loan.quickbooks_customer_id})")
        return redirect('applications:staff_loan_detail', loan_id=loan.id)

    if request.method == 'POST':
        try:
            from quickbooks.services import QuickBooksPushService

            # Initialize QuickBooks service
            qb_service = QuickBooksPushService(request.user)

            # 1. Get customer data
            customer_name = loan.customer.get_full_name() or loan.customer.username
            first_name = loan.customer.first_name or customer_name.split()[0] if ' ' in customer_name else customer_name
            last_name = loan.customer.last_name or ' '.join(customer_name.split()[1:]) if ' ' in customer_name else 'Customer'

            customer_data = {
                'display_name': customer_name,
                'first_name': first_name,
                'last_name': last_name,
                'email': loan.customer.email,
                'phone': getattr(loan.customer, 'phone', ''),
            }

            # 2. Create customer in QuickBooks
            customer = qb_service.create_customer(customer_data)
            customer_id = customer.get('Customer', {}).get('Id')

            if not customer_id:
                raise ValueError("Failed to create customer in QuickBooks")

            # 3. Create invoice (principal + deposit)
            invoice_amount = float(loan.principal_amount + loan.deposit_paid)
            invoice_data = {
                'customer_ref': customer_id,
                'amount': invoice_amount,
                'description': f'HP Loan {loan.loan_id} - {loan.tenure_months} months @ {loan.interest_rate}%',
                'due_date': loan.first_payment_date.strftime('%Y-%m-%d') if loan.first_payment_date else None,
                'txn_date': loan.start_date.strftime('%Y-%m-%d') if loan.start_date else None,
            }
            invoice = qb_service.create_invoice(invoice_data)
            invoice_id = invoice.get('Invoice', {}).get('Id')

            if not invoice_id:
                raise ValueError("Failed to create invoice in QuickBooks")

            # 4. Process ALL confirmed payments (deposits + installments)
            all_payments = loan.payments.filter(
                status='CONFIRMED',
                is_reversed=False
            ).order_by('payment_date')

            # ✅ Track deposit progress
            deposit_remaining = loan.deposit_target - loan.deposit_paid if loan.deposit_target > 0 else 0

            for payment in all_payments:
                # ==========================================
                # ✅ SPLIT PAYMENT LOGIC
                # ==========================================

                # Step 1: Pay deposit first (if not complete)
                deposit_portion = 0
                if deposit_remaining > 0:
                    deposit_portion = min(payment.amount, deposit_remaining)
                    deposit_remaining -= deposit_portion
                    remaining = payment.amount - deposit_portion
                else:
                    remaining = payment.amount

                # Create deposit payment (if any)
                if deposit_portion > 0:
                    deposit_payment_data = {
                        'customer_ref': customer_id,
                        'invoice_ref': invoice_id,
                        'amount': float(deposit_portion),
                        'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                        'PaymentRefNum': payment.receipt_number + '-DEP',
                    }
                    qb_service.create_payment(deposit_payment_data)

                # Step 2: Pay interest next (if any due)
                interest_portion = 0
                if remaining > 0:
                    # Get the first pending installment's interest
                    first_schedule = loan.payment_schedule.filter(
                        status='PENDING'
                    ).order_by('due_date').first()

                    if first_schedule:
                        interest_portion = min(remaining, first_schedule.interest_due)
                        remaining -= interest_portion

                # Create sales receipt for interest (if any)
                if interest_portion > 0:
                    # Create sales receipt for interest
                    from quickbooks.services import QuickBooksPushService
                    interest_receipt = {
                        'customer_ref': customer_id,
                        'amount': float(interest_portion),
                        'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                        'PaymentRefNum': payment.receipt_number + '-INT',
                    }
                    # Use sales receipt endpoint for interest
                    # (This would be a separate function call)

                # Step 3: Everything else goes to principal
                if remaining > 0:
                    principal_payment_data = {
                        'customer_ref': customer_id,
                        'invoice_ref': invoice_id,
                        'amount': float(remaining),
                        'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                        'PaymentRefNum': payment.receipt_number + '-PRIN',
                    }
                    qb_service.create_payment(principal_payment_data)

            # 5. Update loan with QuickBooks IDs
            loan.quickbooks_customer_id = customer_id
            loan.quickbooks_invoice_id = invoice_id
            loan.quickbooks_synced_at = timezone.now()
            loan.save()

            log_action(
                request=request,
                user=request.user,
                action='QB_SYNC_SUCCESS',
                description=f"Loan {loan.loan_id} synced to QuickBooks. Customer: {customer_id}, Invoice: {invoice_id}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(
                request,
                f"✅ Loan {loan.loan_id} synced to QuickBooks successfully!\n"
                f"Customer ID: {customer_id}\nInvoice ID: {invoice_id}"
            )

            return redirect('applications:staff_loan_detail', loan_id=loan.id)

        except Exception as e:
            logger.error(f"QuickBooks sync failed for loan {loan.loan_id}: {str(e)}", exc_info=True)
            messages.error(request, f"❌ Failed to sync to QuickBooks: {str(e)}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Failed to sync {loan.loan_id} to QuickBooks.",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('staff_loan_detail', loan_id=loan.id)

    # GET request - show confirmation form
    context = {
        'loan': loan,
        'customer_name': loan.customer.get_full_name() or loan.customer.username,
        'customer_email': loan.customer.email,
        'deposit_info': {
            'amount': loan.deposit_paid,
            'date': loan.deposit_paid_date,
            'method': loan.deposit_payment_method,
            'receipt': loan.deposit_receipt_number,
        },
    }
    return render(request, 'loans/sync_to_quickbooks.html', context)


@login_required
def sync_status(request, loan_id):
    """Check sync status of a loan"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    if request.user != loan.customer and not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    data = {
        'loan_id': loan.loan_id,
        'is_synced': loan.quickbooks_customer_id is not None,
        'customer_id': loan.quickbooks_customer_id,
        'invoice_id': loan.quickbooks_invoice_id,
        'synced_at': loan.quickbooks_synced_at,
    }
    return JsonResponse(data)


# ============================================================
# COLLECTIONS
# ============================================================

@login_required
@staff_member_required
def collections_dashboard(request):
    """Collections dashboard for staff"""
    # Get overdue loans
    overdue_loans = []
    for loan in LoanProduct.objects.filter(status__in=['ACTIVE', 'DELINQUENT']):
        days_overdue = loan.get_days_overdue() if hasattr(loan, 'get_days_overdue') else 0
        if days_overdue > 0:
            overdue_loans.append({
                'loan': loan,
                'days_overdue': days_overdue,
                'amount': loan.outstanding_balance,
                'next_payment': loan.payment_schedule.filter(status='PENDING').first(),
            })

    # Sort by days overdue (most overdue first)
    overdue_loans.sort(key=lambda x: x['days_overdue'], reverse=True)

    context = {
        'overdue_loans': overdue_loans,
        'total_overdue': len(overdue_loans),
        'total_overdue_amount': sum(loan['amount'] for loan in overdue_loans),
        'recent_activities': CollectionActivity.objects.all().order_by('-created_at')[:20],
    }
    return render(request, 'loans/collections_dashboard.html', context)


@login_required
@staff_member_required
def log_collection_activity(request, loan_id):
    """Log a collection activity"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    if request.method == 'POST':
        try:
            activity = CollectionActivity.objects.create(
                loan=loan,
                activity_type=request.POST.get('activity_type'),
                contact_status=request.POST.get('contact_status'),
                summary=request.POST.get('summary'),
                notes=request.POST.get('notes'),
                promise_date=request.POST.get('promise_date') or None,
                promise_amount=request.POST.get('promise_amount') or None,
                follow_up_date=request.POST.get('follow_up_date') or None,
                follow_up_required=request.POST.get('follow_up_required') == 'on',
                created_by=request.user
            )

            messages.success(request, "Collection activity logged successfully!")
            return redirect('loans:loan_detail', loan_id=loan.id)

        except Exception as e:
            messages.error(request, f"Failed to log activity: {str(e)}")

    context = {
        'loan': loan,
    }
    return render(request, 'loans/log_collection_activity.html', context)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def generate_loan_id():
    """Generate unique loan ID"""
    year = timezone.now().year
    last_loan = LoanProduct.objects.filter(
        loan_id__startswith=f'LOAN-{year}'
    ).order_by('-loan_id').first()

    if last_loan:
        try:
            last_number = int(last_loan.loan_id.split('-')[-1])
            next_number = last_number + 1
        except:
            next_number = 1
    else:
        next_number = 1

    return f"LOAN-{year}-{next_number:06d}"


def calculate_installment(principal, annual_rate, tenure_months):
    """Calculate monthly installment using EMI formula"""
    if principal == 0:
        return Decimal('0.00')

    monthly_rate = annual_rate / 100 / 12

    if monthly_rate == 0:
        return (principal / tenure_months).quantize(Decimal('0.01'))

    # EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    emi = principal * monthly_rate * ((1 + monthly_rate) ** tenure_months) / (((1 + monthly_rate) ** tenure_months) - 1)
    return emi.quantize(Decimal('0.01'))


def generate_payment_schedule(loan):
    """Generate payment schedule for a loan"""
    remaining_principal = loan.principal_amount
    monthly_rate = loan.interest_rate / 100 / 12
    payment_date = loan.first_payment_date

    for i in range(1, loan.tenure_months + 1):
        interest_due = remaining_principal * monthly_rate
        principal_due = loan.monthly_installment - interest_due

        # Adjust last payment for rounding
        if i == loan.tenure_months:
            principal_due = remaining_principal
            total_due = principal_due + interest_due
        else:
            total_due = loan.monthly_installment

        PaymentSchedule.objects.create(
            loan=loan,
            installment_number=i,
            due_date=payment_date,
            principal_due=principal_due.quantize(Decimal('0.01')),
            interest_due=interest_due.quantize(Decimal('0.01')),
            total_due=total_due.quantize(Decimal('0.01')),
            status='PENDING'
        )

        remaining_principal -= principal_due
        payment_date += timedelta(days=30)

    # Adjust last payment if needed
    if remaining_principal > Decimal('0.01'):
        last_schedule = loan.payment_schedule.last()
        adjustment = remaining_principal
        last_schedule.principal_due += adjustment
        last_schedule.total_due += adjustment
        last_schedule.save()

######################################################################################################################################




##################################################################################################################################################################
# loans/views.py

def record_payment(request, loan_id):
    """Record a payment - automatically handles deposit vs installment"""
    loan = get_object_or_404(LoanProduct, id=loan_id)

    PaymentRecord = get_payment_record_model()
    PaymentMethod = get_payment_method_model()

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))
        payment_method_id = request.POST.get('payment_method')
        notes = request.POST.get('notes', '')

        # Validation
        if amount <= 0:
            messages.error(request, "Amount must be greater than 0.")
            return redirect('loans:record_payment', loan_id=loan.id)

        if amount > loan.outstanding_balance:
            messages.error(request, f"Amount exceeds outstanding balance.")
            return redirect('loans:record_payment', loan_id=loan.id)

        try:
            payment_method = get_object_or_404(PaymentMethod, id=payment_method_id)

            with transaction.atomic():
                # ✅ Determine if this is a deposit or installment
                is_deposit = not loan.deposit_complete
                category = 'DEPOSIT' if is_deposit else 'INSTALLMENT'

                # Create payment record
                payment = PaymentRecord.objects.create(
                    customer=loan.customer,
                    application=loan.application,
                    loan=loan,
                    recorded_by=request.user,
                    category=category,
                    amount=amount,
                    payment_method=payment_method,
                    #receipt_number=f"PAY-{timezone.now().strftime('%Y%m%d%H%M%S')}-{PaymentRecord.objects.count() + 1:06d}",
                    receipt_number=f"PY-{timezone.now().strftime('%H%M%S')}-{PaymentRecord.objects.count() + 1:03d}",

                    status='PENDING',
                    confirmed_by=request.user,
                    confirmed_at=timezone.now(),
                    notes=notes
                )

                # Call confirm() to trigger customer creation
                payment.confirm(request.user)

                if is_deposit:
                    # ✅ Let the model handle the deposit logic
                    excess = loan.apply_deposit_payment(amount, payment)

                    # ✅ If there's excess, create an installment payment
                    if excess > 0:
                        apply_payment_to_schedule(loan, payment, amount_to_apply=excess)

                        # Update the payment's notes
                        payment.notes = f"Payment of ${amount:,.2f}. Split into deposit ${amount - excess:,.2f} + installment ${excess:,.2f}. {notes}"
                        payment.save()

                        # ✅ LOG THE INSTALLMENT PORTION
                        log_action(
                            request=request,
                            user=request.user,
                            action='PAYMENT_MADE',
                            description=(
                                f"Split payment: ${amount:,.2f}. "
                                f"Deposit portion: ${amount - excess:,.2f}. "
                                f"Installment portion: ${excess:,.2f}. "
                                f"Loan: {loan.loan_id}. "
                                f"Customer: {loan.customer.get_full_name() if loan.customer else loan.application.Fname + ' ' + loan.application.Lname if loan.application else 'Unknown'}. "
                                f"Deposit complete: {'Yes' if loan.deposit_complete else 'No'}. "
                                f"Outstanding balance: ${loan.outstanding_balance:,.2f}."

                                #f"Installment portion of split payment: ${excess:,.2f}. "
                                #f"Loan: {loan.loan_id}. "
                                #f"Customer: {loan.customer.get_full_name() if loan.customer else 'Unknown'}. "
                                #f"Deposit complete: {'Yes' if loan.deposit_complete else 'No'}. "
                                #f"Outstanding balance: ${loan.outstanding_balance:,.2f}."
                            ),
                            loan=loan,
                            ip_address=request.META.get('REMOTE_ADDR')
                        )

                    messages.success(
                        request,
                        f"💰 Payment split: ${amount - excess} to deposit, ${excess} to installment."
                    )
                else:
                    # ✅ Regular installment payment
                    apply_payment_to_schedule(loan, payment)
                    messages.success(request, f"✅ Payment of ${amount} applied to loan.")

                # ✅ Recalculate totals
                loan.recalculate_totals()

                #return redirect('staff_loan_detail', loan_id=loan.id)
                #return redirect('customer_dashboard_apps')
                #return redirect('loans:loan_detail', loan_id=loan.id)
                if request.user.is_staff:
                    return redirect('staff_loan_detail', loan_id=loan.id)
                else:
                    return redirect('loans:loan_detail', loan_id=loan.id)

        except Exception as e:
            messages.error(request, f"Failed to record payment: {str(e)}")

    # GET request
    context = {
        'loan': loan,
        'customer': loan.customer,
        'payment_methods': PaymentMethod.objects.filter(is_active=True),
        'max_payment': loan.outstanding_balance,
        'min_payment': loan.monthly_installment,
        'must_be_deposit': not loan.deposit_complete,
        'deposit_remaining': loan.deposit_remaining,
        'deposit_paid': loan.deposit_paid,
        'deposit_target': loan.deposit_target,
        'deposit_percentage': loan.deposit_percentage,
    }
    return render(request, 'loans/record_payment.html', context)




@staff_member_required
def record_payment1(request, loan_id):
    """
    Staff view to record a payment on behalf of a customer
    """
    loan = get_object_or_404(LoanProduct, id=loan_id)

    PaymentRecord = get_payment_record_model()
    PaymentMethod = get_payment_method_model()

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))
        payment_method_id = request.POST.get('payment_method')
        notes = request.POST.get('notes', '')

        if amount <= 0:
            messages.error(request, "Payment amount must be greater than 0.")
            return redirect('loans:record_payment', loan_id=loan.id)

        if amount > loan.outstanding_balance:
            messages.error(request, f"Payment amount exceeds outstanding balance of ${loan.outstanding_balance}.")
            return redirect('loans:record_payment', loan_id=loan.id)

        try:
            payment_method = get_object_or_404(PaymentMethod, id=payment_method_id)

            # ✅ Staff can override confirmation (auto-confirm)
            payment = PaymentRecord.objects.create(
                customer=loan.customer,  # Staff records for the customer
                loan=loan,
                recorded_by=request.user,  # Staff is the recorder
                category='INSTALLMENT',
                amount=amount,
                payment_method=payment_method,
                receipt_number=f"PAY-{timezone.now().strftime('%Y%m%d')}-{PaymentRecord.objects.count() + 1:06d}",
                status='CONFIRMED',  # ✅ Staff auto-confirm
                confirmed_by=request.user,
                confirmed_at=timezone.now(),
                notes=f"Recorded by {request.user.username}. {notes}"
            )

            # Apply payment to schedule
            apply_payment_to_schedule(loan, payment)

            # Check if loan is now paid off
            if loan.outstanding_balance <= 0:
                loan.status = 'PAID_OFF'
                loan.closed_date = timezone.now()
                loan.save()

            # Audit log
            log_action(
                request=request,
                user=request.user,
                action='PAYMENT_MADE',
                description=f"Staff {request.user.username} recorded payment of ${amount} on loan {loan.loan_id}",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            return redirect('staff_loan_detail', loan_id=loan.id)

        except Exception as e:
            logger.error(f"Payment recording failed: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to record payment: {str(e)}")
            log_action(
                request=request,
                user=request.user,
                action='ERROR',
                description=f"Staff {request.user.username} recorded payment of ${amount} on loan {loan.loan_id} failed",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )


    # GET request - show payment form
    context = {
        'loan': loan,
        'customer': loan.customer,
        'payment_methods': PaymentMethod.objects.filter(is_active=True),
        'max_payment': loan.outstanding_balance,
        'min_payment': loan.monthly_installment,
        'suggested_payment': min(loan.monthly_installment, loan.outstanding_balance),
        'is_staff': True,
    }
    return render(request, 'loans/record_payment.html', context)


@staff_member_required
def edit_payment_schedule(request, schedule_id):
    """
    Edit a specific payment schedule (staff only)
    Allows changing due date, amounts, or status
    """
    schedule = get_object_or_404(PaymentSchedule, id=schedule_id)
    loan = schedule.loan

    if request.method == 'POST':
        try:
            # Get form data
            new_due_date = request.POST.get('due_date')
            new_principal = request.POST.get('principal_due')
            new_interest = request.POST.get('interest_due')
            new_status = request.POST.get('status')
            notes = request.POST.get('notes', '')

            # ✅ Validate and update
            if new_due_date:
                # Parse date (YYYY-MM-DD)
                schedule.due_date = datetime.strptime(new_due_date, '%Y-%m-%d').date()

            if new_principal:
                schedule.principal_due = Decimal(new_principal)

            if new_interest:
                schedule.interest_due = Decimal(new_interest)

            if new_status:
                schedule.status = new_status

            # ✅ Recalculate total due
            schedule.total_due = schedule.principal_due + schedule.interest_due

            # ✅ Save notes for audit
            if notes:
                schedule.notes = f"{schedule.notes}\n[Edited by {request.user.username}]: {notes}" if schedule.notes else f"[Edited by {request.user.username}]: {notes}"

            schedule.save()

            # ✅ Log the change
            log_action(
                request=request,
                user=request.user,
                action='UPDATE',
                description=f"Payment schedule #{schedule.installment_number} for loan {loan.loan_id} edited",
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, f"✅ Payment schedule #{schedule.installment_number} updated successfully!")
            #return redirect('loans:loan_detail', loan_id=loan.id)
            return redirect('staff_loan_detail', loan.id)

        except Exception as e:
            messages.error(request, f"❌ Failed to update schedule: {str(e)}")

    # GET - show edit form
    context = {
        'schedule': schedule,
        'loan': loan,
        'customer': loan.customer,
        'installment_number': schedule.installment_number,
        'due_date': schedule.due_date.strftime('%Y-%m-%d'),
        'principal_due': schedule.principal_due,
        'interest_due': schedule.interest_due,
        'total_due': schedule.total_due,
        'status': schedule.status,
        'payment_schedule_url': f"/loans/{loan.id}/schedule/{schedule.id}/edit/",
    }
    return render(request, 'loans/edit_schedule.html', context)

@staff_member_required
def admin_auto_repair_loan(request, loan_id):
    """
    Admin view to auto-repair a loan.
    """
    loan = get_object_or_404(LoanProduct, id=loan_id)

    if request.method == 'POST':
        try:
            dry_run = request.POST.get('dry_run') == 'on'
            summary = loan.auto_repair(user=request.user, dry_run=dry_run)

            # ... show messages ...
            return redirect('staff_loan_detail', loan_id=loan.id)
        except Exception as e:
            messages.error(request, f"❌ Repair failed: {str(e)}")

    # GET request - show confirmation form with dry run
    summary = loan.auto_repair(dry_run=True)

    context = {
        'loan': loan,
        'summary': summary,
    }
    return render(request, 'loans/admin_auto_repair_loan.html', context)