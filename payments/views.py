from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from decimal import InvalidOperation
from decimal import Decimal
import logging

from payments.utils import record_deposit_payment, record_deposit_payment_for_loan


# ✅ Models
from loans.models import LoanProduct, PaymentSchedule
from payments.models import PaymentRecord, PaymentMethod, PaymentReversal
from applications.models import ApplicationModel

# ✅ Services
from payments.services.reminder_service import ReminderService

from audit.services import log_action

from loans.utils import apply_payment_to_schedule

logger = logging.getLogger(__name__)

# Create your views here.

def to_decimal(value):
    """Safely convert any value to Decimal."""
    if value is None:
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0.00')



@staff_member_required
def admin_pending_payments(request):
    """
    Admin view to see all pending payments and confirm them manually
    """
    pending_payments = PaymentRecord.objects.filter(
        status='PENDING'
    ).order_by('-created_at')

    context = {
        'pending_payments': pending_payments,
        'total_pending': pending_payments.count(),
        'total_amount': sum(p.amount for p in pending_payments),
    }
    return render(request, 'payments/admin_pending_payments.html', context)

###################################################################################################################################################################

@staff_member_required
def send_manual_reminder(request, schedule_id):
    """
    Admin view to manually send a reminder (AJAX)
    Returns JSON response
    """
    logger.info(f"🔔 send_manual_reminder called for schedule {schedule_id}")

    try:
        schedule = get_object_or_404(PaymentSchedule, id=schedule_id)
        # ✅ Keep this - useful for tracking
        logger.info(f"   Schedule: #{schedule.installment_number}, Loan: {schedule.loan.loan_id}")

        if schedule.status == 'PAID':
            logger.warning(f"   Schedule already paid")
            return JsonResponse({
                'success': False,
                'error': 'This installment is already paid'
            }, status=400)

        customer = schedule.loan.customer
        if not customer:
            logger.error(f"   No customer found")
            return JsonResponse({
                'success': False,
                'error': 'No customer found for this loan'
            }, status=400)

        if not customer.email:
            logger.error(f"   Customer has no email")
            return JsonResponse({
                'success': False,
                'error': 'Customer has no email address'
            }, status=400)

        # ✅ Send reminder with user
        success = ReminderService._send_reminder(schedule, 'manual', user=request.user)

        if success:
            return JsonResponse({
                'success': True,
                'message': f'Reminder sent to {customer.email}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to send reminder. Please check logs.'
            }, status=500)

    except Exception as e:
        logger.error(f"❌ Error in send_manual_reminder: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


###############################################################################################################################################

# payments/views.py - Update admin_confirm_payment

@staff_member_required
def admin_confirm_payment(request, payment_id):
    """
    Admin view to confirm a pending payment
    """
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    if request.method == 'POST':
        try:
            # Confirm the payment
            payment.status = 'CONFIRMED'
            payment.confirmed_by = request.user
            payment.confirmed_at = timezone.now()
            payment.save()

            # Recalculate loan totals after confirmation
            loan = payment.loan
            loan.recalculate_totals()  # ✅ This updates outstanding_balance

            # ============================================================
            # ✅ PERMANENT FIX: Auto-mark installments as PAID if loan reaches zero
            # ============================================================
            if loan.outstanding_balance <= 0:
                if loan.mark_installments_as_paid_if_zero():
                    logger.info(f"✅ Auto-marked remaining installments as PAID for loan {loan.loan_id}")
                    messages.info(request, f"✅ All remaining installments marked as PAID automatically.")
            # ============================================================

            messages.success(request, f"✅ Payment {payment.receipt_number} confirmed successfully!")

            return redirect('payments:admin_payment_detail', payment_id=payment.id)

        except Exception as e:
            messages.error(request, f"Failed to confirm payment: {str(e)}")

    context = {
        'payment': payment,
    }
    return render(request, 'payments/admin_confirm_payment.html', context)







@staff_member_required
def admin_confirm_payment1(request, payment_id):
    """
    Admin manually confirms a pending payment
    """
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    if payment.status != 'PENDING':
        messages.warning(request, f"This payment is already {payment.status}.")
        return redirect('admin_pending_payments')

    if request.method == 'POST':
        try:
            # 1. Confirm the payment
            payment.confirm(request.user)

            # 2. If it's an installment payment, apply to loan
            if payment.category == 'INSTALLMENT' and payment.loan:
                apply_payment_to_schedule(payment.loan, payment)

                # Check if loan is now paid off
                if payment.loan.outstanding_balance <= 0:
                    payment.loan.status = 'PAID_OFF'
                    payment.loan.closed_date = timezone.now()
                    payment.loan.save()

            # 3. If it's a deposit, trigger loan creation
            elif payment.category == 'DEPOSIT' and payment.application:
                from loans.services.loan_creation_service import LoanCreationService
                loan = LoanCreationService.handle_deposit_confirmation(payment)
                if loan:
                    messages.success(request, f"✅ Payment confirmed and loan {loan.loan_id} created!")
                else:
                    messages.success(request, "✅ Payment confirmed but loan creation failed. Please check manually.")

            messages.success(request, f"✅ Payment {payment.receipt_number} confirmed successfully!")
            return redirect('admin_pending_payments')

        except Exception as e:
            messages.error(request, f"Failed to confirm payment: {str(e)}")

    context = {
        'payment': payment,
        'loan': payment.loan,
        'application': payment.application,
    }
    return render(request, 'payments/admin_confirm_payment.html', context)


@staff_member_required
def admin_reject_payment(request, payment_id):
    """
    Admin manually rejects a pending payment
    """
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    if payment.status != 'PENDING':
        messages.warning(request, f"This payment is already {payment.status}.")
        return redirect('admin_pending_payments')

    if request.method == 'POST':
        reason = request.POST.get('reason', 'No reason provided')

        payment.status = 'REJECTED'
        payment.notes = f"{payment.notes}\nRejected by {request.user.username}: {reason}"
        payment.save()

        messages.success(request, f"❌ Payment {payment.receipt_number} rejected.")
        return redirect('admin_pending_payments')

    context = {
        'payment': payment,
    }
    return render(request, 'payments/admin_reject_payment.html', context)


@staff_member_required
def admin_payments_list(request):
    """
    Admin view to see all payments with filtering and search
    """
    # Get all payments
    payments = PaymentRecord.objects.all().order_by('-created_at')
    statpayments = PaymentRecord.objects.filter(
        is_reversed=False  # ✅ Only show non-reversed payments
    ).order_by('-created_at')

    # ===== FILTERS =====
    payment_status = request.GET.get('status', '')
    payment_category = request.GET.get('category', '')
    payment_method = request.GET.get('method', '')
    search_query = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Apply filters
    if payment_status:
        payments = payments.filter(status=payment_status)
    if payment_category:
        payments = payments.filter(category=payment_category)
    if payment_method:
        payments = payments.filter(payment_method_id=payment_method)
    if search_query:
        payments = payments.filter(
            Q(receipt_number__icontains=search_query) |
            Q(customer__username__icontains=search_query) |
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query) |
            Q(loan__loan_id__icontains=search_query) |
            Q(application__reference_number__icontains=search_query)
        )
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            payments = payments.filter(created_at__date__gte=date_from_obj)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            payments = payments.filter(created_at__date__lte=date_to_obj)
        except ValueError:
            pass

    # ===== STATISTICS =====
    total_payments = payments.count()
    total_amount = statpayments.aggregate(total=Sum('amount'))['total'] or 0
    total_confirmed = payments.filter(status='CONFIRMED').count()
    total_pending = payments.filter(status='PENDING').count()
    total_rejected = payments.filter(status='REJECTED').count()

    # ===== PAGINATION =====
    paginator = Paginator(payments, 50)  # 50 per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # ===== FILTER OPTIONS =====

    payment_methods = PaymentMethod.objects.filter(is_active=True)

    # Categories for filter
    categories = [
        ('DEPOSIT', 'Deposit'),
        ('INSTALLMENT', 'Installment'),
        ('LATE_FEE', 'Late Fee'),
        ('FULL_SETTLEMENT', 'Full Settlement'),
        ('PARTIAL', 'Partial Payment'),
    ]

    # Statuses for filter
    statuses = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    ]

    context = {
        'payments': page_obj,
        'total_payments': total_payments,
        'total_amount': total_amount,
        'total_confirmed': total_confirmed,
        'total_pending': total_pending,
        'total_rejected': total_rejected,
        'payment_methods': payment_methods,
        'categories': categories,
        'statuses': statuses,

        # Filter values
        'selected_status': payment_status,
        'selected_category': payment_category,
        'selected_method': payment_method,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'payments/admin_payments_list.html', context)


