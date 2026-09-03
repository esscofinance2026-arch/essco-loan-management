# quickbooks/views.py

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from quickbooks.services import QuickBooksAuthService
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import logging
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from loans.models import LoanProduct
from quickbooks.services import QuickBooksPushService
from quickbooks.models import QuickBooksToken, QuickBooksSyncLog
from datetime import date
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from decimal import Decimal
from loans.models import PaymentSchedule



logger = logging.getLogger(__name__)

@login_required
def connect_quickbooks(request):
    """Start QuickBooks OAuth flow"""
    from quickbooks.services import QuickBooksAuthService
    from quickbooks.models import QuickBooksToken
    import logging

    logger = logging.getLogger(__name__)

    # Check if already connected
    if QuickBooksToken.objects.filter(user=request.user).exists():
        messages.info(request, "You are already connected to QuickBooks.")
        return redirect('sync_dashboard')

    try:
        auth_service = QuickBooksAuthService(request.user)
        auth_url = auth_service.get_auth_url()

        # Validate that auth_url is not empty
        if not auth_url:
            logger.error("Failed to generate auth URL - check QuickBooks settings")
            messages.error(request, "Configuration error. Please contact support.")
            return redirect('sync_dashboard')

        context = {
            'auth_url': auth_url,
        }
        return render(request, 'quickbooks/connect.html', context)

    except Exception as e:
        logger.error(f"Error generating QuickBooks auth URL: {str(e)}")
        messages.error(request, f"Error connecting to QuickBooks: {str(e)}")
        return redirect('sync_dashboard')

@login_required
def oauth_callback(request):
    """Handle OAuth callback from QuickBooks"""
    auth_code = request.GET.get('code')
    realm_id = request.GET.get('realmId')

    if not auth_code or not realm_id:
        messages.error(request, "Authorization failed. Please try again.")
        return redirect('connect_quickbooks')

    try:
        auth_service = QuickBooksAuthService(request.user)
        token_data = auth_service.exchange_code_for_tokens(auth_code, realm_id)
        messages.success(request, "Successfully connected to QuickBooks!")
        return redirect('poc_dashboard')
    except Exception as e:
        messages.error(request, f"Error connecting to QuickBooks: {str(e)}")
        return redirect('connect_quickbooks')

@login_required
def disconnect_quickbooks(request):
    """Disconnect from QuickBooks"""
    from quickbooks.models import QuickBooksToken
    try:
        token = QuickBooksToken.objects.get(user=request.user)
        token.delete()
        messages.success(request, "Disconnected from QuickBooks.")
    except QuickBooksToken.DoesNotExist:
        messages.warning(request, "You are not connected to QuickBooks.")

    return redirect('poc_dashboard')


@login_required
@staff_member_required
def sync_dashboard(request):
    """Display sync status dashboard"""
    from quickbooks.models import QuickBooksSyncLog, QuickBooksToken

    # Check connection status
    is_connected = QuickBooksToken.objects.filter(user=request.user).exists()

    # Get all sync logs
    sync_logs = QuickBooksSyncLog.objects.all().order_by('-created_at')

    # Stats
    total_syncs = sync_logs.count()
    successful = sync_logs.filter(status='SUCCESS').count()
    failed = sync_logs.filter(status='FAILED').count()
    pending = sync_logs.filter(status='PENDING').count()

    # Recent syncs (last 10)
    recent_syncs = sync_logs[:10]

    context = {
        'is_connected': is_connected,
        'total_syncs': total_syncs,
        'successful': successful,
        'failed': failed,
        'pending': pending,
        'recent_syncs': recent_syncs,
    }

    return render(request, 'quickbooks/dashboard.html', context)


@staff_member_required
@login_required
@require_POST
def retry_sync(request, log_id):
    """Retry a failed sync"""
    from quickbooks.models import QuickBooksSyncLog
    from quickbooks.services import QuickBooksPushService

    try:
        log = QuickBooksSyncLog.objects.get(id=log_id)

        # Check if connected
        from quickbooks.models import QuickBooksToken
        if not QuickBooksToken.objects.filter(user=request.user).exists():
            return JsonResponse({'success': False, 'error': 'Not connected to QuickBooks'})

        service = QuickBooksPushService(request.user)

        # Retry based on action type
        if log.action == 'CREATE_CUSTOMER':
            # Reconstruct customer data from log
            customer_data = log.data_sent
            result = service.create_customer(customer_data)
            log.quickbooks_id = result['Customer']['Id']

        elif log.action == 'CREATE_INVOICE':
            invoice_data = log.data_sent
            result = service.create_invoice(invoice_data)
            log.quickbooks_id = result['Invoice']['Id']

        elif log.action == 'CREATE_PAYMENT':
            payment_data = log.data_sent
            result = service.create_payment(payment_data)
            log.quickbooks_id = result['Payment']['Id']

        # Update log
        log.status = 'SUCCESS'
        log.response_data = result
        log.synced_at = timezone.now()
        log.error_message = ''
        log.save()

        return JsonResponse({'success': True})

    except QuickBooksSyncLog.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Log not found'})
    except Exception as e:
        # Update log with new error
        if 'log' in locals():
            log.status = 'FAILED'
            log.error_message = str(e)
            log.save()
        return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
