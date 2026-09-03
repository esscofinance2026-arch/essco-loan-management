from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
import logging
from django.utils import timezone
from datetime import date


logger = logging.getLogger(__name__)



from django.apps import apps

def get_payment_record_model():
    """Return the PaymentRecord model (lazy-loaded)."""
    return apps.get_model('payments', 'PaymentRecord')

def get_payment_method_model():
    """Return the PaymentMethod model (lazy-loaded)."""
    return apps.get_model('payments', 'PaymentMethod')





@transaction.atomic
def apply_payment_to_schedule(loan, payment, amount_to_apply=None):
    """
    Apply a payment to the loan's payment schedule.
    - Installment #1 can be paid early (exemption)
    - All other installments must wait until their due date
    - Any leftover goes directly to principal
    """
    import sys

    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"🔍 apply_payment_to_schedule START")
    logger.info(f"   Loan: {loan.loan_id}")
    logger.info(f"   Payment: {payment.receipt_number}")
    logger.info(f"   Amount: ${payment.amount}")
    logger.info(f"   Category: {payment.category}")
    logger.info(f"   Outstanding Before: ${loan.outstanding_balance}")

    if amount_to_apply is None:
        amount_to_apply = payment.amount

    print(f"\n🔍 DEBUG: Starting apply_payment_to_schedule for loan {loan.loan_id}")
    print(f"   Payment amount: ${amount_to_apply}")
    print(f"   Outstanding Principal before: ${loan.principal_amount}")

    today = date.today()

    # ✅ Separate tracking for installment vs principal
    remaining_amount = amount_to_apply
    extra_principal = Decimal('0.00')

    # ------------------------------------------------------------
    # 1. ✅ Check if Installment #1 is pending and can be paid early
    # ------------------------------------------------------------
    first_installment = loan.payment_schedule.filter(
        installment_number=1,
        status__in=['PENDING', 'PARTIAL']
    ).first()

    if first_installment and first_installment.status != 'PAID':
        print(f"   🔹 Installment #1 is pending. Amount due: ${first_installment.total_due}")
        remaining_due = first_installment.total_due - first_installment.total_paid

        if remaining_due > 0:
            if remaining_amount >= remaining_due:
                # ✅ Fully pay Installment #1
                first_installment.status = 'PAID'
                first_installment.paid_at = timezone.now()

                principal_paid = first_installment.principal_due - first_installment.principal_paid

                first_installment.total_paid += remaining_due
                first_installment.interest_paid += first_installment.interest_due - first_installment.interest_paid
                first_installment.principal_paid += first_installment.principal_due - first_installment.principal_paid
                first_installment.payment_reference = payment
                first_installment.save()

                print(f"      ✅ Paid Installment #1 fully: ${remaining_due}")
                remaining_amount -= remaining_due
                print(f"      Remaining amount after #1: ${remaining_amount}")

                # ✅ ALSO deduct the principal portion from the loan itself
                #principal_paid = remaining_due - (first_installment.interest_due - first_installment.interest_paid)

                loan.principal_amount -= principal_paid
                loan.total_principal_paid += principal_paid
                loan.save()

                print(f"      ✅ Principal deducted: ${principal_paid}")
                print(f"      New Outstanding Principal: ${loan.principal_amount}")

            else:
                # Partially pay Installment #1
                interest_remaining = first_installment.interest_due - first_installment.interest_paid
                if remaining_amount <= interest_remaining:
                    interest_applied = remaining_amount
                    principal_applied = Decimal('0')
                else:
                    interest_applied = interest_remaining
                    principal_applied = remaining_amount - interest_remaining

                first_installment.interest_paid += interest_applied
                first_installment.principal_paid += principal_applied
                first_installment.total_paid += remaining_amount
                first_installment.payment_reference = payment
                first_installment.status = 'PARTIAL'
                first_installment.save()

                print(f"      ⚠️ Partial payment on Installment #1: ${remaining_amount}")
                remaining_amount = 0
                print(f"      Remaining amount after #1: ${remaining_amount}")
    else:
        print(f"   🔹 Installment #1 is already paid or not found.")

    # ------------------------------------------------------------
    # 2. ✅ Pay the oldest due installment (if any) — after #1
    # ------------------------------------------------------------
    current_schedule = loan.payment_schedule.filter(
        status__in=['PENDING', 'PARTIAL'],
        installment_number__gt=1,
        due_date__year=today.year,
        due_date__month=today.month
    ).order_by('due_date').first()

    if current_schedule:
        print(f"   🔹 Found due installment #{current_schedule.installment_number} (${current_schedule.total_due})")
        remaining_due = current_schedule.total_due - current_schedule.total_paid

        if remaining_due > 0:
            if remaining_amount >= remaining_due:
                # ✅ Fully pay the installment
                current_schedule.status = 'PAID'
                current_schedule.paid_at = timezone.now()
                current_schedule.total_paid += remaining_due

                principal_paid = current_schedule.principal_due - current_schedule.principal_paid

                current_schedule.interest_paid += current_schedule.interest_due - current_schedule.interest_paid
                current_schedule.principal_paid += current_schedule.principal_due - current_schedule.principal_paid
                current_schedule.payment_reference = payment
                current_schedule.save()

                print(f"      ✅ Paid due installment #{current_schedule.installment_number} fully: ${remaining_due}")
                remaining_amount -= remaining_due
                print(f"      Remaining amount after due installment: ${remaining_amount}")

                # ✅ ALSO deduct the principal portion from the loan

                loan.principal_amount -= principal_paid
                loan.total_principal_paid += principal_paid
                loan.save()

                print(f"      ✅ Principal deducted: ${principal_paid}")
                print(f"      New Outstanding Principal: ${loan.principal_amount}")

            else:
                # Partial payment
                interest_remaining = current_schedule.interest_due - current_schedule.interest_paid
                if remaining_amount <= interest_remaining:
                    interest_applied = remaining_amount
                    principal_applied = Decimal('0')
                else:
                    interest_applied = interest_remaining
                    principal_applied = remaining_amount - interest_remaining

                current_schedule.interest_paid += interest_applied
                current_schedule.principal_paid += principal_applied
                current_schedule.total_paid += remaining_amount
                current_schedule.payment_reference = payment
                current_schedule.status = 'PARTIAL'
                current_schedule.save()

                print(f"      ⚠️ Partial payment on due installment #{current_schedule.installment_number}: ${remaining_amount}")
                remaining_amount = 0
                print(f"      Remaining amount after due installment: ${remaining_amount}")
    else:
        print(f"   🔹 No other due installments found for this month.")


    # ------------------------------------------------------------
    # 3. ✅ Apply any leftover to principal
    # ------------------------------------------------------------
    if remaining_amount > 0:
        print(f"   🔹 Applying leftover ${remaining_amount} to principal")
        loan.principal_amount -= remaining_amount
        loan.total_principal_paid += remaining_amount
        loan.save()

        payment.notes = f"{payment.notes}\nExtra principal payment: ${remaining_amount:,.2f}"
        payment.save()

        # ✅ Pass the correct leftover amount to recalculation
        extra_principal = remaining_amount
        print(f"      ✅ Extra principal applied: ${extra_principal}")
        print(f"      New Outstanding Principal: ${loan.principal_amount}")
    else:
        print(f"   🔹 No leftover to apply to principal.")

    # ------------------------------------------------------------
    # 4. ✅ Recalculate the remaining schedule
    # ------------------------------------------------------------
    if extra_principal > 0:
        print(f"   🔹 Recalculating remaining schedule...")
        recalculate_remaining_schedule(loan, new_principal=loan.principal_amount)
        print(f"      ✅ Schedule recalculated.")
    else:
        print(f"   🔹 No schedule recalculation needed (no extra principal).")

    # ------------------------------------------------------------
    # 5. ✅ Recalculate and clean up
    # ------------------------------------------------------------
    loan.recalculate_totals()

    unused_installments = loan.payment_schedule.filter(
        status='PENDING',
        total_paid=0,
        due_date__gt=loan.maturity_date
    )

    # ✅ Update payment allocation fields
    payment.principal_applied = sum(
        s.principal_paid for s in loan.payment_schedule.filter(payment_reference=payment)
    )
    payment.interest_applied = sum(
        s.interest_paid for s in loan.payment_schedule.filter(payment_reference=payment)
    )
    payment.fees_applied = Decimal('0.00')
    payment.save()

    # ✅ FORCE update payment allocation fields
    payment.principal_applied = Decimal('0.00')
    payment.interest_applied = Decimal('0.00')

    for schedule in loan.payment_schedule.filter(payment_reference=payment):
        payment.principal_applied += schedule.principal_paid
        payment.interest_applied += schedule.interest_paid

    payment.fees_applied = Decimal('0.00')
    payment.save()





    if payment.category == 'INSTALLMENT' and payment.status == 'CONFIRMED':
        try:
            # Import the service inside to avoid circular imports
            from quickbooks.services import QuickBooksPushService
            from quickbooks.models import QuickBooksToken

            # Check if connected
            if QuickBooksToken.objects.filter(user=payment.recorded_by).exists():
                service = QuickBooksPushService(payment.recorded_by)
                # Trigger the payment sync
                service.sync_payment_to_quickbooks(payment)
                logger.info(f"✅ Synced installment {payment.receipt_number} to QuickBooks")
        except Exception as e:
            logger.error(f"❌ Failed to sync installment {payment.receipt_number}: {str(e)}")



    if unused_installments.exists():
        unused_installments.delete()
        print(f"   🗑️ Removed {unused_installments.count()} unused installments.")

    print(f"🔍 DEBUG: Finished apply_payment_to_schedule")
    print(f"   Final Outstanding Principal: ${loan.principal_amount}\n")

    return True




