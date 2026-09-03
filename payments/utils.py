# payments/utils.py
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from payments.models import PaymentRecord
from audit.services import log_action

###############################################################################################################################################

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

###########################################################################################################################################################
# payments/utils.py - Fix _split_payment

# payments/utils.py - Add debugging to _split_payment

def _split_payment(application, amount, payment_method, payment_date, recorded_by, notes='', loan=None):
    """
    Internal helper: splits a payment into deposit + installment portions.
    ✅ Uses loan.deposit_paid if loan exists.
    """
    from decimal import Decimal
    import logging
    logger = logging.getLogger(__name__)

    deposit_target = to_decimal(application.Deposit)

    # ✅ Get deposit paid from loan if available
    if loan:
        deposit_paid = to_decimal(loan.deposit_paid)
        logger.info(f"🔍 _split_payment: Using loan.deposit_paid = ${deposit_paid}")
    else:
        deposit_paid = to_decimal(application.deposit_paid)
        logger.info(f"🔍 _split_payment: Using application.deposit_paid = ${deposit_paid}")

    deposit_remaining = max(deposit_target - deposit_paid, Decimal('0.00'))

    logger.info(f"🔍 _split_payment:")
    logger.info(f"   Amount: ${amount}")
    logger.info(f"   Deposit Target: ${deposit_target}")
    logger.info(f"   Deposit Paid: ${deposit_paid}")
    logger.info(f"   Deposit Remaining: ${deposit_remaining}")
    logger.info(f"   Amount > Deposit Remaining: {amount > deposit_remaining}")

    # Determine split
    if amount > deposit_remaining:
        deposit_amount = deposit_remaining
        installment_amount = amount - deposit_remaining
        is_split = True
        logger.info(f"   ✅ SPLIT: ${deposit_amount} to deposit, ${installment_amount} to installment")
    else:
        deposit_amount = amount
        installment_amount = Decimal('0.00')
        is_split = False
        logger.info(f"   ✅ NO SPLIT: ${deposit_amount} to deposit, $0 to installment")


    # 1. Create DEPOSIT payment
    deposit_payment = PaymentRecord.objects.create(
        customer=application.customer,
        application=application,
        loan=loan,  # ✅ Link to loan if exists
        receipt_number=f"DEP-{timezone.now().strftime('%Y%m%d%H%M%S')}-{PaymentRecord.objects.filter(category='DEPOSIT').count() + 1:04d}",
        category='DEPOSIT',
        amount=deposit_amount,
        payment_method=payment_method,
        payment_date=payment_date,
        status='PENDING',
        confirmed_by=recorded_by,
        confirmed_at=timezone.now(),
        auto_create_loan=False,
        notes=f"Deposit portion. {notes}",
        recorded_by=recorded_by,
    )

    # 2. Create INSTALLMENT payment (if split)
    installment_payment = None
    if is_split:
        installment_payment = PaymentRecord.objects.create(
            customer=application.customer,
            application=application,
            loan=loan,  # ✅ Link to loan if exists
            receipt_number=f"PAY-{timezone.now().strftime('%Y%m%d%H%M%S')}-{PaymentRecord.objects.filter(category='INSTALLMENT').count() + 1:04d}",
            category='INSTALLMENT',
            amount=installment_amount,
            payment_method=payment_method,
            payment_date=payment_date,
            status='PENDING',
            confirmed_by=recorded_by,
            confirmed_at=timezone.now(),
            auto_create_loan=False,
            notes=f"Installment portion. {notes}",
            recorded_by=recorded_by,
        )

    return {
        'deposit_payment': deposit_payment,
        'installment_payment': installment_payment,
        'deposit_amount': deposit_amount,
        'installment_amount': installment_amount,
        'is_split': is_split,
        'notes': notes,
    }

#############################################################################################################################################################

# payments/utils.py