@login_required
def sync_all_loans(request):
    """Sync all pending loans to QuickBooks"""
    from loans.models import LoanProduct
    from quickbooks.models import QuickBooksSyncLog, QuickBooksToken
    from quickbooks.services import QuickBooksPushService
    from decimal import Decimal

    # Check connection
    if not QuickBooksToken.objects.filter(user=request.user).exists():
        messages.error(request, "Please connect to QuickBooks first.")
        return redirect('connect_quickbooks')

    # Get loans that haven't been synced yet
    synced_loan_ids = QuickBooksSyncLog.objects.filter(
        status='SUCCESS',
        action='CREATE_INVOICE'
    ).values_list('loan_id', flat=True)

    # ✅ Only get loans that haven't been synced
    pending_loans = LoanProduct.objects.filter(
        quickbooks_customer_id__isnull=True
    ).exclude(id__in=synced_loan_ids)

    if not pending_loans:
        messages.info(request, "All loans are already synced to QuickBooks!")
        return redirect('sync_dashboard')

    service = QuickBooksPushService(request.user)
    successful = 0
    failed = 0

    for loan in pending_loans:
        try:
            # 1. Create or find customer
            customer_data = {
                'email': loan.customer.email if loan.customer else '',
                'first_name': loan.customer.first_name if loan.customer else '',
                'last_name': loan.customer.last_name if loan.customer else '',
                'display_name': loan.customer.get_full_name() if loan.customer else f"Loan #{loan.id}",
                'phone': getattr(loan.customer, 'phone', ''),
                'customer_id': loan.customer.customer_id if loan.customer else '',
            }
            customer_result = service.create_customer(customer_data)
            customer_ref = customer_result['Customer']['Id']

            # 2. Create invoice (principal + deposit)
            if loan.application and loan.application.Financed_Amt and loan.application.Deposit:
                invoice_amount = float(loan.application.Financed_Amt + loan.application.Deposit)
            else:
                invoice_amount = float(loan.principal_amount + loan.deposit_paid)

            invoice_data = {
                'doc_number': f"LOAN-{loan.loan_id}",
                'customer_ref': customer_ref,
                'amount': invoice_amount,
                'description': f"HP Loan {loan.loan_id} - {loan.tenure_months} months @ {loan.interest_rate}%",
                'due_date': loan.first_payment_date.strftime('%Y-%m-%d') if loan.first_payment_date else None,
                'txn_date': loan.start_date.strftime('%Y-%m-%d') if loan.start_date else None,
                'invoice_id': str(loan.id),
                'loan_id': loan.loan_id,
            }
            invoice_result = service.create_invoice(invoice_data)
            invoice_id = invoice_result['Invoice']['Id']

            # 3. Process ALL payments (read from allocation fields)
            all_payments = loan.payments.filter(
                status='CONFIRMED',
                is_reversed=False
            ).order_by('payment_date', 'created_at')

            for payment in all_payments:
                amount = Decimal(payment.amount)
                deposit_portion = payment.deposit_portion
                interest_portion = payment.interest_applied
                principal_portion = payment.principal_applied
                remaining = amount - deposit_portion - interest_portion - principal_portion

                # Create deposit payment
                if deposit_portion > 0:
                    deposit_payment_data = {
                        'customer_ref': customer_ref,
                        'invoice_ref': invoice_id,
                        'total_amount': float(deposit_portion),
                        'principal_amount': float(deposit_portion),
                        'interest_amount': 0.0,
                        'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                        'PaymentRefNum': payment.receipt_number + '-DEP',
                    }
                    service.create_payment(deposit_payment_data)

                # Create sales receipt for interest
                if interest_portion > 0:
                    interest_receipt_data = {
                        'customer_ref': customer_ref,
                        'total_amount': float(interest_portion),
                        'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                        'PaymentRefNum': f"PY-{payment.receipt_number[3:]}-INT",
                    }
                    service.create_sales_receipt(interest_receipt_data)

                # Create principal payment
                if principal_portion > 0:
                    principal_payment_data = {
                        'customer_ref': customer_ref,
                        'invoice_ref': invoice_id,
                        'total_amount': float(principal_portion),
                        'principal_amount': float(principal_portion),
                        'interest_amount': 0.0,
                        'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                        'PaymentRefNum': payment.receipt_number + '-PRIN',
                    }
                    payment_result = service.create_payment(principal_payment_data)
                    payment.quickbooks_payment_id = payment_result['Payment']['Id']
                    payment.save()

                # Create extra principal payment
                if remaining > 0:
                    extra_principal_data = {
                        'customer_ref': customer_ref,
                        'invoice_ref': invoice_id,
                        'total_amount': float(remaining),
                        'principal_amount': float(remaining),
                        'interest_amount': 0.0,
                        'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                        'PaymentRefNum': payment.receipt_number + '-EXTRAPRIN',
                    }
                    payment_result = service.create_payment(extra_principal_data)
                    payment.quickbooks_payment_id = payment_result['Payment']['Id']
                    payment.save()

            # 4. Update loan with QuickBooks IDs
            loan.quickbooks_customer_id = customer_ref
            loan.quickbooks_invoice_id = invoice_id
            loan.quickbooks_synced_at = timezone.now()
            loan.save()

            # 5. Log success
            QuickBooksSyncLog.objects.create(
                action='CREATE_INVOICE',
                loan=loan,
                quickbooks_id=invoice_id,
                data_sent={
                    'customer_ref': customer_ref,
                    'invoice_amount': float(invoice_data['amount']),
                    'deposit_paid': float(loan.deposit_paid) if loan.deposit_paid else 0,
                    'installment_count': all_payments.count(),
                },
                response_data=invoice_result,
                status='SUCCESS',
                synced_at=timezone.now()
            )

            successful += 1

        except Exception as e:
            # Log failure
            QuickBooksSyncLog.objects.create(
                action='CREATE_INVOICE',
                loan=loan,
                data_sent={},
                status='FAILED',
                error_message=str(e)
            )
            failed += 1

    messages.success(request, f"Synced {successful} loans to QuickBooks. {failed} failed.")
    return redirect('sync_dashboard')