# payments/views.py

@staff_member_required
def admin_payment_detail(request, payment_id):
    """
    Admin view to see payment details
    """
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    deposit_portion = payment.deposit_portion

    context = {
        'payment': payment,
        'deposit_portion': deposit_portion,
    }
    return render(request, 'payments/admin_payment_detail.html', context)


@staff_member_required
def admin_reverse_payment(request, payment_id):
    """
    Admin view to reverse a payment
    """
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    # ✅ BLOCK if already reversed
    if payment.is_reversed:
        messages.warning(
            request,
            f"⚠️ Payment {payment.receipt_number} is ALREADY reversed. "
            f"Reversed at: {payment.reversed_at.strftime('%Y-%m-%d %H:%M') if payment.reversed_at else 'Unknown'}. "
            f"By: {payment.reversed_by.get_full_name() if payment.reversed_by else 'System'}."
        )
        return redirect('payments:admin_payment_detail', payment_id=payment.id)

    # Check if already reversed
    if payment.is_reversed:
        messages.warning(request, "This payment has already been reversed.")
        return redirect('payments:admin_payment_detail', payment_id=payment.id)

    if request.method == 'POST':
        reason = request.POST.get('reason')
        reason_notes = request.POST.get('reason_notes', '')

        if not reason:
            messages.error(request, "Please select a reason for the reversal.")
            return redirect('payments:admin_reverse_payment', payment_id=payment.id)

        try:
            # 1. Create reversal record
            reversal = PaymentReversal.objects.create(
                original_payment=payment,
                reason=reason,
                reason_notes=reason_notes,
                amount=payment.amount,
                status='APPROVED',
                requested_by=request.user,
                approved_by=request.user,
                approved_at=timezone.now(),
                notes=request.POST.get('notes', '')
            )

            # 2. Complete the reversal
            reversal.complete_reversal(request.user)

            # 3. Recalculate loan totals after reversal
            loan = payment.loan
            loan.recalculate_totals()  # ✅ This updates outstanding_balance

            # ============================================================
            # ✅ PERMANENT FIX: Auto-mark installments as PAID if loan reaches zero
            # ============================================================
            if loan.outstanding_balance <= 0:
                if loan.mark_installments_as_paid_if_zero():
                    logger.info(f"✅ Auto-marked remaining installments as PAID for loan {loan.loan_id}")
                    messages.info(request, f"✅ All remaining installments marked as PAID automatically.")
            # ============================================================

            # ✅ ADD LOG ACTION HERE
            log_action(
                request=request,
                user=request.user,
                action='PAYMENT_REVERSED_BY_ADMIN',
                description=(
                    f"Payment {payment.receipt_number} reversed by {request.user.get_full_name() or request.user.username} in the "
                    f"amount of ${payment.amount}. "
                    f"This was an: {payment.category} "
                    f"for Loan: {loan.loan_id if loan else 'N/A'} "
                    f"belonging to {loan.application.Fname} {loan.application.Lname}"
                ),
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(
                request,
                f"✅ Payment {payment.receipt_number} reversed successfully!\n"
                f"Amount: ${payment.amount}\n"
                f"Reason: {dict(PaymentReversal.REASON_CHOICES).get(reason)}"
            )

            return redirect('payments:admin_payment_detail', payment_id=payment.id)

        except Exception as e:
            messages.error(request, f"Failed to reverse payment: {str(e)}")

    context = {
        'payment': payment,
        'loan': payment.loan,
        'reversal_reasons': PaymentReversal.REASON_CHOICES,
    }
    return render(request, 'payments/admin_reverse_payment.html', context)



@transaction.atomic
def reverse_payment_allocations(payment, user=None):
    """
    Reverse a payment and restore the schedule.
    Handles both deposits AND installment payments.
    """
    from decimal import Decimal

    loan = payment.loan
    if not loan:
        return False

    # ==========================================
    # CASE 1: DEPOSIT PAYMENT
    # ==========================================
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
        loan.recalculate_totals()
        return True

    # ==========================================
    # CASE 2: INSTALLMENT PAYMENT
    # ==========================================
    if payment.category == 'INSTALLMENT':
        # ✅ Find schedules this payment was applied to
        schedules = loan.payment_schedule.filter(
            payment_reference=payment
        )

        if schedules.exists():
            # ✅ Direct reference found - reverse each schedule
            for schedule in schedules:
                # ✅ Only reverse what was actually paid
                schedule.principal_paid -= min(payment.principal_applied, schedule.principal_paid)
                schedule.interest_paid -= min(payment.interest_applied, schedule.interest_paid)
                schedule.total_paid = schedule.principal_paid + schedule.interest_paid

                # ✅ Ensure total_paid is never negative
                if schedule.total_paid < 0:
                    schedule.total_paid = Decimal('0.00')
                    schedule.principal_paid = Decimal('0.00')
                    schedule.interest_paid = Decimal('0.00')

                # ✅ Update status
                if schedule.total_paid <= 0:
                    schedule.status = 'PENDING'
                elif schedule.total_paid < schedule.total_due:
                    schedule.status = 'PARTIAL'
                else:
                    schedule.status = 'PAID'

                schedule.payment_reference = None
                schedule.save()
        else:
            # ✅ If no direct reference, find schedules with matching amounts
            schedules = loan.payment_schedule.filter(
                status__in=['PAID', 'PARTIAL']
            ).order_by('-installment_number')

            remaining = payment.amount
            for schedule in schedules:
                if remaining <= 0:
                    break

                if schedule.total_paid > 0:
                    # ✅ Calculate how much to reverse (don't go negative)
                    principal_to_reverse = min(schedule.principal_paid, remaining)
                    interest_to_reverse = min(schedule.interest_paid, remaining)
                    total_to_reverse = principal_to_reverse + interest_to_reverse

                    if total_to_reverse > 0:
                        schedule.principal_paid -= principal_to_reverse
                        schedule.interest_paid -= interest_to_reverse
                        schedule.total_paid -= total_to_reverse
                        remaining -= total_to_reverse

                        # ✅ Ensure total_paid is never negative
                        if schedule.total_paid < 0:
                            schedule.total_paid = Decimal('0.00')
                            schedule.principal_paid = Decimal('0.00')
                            schedule.interest_paid = Decimal('0.00')

                        # ✅ Update schedule status
                        if schedule.total_paid <= 0:
                            schedule.status = 'PENDING'
                        elif schedule.total_paid < schedule.total_due:
                            schedule.status = 'PARTIAL'
                        else:
                            schedule.status = 'PAID'

                        schedule.payment_reference = None
                        schedule.save()

        # ✅ Recalculate loan totals
        loan.recalculate_totals()
        return True

    return False


##########################################################################################################################


@staff_member_required
def admin_record_payment(request, application_id):
    """
    Admin records a payment for an application.
    Handles:
    - Partial deposits (deposit not complete)
    - Full deposits (completes deposit)
    - Installments (if deposit is already complete and loan exists)
    """
    application = get_object_or_404(ApplicationModel, id=application_id)
    loan = application.loan  # May be None

    # ---------------------------------------------------------
    # ✅ DETERMINE PAYMENT TYPE
    # ---------------------------------------------------------
    deposit_complete = application.deposit_status == 'PAID'
    loan_exists = loan is not None

    if not deposit_complete:
        # Deposit not complete → still a deposit (partial or full)
        payment_type = 'DEPOSIT'
        target = application  # Use application for deposit helper
    elif loan_exists and deposit_complete:
        # Deposit complete + loan exists → installment
        payment_type = 'INSTALLMENT'
        target = loan  # Use loan for installment helper
    else:
        # No loan yet → deposit (must be partial or full)
        payment_type = 'DEPOSIT'
        target = application

    # ---------------------------------------------------------
    # Check whether deposit is complete
    # ---------------------------------------------------------
    if payment_type == 'DEPOSIT' and application.deposit_payment and application.deposit_status == 'PAID':
        messages.warning(
            request,
            f"This application already has a completed deposit. "
            f"Receipt: {application.deposit_payment.receipt_number}"
        )
        return redirect('manual_create_loan', application_id=application.id)
    # ---------------------------------------------------------
    # Get CASH payment method
    # ---------------------------------------------------------
    cash_method = PaymentMethod.objects.filter(
        method_type='CASH',
        is_active=True
    ).first()

    if not cash_method:
        messages.error(
            request,
            "No active Cash payment method exists. "
            "Please create or activate a Cash payment method first."
        )
        return redirect('manual_create_loan', application_id=application.id)

    # ---------------------------------------------------------
    # Handle form submission
    # ---------------------------------------------------------
    if request.method == 'POST':

        #amount = request.POST.get('amount', '').strip()
        amount = to_decimal(request.POST.get('amount', '0'))
        receipt_number = request.POST.get('receipt_number', '').strip()
        #payment_date = request.POST.get('payment_date', '').strip()
        notes = request.POST.get('notes', '').strip()

        payment_date_raw = request.POST.get('payment_date', '').strip()

        if payment_date_raw:
            try:
                from datetime import datetime
                payment_date = timezone.make_aware(
                    datetime.strptime(payment_date_raw, '%Y-%m-%d')
                )
            except ValueError:
                messages.error(request, "Invalid payment date.")
                return render(...)
        else:
            payment_date = timezone.now()

        # ... (validation stays the same) ...

        try:
            if payment_type == 'DEPOSIT' and application.deposit_payment and application.deposit_status == 'PAID':
                messages.warning(
                    request,
                    f"This application already has a completed deposit. "
                    f"Receipt: {application.deposit_payment.receipt_number}"
                )
                return redirect('manual_create_loan', application_id=application.id)

            with transaction.atomic():
                if payment_type == 'DEPOSIT':
                    # ✅ Use the application helper
                    result = record_deposit_payment(
                        request=request,
                        application=application,
                        amount=amount,
                        payment_method=cash_method,
                        receipt_number=receipt_number,
                        recorded_by=request.user,
                        payment_date=payment_date,
                        notes=notes
                    )
                else:
                    # ✅ Use the loan helper (for installments)
                    result = record_deposit_payment_for_loan(
                        request=request,
                        loan=loan,
                        amount=amount,
                        payment_method=cash_method,
                        receipt_number=receipt_number,
                        recorded_by=request.user,
                        payment_date=payment_date,
                        notes=notes
                    )

            # ... logging and messages (use result as before) ...
            log_action(
                request=request,
                user=request.user,
                action='CASH_DEPOSIT_RECORDED_BY_ADMIN',
                description=(
                    f"Admin recorded cash payment of ${amount:,.2f}. "
                    f"Deposit: ${result['deposit_amount']:,.2f}. "
                    f"Installment: ${result['installment_amount']:,.2f}. "
                    f"Split: {'Yes' if result['is_split'] else 'No'}. "
                    f"Application: {application.id}. "
                    f"Deposit status: {str(application.deposit_status) if application.deposit_status else 'None'}. "
                    f"Deposit complete: {'Yes' if application.deposit_status == 'PAID' else 'No'}"
                ),
                loan=application.loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )


            # ✅ Add this success redirect
            messages.success(request, f"✅ Payment of ${amount:,.2f} recorded successfully.")
            if payment_type == 'DEPOSIT':
                return redirect('manual_create_loan', application_id=application.id)
            else:
                # If it was an installment, go to the loan detail page
                return redirect('staff_loan_detail', loan_id=loan.id)

        except Exception as e:
            logger.error(f"Failed to record payment: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to record payment: {str(e)}")

    # ---------------------------------------------------------
    # GET request
    # ---------------------------------------------------------

    #auto_receipt_number = f"DEP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{PaymentRecord.objects.filter(category='DEPOSIT').count() + 1:06d}"
    #auto_receipt_number = f"DEP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{PaymentRecord.objects.count() + 1:06d}"
    auto_receipt_number = f"DP-{timezone.now().strftime('%H%M%S')}-{PaymentRecord.objects.count() + 1:03d}"

    context = {
        'application': application,
        'cash_method': cash_method,
        'auto_receipt_number': auto_receipt_number,
        # Useful defaults for the template
        'default_amount': application.deposit_paid or application.Deposit or 0,
        'default_payment_date': timezone.localdate(),
    }

    return render(
        request,
        'payments/admin_record_cash_deposit.html',
        context
    )






@staff_member_required
def admin_record_payment1(request, application_id):
    """
    Admin records a cash deposit for an application.

    This creates a confirmed PaymentRecord and links it back to the
    ApplicationModel.deposit_payment field.

    The payment is NOT automatically used to create the loan.
    The admin can proceed to the manual loan creation process afterward.
    """

    application = get_object_or_404(
        ApplicationModel,
        id=application_id
    )

    # ---------------------------------------------------------
    # Check whether a deposit payment already exists
    # ---------------------------------------------------------
    existing_payment = application.deposit_payment

    if existing_payment:
        messages.warning(
            request,
            f"This application already has a deposit payment recorded: "
            f"{existing_payment.receipt_number}"
        )

        return redirect(
            'manual_create_loan',
            application_id=application.id
        )

    # ---------------------------------------------------------
    # Get CASH payment method
    # ---------------------------------------------------------
    cash_method = PaymentMethod.objects.filter(
        method_type='CASH',
        is_active=True
    ).first()

    if not cash_method:
        messages.error(
            request,
            "No active Cash payment method exists. "
            "Please create or activate a Cash payment method first."
        )

        return redirect(
            'manual_create_loan',
            application_id=application.id
        )

    # ---------------------------------------------------------
    # Handle form submission
    # ---------------------------------------------------------
    if request.method == 'POST':

        amount_raw = request.POST.get('amount', '').strip()
        receipt_number = request.POST.get('receipt_number', '').strip()
        payment_date_raw = request.POST.get('payment_date', '').strip()
        notes = request.POST.get('notes', '').strip()

        # -----------------------------------------------------
        # Validate amount
        # -----------------------------------------------------
        if not amount_raw:
            messages.error(request, "Please enter the deposit amount.")

            return render(
                request,
                'payments/admin_record_cash_deposit.html',
                {
                    'application': application,
                    'cash_method': cash_method,
                    'amount': amount_raw,
                    'receipt_number': receipt_number,
                    'payment_date': payment_date_raw,
                    'notes': notes,
                }
            )

        try:
            amount = Decimal(amount_raw)
        except (InvalidOperation, ValueError):
            messages.error(
                request,
                "Please enter a valid deposit amount."
            )

            return render(
                request,
                'payments/admin_record_cash_deposit.html',
                {
                    'application': application,
                    'cash_method': cash_method,
                    'amount': amount_raw,
                    'receipt_number': receipt_number,
                    'payment_date': payment_date_raw,
                    'notes': notes,
                }
            )

        if amount <= Decimal('0.00'):
            messages.error(
                request,
                "Deposit amount must be greater than zero."
            )

            return render(
                request,
                'payments/admin_record_cash_deposit.html',
                {
                    'application': application,
                    'cash_method': cash_method,
                    'amount': amount_raw,
                    'receipt_number': receipt_number,
                    'payment_date': payment_date_raw,
                    'notes': notes,
                }
            )

        # -----------------------------------------------------
        # Validate receipt number
        # -----------------------------------------------------
        if not receipt_number:
            messages.error(
                request,
                "Please enter the cash receipt number."
            )

            return render(
                request,
                'payments/admin_record_cash_deposit.html',
                {
                    'application': application,
                    'cash_method': cash_method,
                    'amount': amount_raw,
                    'receipt_number': receipt_number,
                    'payment_date': payment_date_raw,
                    'notes': notes,
                }
            )

        # Check duplicate receipt number
        if PaymentRecord.objects.filter(
            receipt_number=receipt_number
        ).exists():

            messages.error(
                request,
                f"Receipt number '{receipt_number}' already exists."
            )

            return render(
                request,
                'payments/admin_record_cash_deposit.html',
                {
                    'application': application,
                    'cash_method': cash_method,
                    'amount': amount_raw,
                    'receipt_number': receipt_number,
                    'payment_date': payment_date_raw,
                    'notes': notes,
                }
            )

        # -----------------------------------------------------
        # Determine payment date
        # -----------------------------------------------------
        payment_date = timezone.now()

        if payment_date_raw:
            try:
                from datetime import datetime

                payment_date = timezone.make_aware(
                    datetime.strptime(
                        payment_date_raw,
                        '%Y-%m-%d'
                    )
                )

            except ValueError:
                messages.error(
                    request,
                    "Invalid payment date."
                )

                return render(
                    request,
                    'payments/admin_record_cash_deposit.html',
                    {
                        'application': application,
                        'cash_method': cash_method,
                        'amount': amount_raw,
                        'receipt_number': receipt_number,
                        'payment_date': payment_date_raw,
                        'notes': notes,
                    }
                )

        # -----------------------------------------------------
        # Create payment + update application atomically
        # -----------------------------------------------------
        try:

            if application.deposit_payment and application.deposit_status == 'PAID':
                messages.warning(
                    request,
                    f"This application already has a completed deposit. "
                    f"Receipt: {application.deposit_payment.receipt_number}"
                )
                return redirect('manual_create_loan', application_id=application.id)
            with transaction.atomic():
                result = record_deposit_payment(
                    request=request,
                    application=application,
                    amount=amount,
                    payment_method=cash_method,
                    receipt_number=receipt_number,
                    recorded_by=request.user,
                    payment_date=payment_date,
                    notes=notes
                )
            import sys
            print("🔍 DEBUG: Entering log_action block", file=sys.stderr)
            print(f"🔍 DEBUG: request = {request}", file=sys.stderr)
            print(f"🔍 DEBUG: request.user = {request.user}", file=sys.stderr)
            print(f"🔍 DEBUG: request.user.is_authenticated = {request.user.is_authenticated}", file=sys.stderr)
            print(f"🔍 DEBUG: action = 'CASH_DEPOSIT_RECORDED_BY_ADMIN'", file=sys.stderr)
            print(f"🔍 DEBUG: description = 'Test log with plain string'", file=sys.stderr)
            print(f"🔍 DEBUG: loan = {application.loan}", file=sys.stderr)
            print(f"🔍 DEBUG: ip_address = {request.META.get('REMOTE_ADDR')}", file=sys.stderr)


            # -----------------------------------------------------
            # ✅ LOG THE SUCCESSFUL DEPOSIT (SAME DETAILS AS CUSTOMER)
            # -----------------------------------------------------
            log_action(
                request=request,
                user=request.user,
                action='CASH_DEPOSIT_RECORDED_BY_ADMIN',
                description=(
                    f"Admin recorded cash payment of ${amount:,.2f}. "
                    f"Deposit: ${result['deposit_amount']:,.2f}. "
                    f"Installment: ${result['installment_amount']:,.2f}. "
                    f"Split: {'Yes' if result['is_split'] else 'No'}. "
                    f"Application: {application.id}. "
                    f"Deposit status: {str(application.deposit_status) if application.deposit_status else 'None'}. "
                    f"Deposit complete: {'Yes' if application.deposit_status == 'PAID' else 'No'}"
                ),
                loan=application.loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            log_action(
                request=request,
                user=request.user,
                action='CASH_DEPOSIT_RECORDED_BY_ADMIN',
                description=(
                    f"Admin recorded cash payment of ${amount:,.2f}. "
                    #f"Deposit: ${result['deposit_amount']:,.2f}. "
                    #f"Installment: ${result['installment_amount']:,.2f}. "
                    #f"Split: {'Yes' if result['is_split'] else 'No'}. "
                    #f"Application: {application.id}. "
                    #f"Deposit status: {application.deposit_status if application.deposit_status else 'None'}. "  # ✅ SAFE
                    #f"Deposit complete: {'Yes' if application.deposit_status == 'PAID' else 'No'}"
                ),
                loan=application.loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )



            # -----------------------------------------------------
            # Show success message
            # -----------------------------------------------------
            if result['is_split']:
                messages.success(
                    request,
                    f"✅ Payment of ${amount:,.2f} split: "
                    f"${result['deposit_amount']:,.2f} to deposit, "
                    f"${result['installment_amount']:,.2f} to installment."
                )
            else:
                messages.success(
                    request,
                    f"✅ Deposit of ${amount:,.2f} recorded successfully. "
                    f"Receipt: {receipt_number}"
                )

            # Go to manual loan creation
            return redirect('manual_create_loan', application_id=application.id)
            #return redirect('staff_loan_detail', loan_id=loan.id)

        except Exception as e:

            logger.error(
                f"Failed to record cash deposit for application "
                f"{application.id}: {str(e)}",
                exc_info=True
            )

            messages.error(
                request,
                f"Failed to record cash deposit: {str(e)}"
            )

    # ---------------------------------------------------------
    # GET request
    # ---------------------------------------------------------
    context = {
        'application': application,
        'cash_method': cash_method,

        # Useful defaults for the template
        'default_amount': application.deposit_paid or application.Deposit or 0,
        'default_payment_date': timezone.localdate(),
    }

    return render(
        request,
        'payments/admin_record_cash_deposit.html',
        context
    )

######################################################################################################################

# payments/views.py – inside admin_un_reverse_payment

@staff_member_required
def admin_un_reverse_payment(request, payment_id):
    payment = get_object_or_404(PaymentRecord, id=payment_id)

    # ✅ BLOCK if NOT reversed
    if not payment.is_reversed:
        messages.warning(
            request,
            f"⚠️ Payment {payment.receipt_number} is NOT reversed. "
            f"Current status: {payment.status}. "
            f"Confirmed at: {payment.confirmed_at.strftime('%Y-%m-%d %H:%M') if payment.confirmed_at else 'Unknown'}."
        )
        return redirect('payments:admin_payment_detail', payment_id=payment.id)

    if not payment.is_reversed:
        messages.warning(request, "This payment is not reversed.")
        return redirect('payments:admin_payment_detail', payment_id=payment.id)

    if request.method == 'POST':
        try:
            # 1. Get the reversal record
            reversal = PaymentReversal.objects.filter(original_payment=payment).latest('created_at')

            # 2. DELETE the reversal record (not just VOID it)
            reversal.delete()

            # 3. Restore the payment
            payment.is_reversed = False
            payment.status = 'CONFIRMED'
            payment.save()

            # ✅ REFRESH THE OBJECT FROM DB
            payment.refresh_from_db()

            #Declaration
            loan = payment.loan

            # 4. RE-APPLY THE PAYMENT TO THE SCHEDULE
            apply_payment_to_schedule(loan, payment)

            # 4. Recalculate loan totals
            loan.recalculate_totals()

            # 5. Auto-mark installments if loan reaches zero
            if loan.outstanding_balance <= 0:
                if loan.mark_installments_as_paid_if_zero():
                    logger.info(f"✅ Auto-marked remaining installments as PAID for loan {loan.loan_id}")
                    messages.info(request, f"✅ All remaining installments marked as PAID automatically.")

            # ==========================================
            # ✅ LOG THE UN-REVERSAL / REINSTATEMENT
            # ==========================================
            log_action(
                request=request,
                user=request.user,
                action='PAYMENT_REINSTATED_BY_ADMIN',
                description=(
                    f"Payment {payment.receipt_number} reinstated by {request.user.get_full_name() or request.user.username}. "
                    f"Amount: ${payment.amount}. "
                    f"Category: {payment.category}. "
                    f"Loan: {loan.loan_id if loan else 'N/A'}"
                ),
                loan=loan,
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, f"✅ Payment {payment.receipt_number} un-reversed successfully!")

            return redirect('payments:admin_payment_detail', payment_id=payment.id)

        except Exception as e:
            messages.error(request, f"Failed to un-reverse payment: {str(e)}")

    context = {
        'payment': payment,
        'loan': payment.loan,
    }
    return render(request, 'payments/admin_un_reverse_payment.html', context)