def record_deposit_payment(request, application, amount, payment_method, receipt_number, recorded_by, payment_date=None, notes=''):
    """
    Admin-facing: records a deposit on an application.
    Uses _split_payment internally.
    """
    if payment_date is None:
        payment_date = timezone.now()

    # Call the internal splitter
    result = _split_payment(
        application=application,
        amount=amount,
        payment_method=payment_method,
        payment_date=payment_date,
        recorded_by=recorded_by,
        notes=notes
    )

    # ✅ CALL confirm() TO TRIGGER CUSTOMER CREATION
    if result['deposit_payment']:
        result['deposit_payment'].confirm(recorded_by)

    deposit_target = to_decimal(application.Deposit)
    deposit_paid = to_decimal(application.deposit_paid)

    # Update application deposit fields
    application.deposit_paid += result['deposit_amount']
    application.deposit_paid_date = payment_date
    application.deposit_payment_method = payment_method.name
    application.deposit_receipt_number = receipt_number
    application.deposit_status = 'PAID' if deposit_paid >= deposit_target else 'PARTIAL'
    #application.deposit_status = 'PAID' if application.deposit_paid >= application.Deposit else 'PARTIAL'
    #application.deposit_status = 'PAID' if application.deposit_paid >= Decimal(str(application.Deposit)) else 'PARTIAL'
    application.deposit_payment = result['deposit_payment']
    application.save()

    # If loan exists, update loan deposit fields
    loan = application.loan
    if loan:
        loan.deposit_payment = result['deposit_payment']
        loan.deposit_paid += result['deposit_amount']
        loan.deposit_paid_date = payment_date
        loan.deposit_payment_method = payment_method.name
        loan.deposit_receipt_number = receipt_number
        loan.deposit_complete = True if loan.deposit_paid >= loan.deposit_target else False
        loan.save()

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
            f"Deposit complete: {'Yes' if application.deposit_status == 'PAID' else 'No'}"
        ),
        loan=application.loan,
        ip_address=request.META.get('REMOTE_ADDR')
    )

    # Return result for views to use
    return result

###############################################Customer Facing############################################################################################################

# payments/utils.py

def record_deposit_payment_for_loan1(request, loan, amount, payment_method, receipt_number, recorded_by, payment_date=None, notes=''):
    """
    Customer-facing: records a deposit on an existing loan.
    Uses _split_payment internally.
    """
    from loans.utils import apply_payment_to_schedule

    if payment_date is None:
        payment_date = timezone.now()

    application = loan.application
    if not application:
        raise ValueError("Loan has no associated application")

    # Call the internal splitter
    result = _split_payment(
        application=application,
        amount=amount,
        payment_method=payment_method,
        payment_date=payment_date,
        recorded_by=recorded_by,
        notes=notes
    )

    # ✅ CALL confirm() TO TRIGGER CUSTOMER CREATION
    if result['deposit_payment']:
        result['deposit_payment'].confirm(recorded_by)

    #deposit_target = to_decimal(application.Deposit)
    #deposit_paid = to_decimal(application.deposit_paid)

    # Update loan deposit fields
    loan.deposit_paid += result['deposit_amount']
    loan.deposit_paid_date = payment_date
    loan.deposit_payment_method = payment_method.name
    loan.deposit_receipt_number = receipt_number
    loan.deposit_payment = result['deposit_payment']
    loan.deposit_complete = True if loan.deposit_paid >= loan.deposit_target else False
    loan.total_paid += result['deposit_amount']
    #loan.outstanding_balance -= result['deposit_amount']
    loan.save()

    # If installment payment exists, apply to schedule
    if result['installment_payment']:
        apply_payment_to_schedule(loan, result['installment_payment'])
        loan.total_paid += result['installment_amount']
        loan.outstanding_balance -= result['installment_amount']
        loan.save()

    # -----------------------------------------------------
    # ✅ LOG THE PAYMENT WITH FULL DETAILS
    # -----------------------------------------------------
    log_action(
        request=request,
        user=request.user,
        action='PAYMENT_MADE',
        description=(
            f"Customer payment of ${amount:,.2f}. "
            f"Deposit: ${result['deposit_amount']:,.2f}. "
            f"Installment: ${result['installment_amount']:,.2f}. "
            f"Split: {'Yes' if result['is_split'] else 'No'}. "
            f"Loan: {loan.loan_id}. "
            f"New outstanding: ${loan.outstanding_balance:,.2f}. "
            f"Deposit complete: {'Yes' if loan.deposit_complete else 'No'}"
        ),
        loan=loan,
        ip_address=request.META.get('REMOTE_ADDR')
    )

    # Return result for views to use
    return result