##################################################################################################################################################################################

@staff_member_required
@login_required
def sync_loan_to_quickbookswork(request, loan_id):
    """
    NEW CLEAN VERSION:
    - One invoice per loan (principal + deposit)
    - Reads allocation from payment records
    - Splits each payment: Deposit → Interest → Principal
    """
    from decimal import Decimal

    try:
        loan = LoanProduct.objects.get(id=loan_id)

        if loan.quickbooks_customer_id and not request.GET.get('force'):
            messages.warning(request, f"Loan {loan.loan_id} is already synced to QuickBooks. Use ?force=1 to resync.")
            return redirect('staff_loan_detail', loan_id=loan.id)

        if not QuickBooksToken.objects.filter(user=request.user).exists():
            messages.error(request, "Please connect to QuickBooks first.")
            return redirect('connect_quickbooks')

        service = QuickBooksPushService(request.user)

        customer_data = {
            'email': loan.customer.email if loan.customer else '',
            'first_name': loan.customer.first_name if loan.customer else '',
            'last_name': loan.customer.last_name if loan.customer else '',
            'display_name': loan.customer.get_full_name() if loan.customer else f"Loan #{loan.id}",
            'phone': getattr(loan.customer, 'phone', ''),
            'customer_id': loan.customer.customer_id if loan.customer else '',
        }
        customer_result = service.create_customer(customer_data)
        customer_ref = customer_result['Customer']['Id']

        if loan.application and loan.application.Financed_Amt and loan.application.Deposit:
            invoice_amount = float(loan.application.Financed_Amt + loan.application.Deposit)
        else:
            invoice_amount = float(loan.principal_amount + loan.deposit_paid)

        invoice_data = {
            'doc_number': f"LOAN-{loan.loan_id}",
            'customer_ref': customer_ref,
            'amount': invoice_amount,
            'description': f"HP Loan {loan.loan_id} - {loan.tenure_months} months @ {loan.interest_rate}%",
            'due_date': loan.first_payment_date.strftime('%Y-%m-%d') if loan.first_payment_date else None,
            'txn_date': loan.start_date.strftime('%Y-%m-%d') if loan.start_date else None,
            'invoice_id': str(loan.id),
            'loan_id': loan.loan_id,
        }
        invoice_result = service.create_invoice(invoice_data)
        invoice_id = invoice_result['Invoice']['Id']
        loan.quickbooks_invoice_id = invoice_result['Invoice']['Id']

        # ==========================================
        # PROCESS ALL PAYMENTS (READ FROM ALLOCATION FIELDS)
        # ==========================================
        all_payments = loan.payments.filter(
            status='CONFIRMED',
            is_reversed=False
        ).order_by('payment_date', 'created_at')

        for payment in all_payments:
            amount = Decimal(payment.amount)

            # ✅ Use the payment fields directly
            deposit_portion = payment.deposit_portion
            interest_portion = payment.interest_applied
            principal_portion = payment.principal_applied

            # If there's any remaining (shouldn't be, but just in case)
            remaining = amount - deposit_portion - interest_portion - principal_portion

            # Create deposit payment
            if deposit_portion > 0:
                deposit_payment_data = {
                    'customer_ref': customer_ref,
                    'invoice_ref': invoice_id,
                    'total_amount': float(deposit_portion),
                    'principal_amount': float(deposit_portion),
                    'interest_amount': 0.0,
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                    'PaymentRefNum': payment.receipt_number + '-DEP',
                }
                service.create_payment(deposit_payment_data)

            # Create sales receipt for interest
            if interest_portion > 0:
                interest_receipt_data = {
                    'customer_ref': customer_ref,
                    'total_amount': float(interest_portion),
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                    'PaymentRefNum': f"PY-{payment.receipt_number[3:]}-INT",
                }
                service.create_sales_receipt(interest_receipt_data)

            # Create principal payment
            if principal_portion > 0:
                principal_payment_data = {
                    'customer_ref': customer_ref,
                    'invoice_ref': invoice_id,
                    'total_amount': float(principal_portion),
                    'principal_amount': float(principal_portion),
                    'interest_amount': 0.0,
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                    'PaymentRefNum': payment.receipt_number + '-PRIN',
                }
                payment_result = service.create_payment(principal_payment_data)
                payment.quickbooks_payment_id = payment_result['Payment']['Id']
                payment.save()

            # Create extra principal payment (if any remaining)
            if remaining > 0:
                extra_principal_data = {
                    'customer_ref': customer_ref,
                    'invoice_ref': invoice_id,
                    'total_amount': float(remaining),
                    'principal_amount': float(remaining),
                    'interest_amount': 0.0,
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                    'PaymentRefNum': payment.receipt_number + '-EXTRAPRIN',
                }
                payment_result = service.create_payment(extra_principal_data)
                payment.quickbooks_payment_id = payment_result['Payment']['Id']
                payment.save()

        loan.quickbooks_customer_id = customer_ref
        loan.quickbooks_invoice_id = invoice_id
        loan.quickbooks_synced_at = timezone.now()
        loan.save()

        QuickBooksSyncLog.objects.create(
            action='CREATE_INVOICE',
            loan=loan,
            quickbooks_id=invoice_id,
            data_sent={
                'customer_ref': customer_ref,
                'invoice_amount': float(invoice_data['amount']),
                'deposit_paid': float(loan.deposit_paid) if loan.deposit_paid else 0,
                'installment_count': all_payments.count(),
            },
            response_data=invoice_result,
            status='SUCCESS',
            synced_at=timezone.now()
        )

        messages.success(
            request,
            f"✅ Loan {loan.loan_id} synced to QuickBooks!\n"
            f"Customer ID: {customer_ref}\n"
            f"Invoice ID: {invoice_id}\n"
            f"Amount: ${invoice_amount:,.2f}\n"
            f"Payments applied: {all_payments.count()}"
        )

        return redirect('staff_loan_detail', loan_id=loan.id)

    except Exception as e:
        logger.error(f"❌ Error syncing loan #{loan_id}: {str(e)}")
        messages.error(request, f"Failed to sync loan: {str(e)}")
        return redirect('staff_loan_detail', loan_id=loan.id)