def apply_excess_to_installment(loan, payment, excess):
    """
    Apply excess payment to the first installment.

    Args:
        loan: The loan object
        payment: The payment record
        excess: The excess amount to apply

    Returns:
        bool: True if excess was applied, False if not
    """
    from decimal import Decimal

    if excess <= 0:
        return False

    # Apply excess to the first installment
    apply_payment_to_schedule(loan, payment, amount_to_apply=excess)

    # Update loan totals
    loan.total_paid += excess
    loan.outstanding_balance -= excess
    loan.save()

    # Update payment notes
    payment.notes = f"{payment.notes}\nExcess of ${excess:,.2f} applied to installment."
    payment.save()

    return True




def recalculate_remaining_schedule(loan, new_principal=None):
    """
    Recalculate the remaining payment schedule after an extra principal payment.
    This shrinks the final payment and ensures the schedule is visually correct.
    """
    # 1. Get the remaining balance and remaining months
    print(f"🔍 Recalculating schedule for {loan.loan_id}")

    # ✅ Use the new principal if provided, otherwise fallback to outstanding_balance
    if new_principal is not None:
        remaining_balance = new_principal
    else:
        remaining_balance = loan.outstanding_balance

    print(f"   Outstanding balance: {remaining_balance}")
    pending_schedules = loan.payment_schedule.filter(
        status__in=['PENDING', 'PARTIAL']
    ).order_by('due_date')
    print(f"   Pending schedules: {pending_schedules.count()}")
    remaining_months = pending_schedules.count()

    if remaining_months == 0:
        return

    # 2. Monthly interest rate
    monthly_rate = (loan.interest_rate / 100) / 12

    # 3. Recalculate the schedule
    remaining = remaining_balance
    total_interest = Decimal('0.00')
    total_principal = Decimal('0.00')

    for i, schedule in enumerate(pending_schedules):
        if remaining <= Decimal('0.00'):
            # Delete this and all remaining schedules
            pending_schedules.filter(installment_number__gte=schedule.installment_number).delete()
            break

        # Interest due on the current balance
        interest_due = (remaining * monthly_rate).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        # For the final month, pay off the remaining balance
        if i == remaining_months - 1:
            principal_due = remaining
        else:
            principal_due = (loan.monthly_installment - interest_due).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            if principal_due < 0:
                principal_due = Decimal('0.00')

        total_due = principal_due + interest_due

        # Update the schedule row
        schedule.principal_due = principal_due
        schedule.interest_due = interest_due
        schedule.total_due = total_due
        schedule.save()

        remaining -= principal_due
        total_interest += interest_due
        total_principal += principal_due

    # 4. Update loan totals
    loan.total_interest = total_interest
    loan.total_payable = total_principal + total_interest
    loan.outstanding_balance = remaining
    #loan.principal_amount = total_principal
    loan.total_paid = loan.total_principal_paid
    loan.save()

    # 5. Delete any truly unused installments
    unused = loan.payment_schedule.filter(
        status='PENDING',
        total_paid=0,
        due_date__gt=loan.maturity_date
    )
    if unused.exists():
        unused.delete()