# payments/utils.py - Add debugging to record_deposit_payment_for_loan

def record_deposit_payment_for_loan(request, loan, amount, payment_method, receipt_number, recorded_by, payment_date=None, notes=''):
    """
    Customer-facing: records a deposit on an existing loan.
    ✅ Deposits DO NOT reduce outstanding_balance.
    """
    from loans.utils import apply_payment_to_schedule
    import logging
    logger = logging.getLogger(__name__)

    if payment_date is None:
        payment_date = timezone.now()

    application = loan.application
    if not application:
        raise ValueError("Loan has no associated application")

    logger.info(f"🔍 record_deposit_payment_for_loan START")
    logger.info(f"   Loan: {loan.loan_id}")
    logger.info(f"   Amount: ${amount}")
    logger.info(f"   Deposit Target: ${loan.deposit_target}")
    logger.info(f"   Deposit Paid Before: ${loan.deposit_paid}")
    logger.info(f"   Outstanding Before: ${loan.outstanding_balance}")
    logger.info(f"   Status Before: {loan.status}")

    # ✅ Pass the loan to _split_payment
    result = _split_payment(
        application=application,
        loan=loan,  # ✅ Pass the loan!
        amount=amount,
        payment_method=payment_method,
        payment_date=payment_date,
        recorded_by=recorded_by,
        notes=notes
    )

    logger.info(f"🔍 _split_payment result:")
    logger.info(f"   Deposit Amount: ${result['deposit_amount']}")
    logger.info(f"   Installment Amount: ${result['installment_amount']}")
    logger.info(f"   Is Split: {result['is_split']}")

    # ✅ CALL confirm() TO TRIGGER CUSTOMER CREATION
    if result['deposit_payment']:
        result['deposit_payment'].confirm(recorded_by)
        logger.info(f"   Deposit Payment Created: {result['deposit_payment'].receipt_number}")

    # ✅ Update loan deposit fields (DO NOT change outstanding_balance)
    loan.deposit_paid += result['deposit_amount']
    loan.deposit_paid_date = payment_date
    loan.deposit_payment_method = payment_method.name
    loan.deposit_receipt_number = receipt_number
    loan.deposit_payment = result['deposit_payment']
    loan.deposit_complete = True if loan.deposit_paid >= loan.deposit_target else False

    logger.info(f"🔍 After deposit update:")
    logger.info(f"   Deposit Paid After: ${loan.deposit_paid}")
    logger.info(f"   Deposit Complete: {loan.deposit_complete}")

    # ✅ ONLY update total_paid, NOT outstanding_balance
    loan.total_paid += result['deposit_amount']
    loan.save()

    # If installment payment exists, apply to schedule
    if result['installment_payment']:
        logger.info(f"🔍 Applying installment payment: {result['installment_payment'].receipt_number}")
        apply_payment_to_schedule(loan, result['installment_payment'])
        loan.total_paid += result['installment_amount']
        loan.recalculate_totals()
        logger.info(f"   Outstanding After: ${loan.outstanding_balance}")
    else:
        logger.info(f"🔍 No installment payment - recalculating totals")
        loan.recalculate_totals()

    logger.info(f"🔍 record_deposit_payment_for_loan END")
    logger.info(f"   Final Outstanding: ${loan.outstanding_balance}")
    logger.info(f"   Final Status: {loan.status}")

    # -----------------------------------------------------
    # ✅ LOG THE PAYMENT WITH FULL DETAILS
    # -----------------------------------------------------
    log_action(
        request=request,
        user=request.user,
        action='PAYMENT_MADE',
        description=(
            f"Customer payment of ${amount:,.2f}. "
            f"Deposit: ${result['deposit_amount']:,.2f}. "
            f"Installment: ${result['installment_amount']:,.2f}. "
            f"Split: {'Yes' if result['is_split'] else 'No'}. "
            f"Loan: {loan.loan_id}. "
            f"New outstanding: ${loan.outstanding_balance:,.2f}. "
            f"Deposit complete: {'Yes' if loan.deposit_complete else 'No'}"
        ),
        loan=loan,
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return result