# quickbooks/views.py - Add this view

# quickbooks/views.py - Update your connection_status view


@staff_member_required
@login_required
def sync_loan_to_quickbooks(request, loan_id):
    """
    Sync loan to QuickBooks with correct payment hierarchy:
    1. Fees (fees_applied) → 2. Interest (interest_applied) → 3. Principal (principal_applied)
    All principal-related amounts (deposit + principal + extra) go to ONE payment with -PRIN suffix.
    """
    from decimal import Decimal

    try:
        loan = LoanProduct.objects.get(id=loan_id)

        if loan.quickbooks_customer_id and not request.GET.get('force'):
            messages.warning(request, f"Loan {loan.loan_id} is already synced to QuickBooks. Use ?force=1 to resync.")
            return redirect('staff_loan_detail', loan_id=loan.id)

        if not QuickBooksToken.objects.filter(user=request.user).exists():
            messages.error(request, "Please connect to QuickBooks first.")
            return redirect('connect_quickbooks')

        service = QuickBooksPushService(request.user)

        # Get customer_id
        customer_id = ''
        if loan.customer:
            customer_id = getattr(loan.customer, 'customer_id', '') or str(loan.customer.id)

        customer_data = {
            'email': loan.customer.email if loan.customer else '',
            'first_name': loan.customer.first_name if loan.customer else '',
            'last_name': loan.customer.last_name if loan.customer else '',
            'display_name': loan.customer.get_full_name() if loan.customer else f"Loan #{loan.id}",
            'phone': getattr(loan.customer, 'phone', ''),
            'customer_id': customer_id,
        }
        customer_result = service.create_customer(customer_data)
        customer_ref = customer_result['Customer']['Id']

        # Calculate invoice amount
        if loan.application and loan.application.Financed_Amt and loan.application.Deposit:
            invoice_amount = float(loan.application.Financed_Amt + loan.application.Deposit)
        else:
            invoice_amount = float(loan.principal_amount + loan.deposit_paid)

        invoice_data = {
            'doc_number': f"LOAN-{loan.loan_id}",
            'customer_ref': customer_ref,
            'amount': invoice_amount,
            'description': f"HP Loan {loan.loan_id} - {loan.tenure_months} months @ {loan.interest_rate}%",
            'due_date': loan.first_payment_date.strftime('%Y-%m-%d') if loan.first_payment_date else None,
            'txn_date': loan.start_date.strftime('%Y-%m-%d') if loan.start_date else None,
            'invoice_id': str(loan.id),
            'loan_id': loan.loan_id,
        }
        invoice_result = service.create_invoice(invoice_data)
        invoice_id = invoice_result['Invoice']['Id']
        loan.quickbooks_invoice_id = invoice_id

        # ==========================================
        # PROCESS ALL PAYMENTS
        # ==========================================
        all_payments = loan.payments.filter(
            status='CONFIRMED',
            is_reversed=False
        ).order_by('payment_date', 'created_at')

        interest_counter = {}

        for payment in all_payments:
            amount = Decimal(payment.amount)

            # Get allocations
            deposit_portion = payment.deposit_portion or 0
            fees_portion = payment.fees_applied or 0
            interest_portion = payment.interest_applied or 0
            principal_portion = payment.principal_applied or 0

            # Get base receipt number (shorten if needed for QuickBooks)
            receipt_number = payment.receipt_number or f"PY-{payment.id}"
            if receipt_number.startswith('PY-'):
                receipt_base = receipt_number[3:]
            else:
                receipt_base = str(receipt_number)

            # Keep receipt base under 15 chars to fit with -PRIN or -INT01
            if len(receipt_base) > 15:
                receipt_base = receipt_base[:15]

            # Get installment number
            schedule = PaymentSchedule.objects.filter(payment_reference=payment).first()
            installment_number = schedule.installment_number if schedule else list(all_payments).index(payment) + 1

            # ==========================================
            # 1. FEES (if any)
            # ==========================================
            if fees_portion > 0:
                fee_payment_data = {
                    'customer_ref': customer_ref,
                    'invoice_ref': invoice_id,
                    'total_amount': float(fees_portion),
                    'principal_amount': 0.0,
                    'interest_amount': 0.0,
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                    'PaymentRefNum': f"{receipt_base}-FEE",
                    'memo': f"Fee payment for Payment #{installment_number}",
                }
                service.create_payment(fee_payment_data)

            # ==========================================
            # 2. INTEREST (Sales Receipt)
            # ==========================================
            if interest_portion > 0:
                if receipt_base not in interest_counter:
                    interest_counter[receipt_base] = 0
                interest_counter[receipt_base] += 1
                int_suffix = f"INT{interest_counter[receipt_base]:02d}"

                interest_receipt_data = {
                    'customer_ref': customer_ref,
                    'total_amount': float(interest_portion),
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                    'PaymentRefNum': f"{receipt_base}-{int_suffix}",
                    'memo': f"Interest payment for Payment #{installment_number} (Part {interest_counter[receipt_base]} of partial)",
                }
                service.create_sales_receipt(interest_receipt_data)

            # ==========================================
            # 3. PRINCIPAL (Combined: deposit + principal + remaining)
            # ==========================================
            # Calculate remaining after all allocations
            total_applied = deposit_portion + fees_portion + interest_portion + principal_portion
            remaining = amount - total_applied

            # Combine everything that reduces principal
            total_principal = deposit_portion + principal_portion + remaining

            if total_principal > 0:
                memo_parts = [f"Principal: ${principal_portion:,.2f}"]
                if deposit_portion > 0:
                    memo_parts.insert(0, f"Deposit: ${deposit_portion:,.2f}")
                if remaining > 0:
                    memo_parts.append(f"Extra: ${remaining:,.2f}")

                principal_payment_data = {
                    'customer_ref': customer_ref,
                    'invoice_ref': invoice_id,
                    'total_amount': float(total_principal),
                    'principal_amount': float(total_principal),
                    'interest_amount': 0.0,
                    'payment_date': payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
                    'PaymentRefNum': f"{receipt_base}-PRIN",  # ✅ Single PRIN payment
                    'memo': f"Payment #{installment_number}: {' + '.join(memo_parts)}",
                }
                payment_result = service.create_payment(principal_payment_data)
                payment.quickbooks_payment_id = payment_result['Payment']['Id']
                payment.save()

        # Update loan
        loan.quickbooks_customer_id = customer_ref
        loan.quickbooks_invoice_id = invoice_id
        loan.quickbooks_synced_at = timezone.now()
        loan.save()

        QuickBooksSyncLog.objects.create(
            action='CREATE_INVOICE',
            loan=loan,
            quickbooks_id=invoice_id,
            data_sent={
                'customer_ref': customer_ref,
                'invoice_amount': float(invoice_data['amount']),
                'deposit_paid': float(loan.deposit_paid) if loan.deposit_paid else 0,
                'installment_count': all_payments.count(),
            },
            response_data=invoice_result,
            status='SUCCESS',
            synced_at=timezone.now()
        )

        messages.success(
            request,
            f"✅ Loan {loan.loan_id} synced to QuickBooks!\n"
            f"Customer ID: {customer_ref}\n"
            f"Invoice ID: {invoice_id}\n"
            f"Amount: ${invoice_amount:,.2f}\n"
            f"Payments applied: {all_payments.count()}"
        )

        return redirect('staff_loan_detail', loan_id=loan.id)

    except Exception as e:
        logger.error(f"❌ Error syncing loan #{loan_id}: {str(e)}")
        messages.error(request, f"Failed to sync loan: {str(e)}")
        return redirect('staff_loan_detail', loan_id=loan.id)

#####################################################################################################################################################################################################################
@login_required
def connection_status(request):
    """Check and display QuickBooks connection status"""

    try:
        token = QuickBooksToken.objects.get(user=request.user)
        is_connected = True

        # Check if token is expired
        is_expired = token.is_expired()

        # Calculate time until expiry
        if not is_expired:
            time_until_expiry = token.expires_at - timezone.now()
            hours_until_expiry = int(time_until_expiry.total_seconds() // 3600)
            minutes_until_expiry = int((time_until_expiry.total_seconds() % 3600) // 60)
        else:
            hours_until_expiry = 0
            minutes_until_expiry = 0

        # Get sync statistics
        sync_logs = QuickBooksSyncLog.objects.all()
        total_syncs = sync_logs.count()
        successful = sync_logs.filter(status='SUCCESS').count()
        failed = sync_logs.filter(status='FAILED').count()
        pending = sync_logs.filter(status='PENDING').count()

        context = {
            'is_connected': True,
            'realm_id': token.realm_id,
            'expires_at': token.expires_at,
            'is_expired': is_expired,
            'created_at': token.created_at,
            'updated_at': token.updated_at,
            'hours_until_expiry': hours_until_expiry,
            'minutes_until_expiry': minutes_until_expiry,
            'total_syncs': total_syncs,
            'successful': successful,
            'failed': failed,
            'pending': pending,
            # Token previews for debugging
            'access_token_preview': token.access_token[:20] + '...' if token.access_token else 'N/A',
            'refresh_token_preview': token.refresh_token[:20] + '...' if token.refresh_token else 'N/A',
            'debug': settings.DEBUG,  # Only show debug info in development
        }

    except QuickBooksToken.DoesNotExist:
        context = {
            'is_connected': False,
            'total_syncs': 0,
            'successful': 0,
            'failed': 0,
            'pending': 0,
        }

    return render(request, 'quickbooks/status.html', context)

@login_required
def verify_loan_sync(request, loan_id):
    """Verify if a loan is properly synced to QuickBooks"""

    loan = get_object_or_404(LoanProduct, id=loan_id)

    # Security: Check access
    if request.user != loan.customer and not request.user.is_staff:
        messages.error(request, "You don't have permission to verify this loan.")
        return redirect('staff_loan_detail', loan_id=loan.id)

    # Check if connected
    if not QuickBooksToken.objects.filter(user=request.user).exists():
        messages.error(request, "Not connected to QuickBooks. Please connect first.")
        return redirect('connect_quickbooks')

    try:
        service = QuickBooksPushService(request.user)
        verification = service.verify_loan_sync(loan)

        # Log the verification
        from quickbooks.models import QuickBooksSyncLog
        QuickBooksSyncLog.objects.create(
            action='VERIFY_SYNC',
            loan=loan,
            data_sent={
                'loan_id': loan.id,
                'customer_id': loan.quickbooks_customer_id,
                'invoice_id': loan.quickbooks_invoice_id
            },
            response_data=verification,
            status='SUCCESS' if verification['verified'] else 'FAILED',
            synced_at=timezone.now()
        )

        context = {
            'loan': loan,
            'verification': verification,
            'is_connected': True,
        }

        return render(request, 'quickbooks/verify_sync.html', context)

    except Exception as e:
        logger.error(f"Verification failed for loan {loan.loan_id}: {str(e)}")
        messages.error(request, f"Failed to verify sync: {str(e)}")
        return redirect('staff_loan_detail', loan_id=loan.id)



###########################################################################################################################################################################
@login_required
def quickbooks_comparison1(request):
    """Display QuickBooks data for comparison - filtered by Django customers"""


    # Check if connected
    if not QuickBooksToken.objects.filter(user=request.user).exists():
        messages.error(request, "Not connected to QuickBooks. Please connect first.")
        return redirect('connect_quickbooks')

    try:
        service = QuickBooksPushService(request.user)

        # Get search query
        search_query = request.GET.get('search', '').strip()

        # Get all Django customer emails
        User = get_user_model()
        django_customer_emails = set(
            user.email.lower() for user in User.objects.filter(role='customer') if user.email
        )

        # Fetch all customers from QuickBooks
        all_customers = service.get_all_customers()

        # Filter to only Django customers
        customers = [
            c for c in all_customers
            if c.get('PrimaryEmailAddr', {}).get('Address', '').lower() in django_customer_emails
        ]

        # Apply search filter to customers
        if search_query:
            customers = [
                c for c in customers
                if search_query.lower() in c.get('DisplayName', '').lower()
                or search_query.lower() in c.get('PrimaryEmailAddr', {}).get('Address', '').lower()
            ]

        # Get the QuickBooks customer IDs we care about
        customer_ids = [c['Id'] for c in customers]

        # Fetch all invoices and payments
        all_invoices = service.get_all_invoices()
        all_payments = service.get_all_payments()

        # Filter invoices to only those customers
        invoices = [
            i for i in all_invoices
            if i.get('CustomerRef', {}).get('value') in customer_ids
        ]

        # Filter payments to only those customers
        payments = [
            p for p in all_payments
            if p.get('CustomerRef', {}).get('value') in customer_ids
        ]

        # Get all Django loans
        loans = LoanProduct.objects.all()

        context = {
            'quickbooks_customers': customers,
            'quickbooks_invoices': invoices,
            'quickbooks_payments': payments,
            'loans': loans,
            'search_query': search_query,
            'is_connected': True,
        }

        return render(request, 'quickbooks/comparison.html', context)

    except Exception as e:
        messages.error(request, f"Failed to fetch QuickBooks data: {str(e)}")
        return redirect('sync_dashboard')


# quickbooks/views.py - Add this improved comparison view

# quickbooks/views.py - Fixed comparison view

# quickbooks/views.py - Updated comparison view

# quickbooks/views.py - Updated comparison view

# quickbooks/views.py - Updated comparison using application fields

# quickbooks/views.py - Full quickbooks_comparison view with the fix

# quickbooks/views.py - Updated comparison view using model properties

@login_required
def quickbooks_comparison(request):
    """
    Display QuickBooks data comparison with Django loans.
    Uses model properties for accurate deposit calculation.
    """
    from django.core.paginator import Paginator
    from django.db.models import Q
    from decimal import Decimal
    import re

    # Check connection
    if not QuickBooksToken.objects.filter(user=request.user).exists():
        messages.error(request, "Not connected to QuickBooks. Please connect first.")
        return redirect('connect_quickbooks')

    # Get parameters
    search_query = request.GET.get('search', '').strip()
    show_mismatches = request.GET.get('show_mismatches', '') == 'on'
    compare = request.GET.get('compare', '') == 'true'
    page = request.GET.get('page', 1)

    # Initialize variables
    show_data = False
    quickbooks_customers = []
    quickbooks_invoices = []
    quickbooks_payments = []
    loans = []
    mismatches = []
    mismatches_count = 0
    is_connected = True

    # Only fetch data if search or compare is triggered
    if search_query or compare:
        show_data = True

        try:
            service = QuickBooksPushService(request.user)

            # Get Django customers
            User = get_user_model()
            django_customers = {}
            for user in User.objects.filter(role='customer'):
                if user.email:
                    customer_id = getattr(user, 'customer_id', None)
                    django_customers[user.email.lower()] = {
                        'user': user,
                        'id': user.id,
                        'customer_id': customer_id,
                        'full_name': user.get_full_name(),
                        'email': user.email
                    }

            django_customer_emails = set(django_customers.keys())

            # Fetch customers from QuickBooks
            all_customers = service.get_all_customers()

            customers = []
            for c in all_customers:
                customer_email = c.get('PrimaryEmailAddr', {}).get('Address', '').lower()
                if customer_email in django_customer_emails:
                    display_name = c.get('DisplayName', '')
                    extracted_id = None
                    match = re.search(r'\(([^)]+)\)$', display_name)
                    if match:
                        extracted_id = match.group(1)

                    c['extracted_customer_id'] = extracted_id
                    c['django_customer'] = django_customers[customer_email]
                    customers.append(c)

            # Apply search filter
            if search_query:
                customers = [
                    c for c in customers
                    if search_query.lower() in c.get('DisplayName', '').lower()
                    or search_query.lower() in c.get('PrimaryEmailAddr', {}).get('Address', '').lower()
                    or (c.get('extracted_customer_id') and search_query in c['extracted_customer_id'])
                ]

            customer_ids = [c['Id'] for c in customers]

            # Get loans with applications and payments prefetched
            loans_qs = LoanProduct.objects.select_related(
                'application',
                'customer'
            ).prefetch_related(
                'payments'
            ).all()

            if search_query:
                loans_qs = loans_qs.filter(
                    Q(loan_id__icontains=search_query) |
                    Q(customer__first_name__icontains=search_query) |
                    Q(customer__last_name__icontains=search_query) |
                    Q(customer__email__icontains=search_query) |
                    Q(customer__customer_id__icontains=search_query)
                )
            loans = list(loans_qs)

            loan_by_id = {str(loan.id): loan for loan in loans}
            loan_by_loan_id = {loan.loan_id: loan for loan in loans}

            # Map customer_id to loan
            customer_id_to_loan = {}
            for loan in loans:
                if loan.customer:
                    customer_id = getattr(loan.customer, 'customer_id', None)
                    if customer_id:
                        customer_id_to_loan[customer_id] = loan
                    if loan.customer.email:
                        customer_id_to_loan[loan.customer.email.lower()] = loan

            # Fetch invoices and payments from QuickBooks
            all_invoices = service.get_all_invoices()
            all_payments = service.get_all_payments()
            all_sales_receipts = service.get_all_sales_receipts()

            quickbooks_invoices = [
                i for i in all_invoices
                if i.get('CustomerRef', {}).get('value') in customer_ids
            ]

            quickbooks_sales_receipts = [
                r for r in all_sales_receipts
                if r.get('CustomerRef', {}).get('value') in customer_ids
            ]

            quickbooks_payments = [
                p for p in all_payments
                if p.get('CustomerRef', {}).get('value') in customer_ids
            ]

            # ============================================
            # COMPARISON LOGIC
            # ============================================

            # 1. Check customers
            customer_mismatches = []
            for customer in customers:
                customer['mismatch'] = False
                extracted_id = customer.get('extracted_customer_id')
                django_customer = customer.get('django_customer')

                if not extracted_id:
                    customer['mismatch'] = True
                    customer_mismatches.append(
                        f"Customer {customer.get('DisplayName')} missing ID in DisplayName"
                    )
                elif django_customer:
                    django_customer_id = django_customer.get('customer_id')
                    if django_customer_id and extracted_id != django_customer_id:
                        customer['mismatch'] = True
                        customer_mismatches.append(
                            f"Customer {customer.get('DisplayName')} has ID '{extracted_id}' "
                            f"but expected '{django_customer_id}'"
                        )

            # 2. Check invoices - Using model properties
            invoice_mismatches = []
            for invoice in quickbooks_invoices:
                invoice['mismatch'] = False

                doc_number = invoice.get('DocNumber', '')
                loan_id_match = re.search(r'LOAN-(.+)', doc_number)
                loan_id = loan_id_match.group(1) if loan_id_match else None

                if loan_id and loan_id in loan_by_loan_id:
                    loan = loan_by_loan_id[loan_id]
                    qb_amount = float(invoice.get('TotalAmt', 0))

                    # ✅ Use the model properties
                    expected_amount = float(loan.total_loan_amount_from_payments)

                    # Get breakdown for display
                    if loan.application:
                        financed_amount = float(loan.application.Financed_Amt or 0)
                    else:
                        financed_amount = float(loan.principal_amount or 0)

                    total_deposit = float(loan.total_deposit_from_payments)
                    payments_count = loan.payments.filter(
                        status='CONFIRMED',
                        is_reversed=False
                    ).count()

                    if abs(qb_amount - expected_amount) <= 0.01:
                        # Match found!
                        invoice['matched'] = True
                        invoice['financed_amount'] = financed_amount
                        invoice['total_deposit'] = total_deposit
                        invoice['payment_count'] = payments_count
                    else:
                        invoice['mismatch'] = True

                        # Build detailed mismatch message
                        mismatch_detail = (
                            f"Invoice {doc_number} amount mismatch:\n"
                            f"  QB Amount: ${qb_amount:,.2f}\n"
                            f"  Django Total: ${expected_amount:,.2f}\n"
                            f"    Financed: ${financed_amount:,.2f}\n"
                            f"    Total Deposit from {payments_count} payments: ${total_deposit:,.2f}\n"
                        )

                        # Show deposit breakdown
                        deposit_breakdown = loan.total_deposit_breakdown
                        if deposit_breakdown:
                            mismatch_detail += "  Deposit breakdown:\n"
                            for dep in deposit_breakdown[:5]:
                                date_str = dep['date'].strftime('%Y-%m-%d') if dep['date'] else 'Unknown'
                                mismatch_detail += (
                                    f"    - {date_str}: "
                                    f"${dep['amount']:,.2f} (Receipt: {dep['receipt']})\n"
                                )
                            if len(deposit_breakdown) > 5:
                                mismatch_detail += f"    ... and {len(deposit_breakdown) - 5} more\n"

                        # Check if application deposit_paid field exists and differs
                        if loan.application and loan.application.deposit_paid:
                            app_deposit = float(loan.application.deposit_paid)
                            if abs(app_deposit - total_deposit) > 0.01:
                                mismatch_detail += (
                                    f"  Note: Application deposit_paid field is ${app_deposit:,.2f} "
                                    f"(different from total deposit from payments)\n"
                                )

                        invoice_mismatches.append(mismatch_detail)

                else:
                    # Try to find loan by customer
                    customer_ref = invoice.get('CustomerRef', {}).get('value')
                    matching_customer = next((c for c in customers if c.get('Id') == customer_ref), None)

                    if matching_customer:
                        django_customer = matching_customer.get('django_customer')
                        if django_customer:
                            customer_id = django_customer.get('customer_id')
                            found_loan = customer_id_to_loan.get(customer_id)

                            if found_loan:
                                # Check amount using model properties
                                qb_amount = float(invoice.get('TotalAmt', 0))
                                expected_amount = float(found_loan.total_loan_amount_from_payments)

                                if abs(qb_amount - expected_amount) > 0.01:
                                    invoice['mismatch'] = True
                                    invoice_mismatches.append(
                                        f"Invoice {doc_number} amount mismatch for loan {found_loan.loan_id}: "
                                        f"QB ${qb_amount:,.2f} vs Django ${expected_amount:,.2f}"
                                    )
                            else:
                                invoice['mismatch'] = True
                                invoice_mismatches.append(
                                    f"Invoice {doc_number} has no matching loan (Customer ID: {customer_id})"
                                )
                    else:
                        invoice['mismatch'] = True
                        invoice_mismatches.append(
                            f"Invoice {doc_number} has no matching loan in Django"
                        )

            # 3. Check payments
            payment_mismatches = []
            for payment in quickbooks_payments:
                payment['mismatch'] = False

                linked_txn = payment.get('Line', [{}])[0].get('LinkedTxn', [{}])[0]
                invoice_ref = linked_txn.get('TxnId')

                if invoice_ref:
                    matching_invoice = next((i for i in quickbooks_invoices if i.get('Id') == invoice_ref), None)
                    if not matching_invoice:
                        payment['mismatch'] = True
                        payment_mismatches.append(
                            f"Payment {payment.get('PaymentRefNum')} references non-existent invoice {invoice_ref}"
                        )

            # 4. Check loans missing in QuickBooks
            loan_mismatches = []
            for loan in loans:
                has_qb_invoice = any(
                    i for i in quickbooks_invoices
                    if i.get('DocNumber', '') == f"LOAN-{loan.loan_id}"
                )
                if not has_qb_invoice and loan.status not in ['PAID_OFF', 'CLOSED', 'CANCELLED']:
                    loan_mismatches.append(
                        f"Loan {loan.loan_id} ({loan.customer.get_full_name() if loan.customer else 'No customer'}) has no invoice in QB"
                    )

            # Combine mismatches
            mismatches = customer_mismatches + invoice_mismatches + payment_mismatches + loan_mismatches
            mismatches_count = len(mismatches)

            # Filter to show only mismatches if checkbox checked
            if show_mismatches:
                customers = [c for c in customers if c.get('mismatch', False)]
                quickbooks_invoices = [i for i in quickbooks_invoices if i.get('mismatch', False)]
                quickbooks_payments = [p for p in quickbooks_payments if p.get('mismatch', False)]

                # Filter loans to those with mismatches
                mismatch_loan_ids = set()
                for loan in loans:
                    has_qb = any(
                        i for i in quickbooks_invoices
                        if i.get('DocNumber', '') == f"LOAN-{loan.loan_id}"
                    )
                    if not has_qb and loan.status not in ['PAID_OFF', 'CLOSED', 'CANCELLED']:
                        mismatch_loan_ids.add(loan.id)
                loans = [l for l in loans if l.id in mismatch_loan_ids]

            # Pagination for customers
            paginator = Paginator(customers, 20)
            quickbooks_customers = paginator.get_page(page)

            # Store QB match status on loans
            for loan in loans:
                loan.qb_match = any(
                    i for i in quickbooks_invoices
                    if i.get('DocNumber', '') == f"LOAN-{loan.loan_id}"
                )

        except Exception as e:
            logger.error(f"Failed to fetch QuickBooks data: {str(e)}")
            messages.error(request, f"Failed to fetch QuickBooks data: {str(e)}")
            show_data = False
            quickbooks_customers = []
            quickbooks_invoices = []
            quickbooks_payments = []
            loans = []
            mismatches = []
            mismatches_count = 0

    context = {
        'quickbooks_customers': quickbooks_customers,
        'quickbooks_invoices': quickbooks_invoices,
        'quickbooks_payments': quickbooks_payments,
        'quickbooks_sales_receipts': quickbooks_sales_receipts,
        'loans': loans,
        'search_query': search_query,
        'show_mismatches': show_mismatches,
        'mismatches': mismatches,
        'mismatches_count': mismatches_count,
        'show_data': show_data,
        'is_connected': is_connected,
        'compare_triggered': compare,
        'total_transactions': (len(quickbooks_invoices) + len(quickbooks_payments) + len(quickbooks_sales_receipts)
    ),
    }

    return render(request, 'quickbooks/comparison.html', context)