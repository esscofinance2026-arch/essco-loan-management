# poc/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
import requests  # ✅ ADD THIS
import logging  # ✅ ADD THIS

import time  # ✅ Add this for the unique name

from applications.models import ApplicationModel

# ✅ Add this line to create the logger
logger = logging.getLogger(__name__)


@login_required
def poc_dashboard(request):
    """POC Dashboard"""
    # Try to get existing application
    application = ApplicationModel.objects.filter(
        customer=request.user,
        Approval_Status__in=['Approved Pending', 'Human Approved']
    ).order_by('-created').first()

    if not application:
        # Create a test application using correct field names
        application = ApplicationModel.objects.create(
            customer=request.user,
            Fname="John",
            Lname="Doe",
            email="john@example.com",
            DOB="1990-01-01",
            Nationality="Barbadian",
            ID_number="123456789",
            Gender="Male",
            Marital_Status="Single",
            Num_Dependents=0,
            Parish="Christ Church",
            Address="123 Main Street",
            Length_at_Address=1,
            Residential_Status="Owner",
            Cell_Phone="+12465551234",
            Employer_Name="ABC Company",
            Employer_Address="456 Business Park",
            Employer_Type="Permanent",
            Job_Title="Manager",
            less_than_six="No",
            Employer_Num="+12465551234",
            Len_Employ="2 + Years",
            Gross_Monthly_Income=3000.00,
            Previous_Employer="Previous Company",
            # Financial Info (defaults)
            Loan_mortgages_payments=0,
            CCPayments=0,
            Other_Debt_Payments=0,
            Rent=500,
            Transportation=200,
            Insurance=150,
            Other_Living_Expenses=100,
            food=400,
            utilities=150,
            # References
            Reference1_FullName="Ref One",
            Reference1_Relationship="Friend",
            Reference1_Employer="Ref Company",
            Reference1_Job_Title="Manager",
            Reference1_Contact_Number="+12465551234",
            Reference1_Len_Time_Known=1,
            Reference1_Address="123 Ref Street",
            Reference2_FullName="Ref Two",
            Reference2_Relationship="Colleague",
            Reference2_Employer="Ref Company 2",
            Reference2_Job_Title="Supervisor",
            Reference2_Contact_Number="+12465551234",
            Reference2_Len_Time_Known=1,
            Reference2_Address="456 Ref Street",
            # Consent and files
            accept_terms=True,
            # Product info
            item_name="Test Product",
            item_sku="TEST-001",
            Purchase_Value=10000.00,
            # Calculated fields (will be auto-calculated on save)
            Total_Monthly_living_expenses=0,
            Total_Monthly_debt=0,
            Monthly_Obligations=0,
            Disposable_Income=0,
            Debt_To_Income_Ratio=0,
            Living_Expense_Ratio=0,
            Total_Debt_Service_Ratio=0,
            Approval_Status='Approved Pending',
            Total_Credit_Allowed=0,
            Deposit=0,
            Six=0,
            Twelve=0,
            Eighteen=0,
            Twenty_Four=0,
            Thirty=0,
            Thirty_Six=0,
            RR=0,
            NIS=0,
            PAYE=0,
            Gross_Monthly_Income_AT=0,
            Financed_Amt=0,
            Disposable_Income_After=0,
            notes="POC Test Application"
        )

    # Get the latest payment for this application
    latest_payment = None
    try:
        from payments.models import PaymentRecord
        latest_payment = PaymentRecord.objects.filter(
            application=application
        ).order_by('-created_at').first()
    except:
        pass

    # Get the loan if it exists
    loan = None
    try:
        from loans.models import LoanProduct
        loan = LoanProduct.objects.filter(application=application).first()
    except:
        pass

    # Check if deposit exists (look at the model fields)
    has_deposit = False
    if hasattr(application, 'deposit_paid'):
        has_deposit = application.deposit_paid > 0

    context = {
        'application': application,
        'has_deposit': has_deposit,
        'has_loan': loan is not None,
        'loan': loan,
        'is_synced': loan and hasattr(loan, 'quickbooks_customer_id') and loan.quickbooks_customer_id is not None,
        'latest_payment': latest_payment,
    }
    return render(request, 'poc/dashboard.html', context)


@login_required
def step1_pay_deposit(request, application_id):
    """Step 1: Pay Deposit"""
    application = get_object_or_404(ApplicationModel, id=application_id)

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 1000.00))

        # Create payment record
        try:
            from payments.models import PaymentRecord, PaymentMethod

            # Get or create payment method
            method, _ = PaymentMethod.objects.get_or_create(
                method_type='CASH',
                defaults={'name': 'Cash', 'requires_manual_confirmation': True}
            )

            # Create payment
            payment = PaymentRecord.objects.create(
                customer=request.user,
                application=application,
                recorded_by=request.user,
                category='DEPOSIT',
                amount=amount,
                payment_method=method,
                receipt_number=f"DEP-{timezone.now().strftime('%Y%m%d')}-{PaymentRecord.objects.count() + 1:06d}",
                status='CONFIRMED',  # Auto-confirm for POC
                confirmed_by=request.user,
                confirmed_at=timezone.now(),
                auto_create_loan=True,
                notes="POC Deposit - Auto-confirmed"
            )

            # Update application with deposit info
            application.deposit_paid = amount
            application.deposit_paid_date = timezone.now()
            application.deposit_status = 'PAID'
            application.deposit_receipt_number = payment.receipt_number
            application.save()

            messages.success(request, f"✅ Deposit of ${amount} paid and confirmed!")

            # Try to auto-create loan
            try:
                from loans.services.loan_creation_service import LoanCreationService
                loan = LoanCreationService.handle_deposit_confirmation(payment)
                if loan:
                    messages.success(request, f"🚀 Loan {loan.loan_id} was auto-created!")
                    return redirect('poc_step3_view_loan', loan_id=loan.id)
            except:
                pass

            return redirect('poc_step2_view_payment', payment_id=payment.id)

        except Exception as e:
            messages.error(request, f"Error processing payment: {str(e)}")

    # Calculate suggested deposit (10% of purchase value)
    suggested_deposit = application.Purchase_Value * Decimal('0.10')

    context = {
        'application': application,
        'suggested_deposit': suggested_deposit,
    }
    return render(request, 'poc/step1_pay_deposit.html', context)


@login_required
def step2_view_payment(request, payment_id):
    """Step 2: View Payment"""
    from payments.models import PaymentRecord

    payment = get_object_or_404(PaymentRecord, id=payment_id)
    application = payment.application
    loan = payment.loan if hasattr(payment, 'loan') and payment.loan else None

    # If loan wasn't auto-created, try to create it now
    if not loan and application and payment.status == 'CONFIRMED':
        try:
            from loans.services.loan_creation_service import LoanCreationService
            loan = LoanCreationService.handle_deposit_confirmation(payment)
        except Exception as e:
            messages.warning(request, f"Loan auto-creation failed: {str(e)}")

    context = {
        'payment': payment,
        'application': application,
        'loan': loan,
    }
    return render(request, 'poc/step2_view_payment.html', context)


@login_required
def step3_view_loan(request, loan_id):
    """Step 3: View Loan"""
    from loans.models import LoanProduct

    loan = get_object_or_404(LoanProduct, id=loan_id)

    context = {
        'loan': loan,
        'payment_schedule': loan.payment_schedule.all()[:5] if hasattr(loan, 'payment_schedule') else [],
        'total_installments': loan.payment_schedule.count() if hasattr(loan, 'payment_schedule') else 0,
        'deposit_info': loan.get_complete_deposit_record() if hasattr(loan, 'get_complete_deposit_record') else {},
        'is_synced': hasattr(loan, 'quickbooks_customer_id') and loan.quickbooks_customer_id is not None,
    }
    return render(request, 'poc/step3_view_loan.html', context)


# poc/views.py - Update step4_push_quickbooks

@login_required
def step4_push_quickbooks(request, loan_id):
    """Step 4: Push to QuickBooks"""
    import time  # ✅ Add this import at the top of the file
    logger.info(f"🚀 STEP 4 VIEW CALLED for loan {loan_id}")
    logger.info(f"   Method: {request.method}")

    from loans.models import LoanProduct
    loan = get_object_or_404(LoanProduct, id=loan_id)

    # Get customer info
    customer_name = "Unknown Customer"
    customer_email = "noemail@example.com"

    if loan.customer:
        customer_name = loan.customer.get_full_name() or loan.customer.username or "Customer"
        customer_email = loan.customer.email or "noemail@example.com"
    elif loan.application:
        customer_name = f"{loan.application.Fname} {loan.application.Lname}"
        customer_email = loan.application.email or "noemail@example.com"

    logger.info(f"   Customer: {customer_name}")
    logger.info(f"   Email: {customer_email}")

    if request.method == 'POST':
        logger.info("   ✅ POST request received - processing...")

        try:
            from quickbooks.services import QuickBooksPushService

            # Check if already synced
            if loan.quickbooks_customer_id:
                logger.warning("   ⚠️ Loan already synced")
                messages.warning(request, "This loan is already synced to QuickBooks")
                return redirect('poc_step3_view_loan', loan_id=loan.id)

            qb_service = QuickBooksPushService(request.user)

            # ============================================================
            # STEP 1: Create Customer with UNIQUE name
            # ============================================================
            logger.info("   📤 Creating QuickBooks customer...")

            first_name = customer_name.split()[0] if customer_name and ' ' in customer_name else customer_name
            last_name = ' '.join(customer_name.split()[1:]) if customer_name and ' ' in customer_name else 'Customer'

            # Get phone from application
            phone = ''
            if loan.application and hasattr(loan.application, 'Cell_Phone'):
                phone = loan.application.Cell_Phone or ''

            # ✅ Generate a unique name to avoid duplicate errors
            unique_name = f"{customer_name}_{int(time.time())}"

            customer_data = {
                'display_name': unique_name,  # Use unique name
                'first_name': first_name or 'Test',
                'last_name': last_name or 'Customer',
                'email': customer_email or 'noemail@example.com',
                'phone': phone or '246-555-0000',
            }

            logger.info(f"   Customer data: {customer_data}")

            customer = qb_service.create_customer(customer_data)
            customer_id = customer.get('Customer', {}).get('Id')

            if not customer_id:
                raise ValueError("Failed to create customer in QuickBooks")

            logger.info(f"   ✅ Customer created: {customer_id}")

            # ============================================================
            # STEP 2: Create Invoice
            # ============================================================
            logger.info("   📤 Creating QuickBooks invoice...")

            invoice_data = {
                'customer_ref': customer_id,
                'amount': float(loan.principal_amount),
                'description': f'HP Loan {loan.loan_id} - {loan.tenure_months} months @ {loan.interest_rate}%',
                'due_date': loan.first_payment_date.strftime('%Y-%m-%d') if loan.first_payment_date else None,
                'txn_date': loan.start_date.strftime('%Y-%m-%d') if loan.start_date else None,
            }

            invoice = qb_service.create_invoice(invoice_data)
            invoice_id = invoice.get('Invoice', {}).get('Id')

            if not invoice_id:
                raise ValueError("Failed to create invoice in QuickBooks")

            logger.info(f"   ✅ Invoice created: {invoice_id}")

            # ============================================================
            # STEP 3: Apply Deposit as Payment
            # ============================================================
            if loan.deposit_paid > 0:
                logger.info(f"   📤 Creating QuickBooks payment for ${loan.deposit_paid}...")

                payment_data = {
                    'customer_ref': customer_id,
                    'invoice_ref': invoice_id,
                    'amount': float(loan.deposit_paid),
                    'payment_date': loan.deposit_paid_date.strftime('%Y-%m-%d') if loan.deposit_paid_date else None,
                    'receipt_number': loan.deposit_receipt_number or f'DEP-{loan.loan_id}',
                    'memo': f'Deposit for {loan.loan_id} (Receipt: {loan.deposit_receipt_number or "N/A"})',
                }
                qb_service.create_payment(payment_data)
                logger.info(f"   ✅ Payment created: ${loan.deposit_paid}")

            # Update loan with QuickBooks IDs
            loan.quickbooks_customer_id = customer_id
            loan.quickbooks_invoice_id = invoice_id
            loan.quickbooks_synced_at = timezone.now()
            loan.save()

            logger.info("   🎉 QuickBooks sync complete!")

            messages.success(
                request,
                f"✅ Loan pushed to QuickBooks successfully!\n"
                f"Customer: {customer_name} (ID: {customer_id})\n"
                f"Invoice: ${loan.principal_amount:.2f} (ID: {invoice_id})"
            )

            return redirect('poc_step3_view_loan', loan_id=loan.id)

        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                if e.response:
                    error_data = e.response.json()
                    if 'Fault' in error_data:
                        fault = error_data['Fault']
                        if 'Error' in fault:
                            error_messages = []
                            for err in fault['Error']:
                                msg = err.get('Message', '')
                                detail = err.get('Detail', '')
                                error_messages.append(f"{msg} - {detail}")
                            error_detail = " | ".join(error_messages)
            except:
                pass

            error_msg = f"❌ QuickBooks API Error: {str(e)}"
            if error_detail:
                error_msg += f"\nDetails: {error_detail}"

            logger.error(error_msg)
            messages.error(request, error_msg)
            return redirect('poc_step4_push_quickbooks', loan_id=loan.id)

        except Exception as e:
            logger.error(f"❌ QuickBooks push failed: {str(e)}", exc_info=True)
            messages.error(request, f"❌ Failed to push to QuickBooks: {str(e)}")
            return redirect('poc_step4_push_quickbooks', loan_id=loan.id)

    # GET request - show the form
    logger.info("   📄 GET request - showing form")
    deposit_info = loan.get_complete_deposit_record() if hasattr(loan, 'get_complete_deposit_record') else {
        'amount': loan.deposit_paid,
        'date': loan.deposit_paid_date,
        'method': loan.deposit_payment_method,
        'receipt': loan.deposit_receipt_number,
    }

    context = {
        'loan': loan,
        'deposit_info': deposit_info,
        'customer_name': customer_name,
        'customer_email': customer_email,
    }
    return render(request, 'poc/step4_push_quickbooks.html', context)


@login_required
def poc_reset(request):
    """Reset POC data"""
    if request.method == 'POST':
        confirm_text = request.POST.get('confirm_text', '')
        if confirm_text == 'DELETE':
            # Delete POC data
            ApplicationModel.objects.filter(
                customer=request.user,
                notes__icontains='POC'
            ).delete()

            try:
                from payments.models import PaymentRecord
                PaymentRecord.objects.filter(
                    customer=request.user,
                    notes__icontains='POC'
                ).delete()
            except:
                pass

            try:
                from loans.models import LoanProduct
                LoanProduct.objects.filter(
                    customer=request.user,
                    notes__icontains='POC'
                ).delete()
            except:
                pass

            messages.success(request, "✅ POC data reset successfully!")
            return redirect('poc_dashboard')
        else:
            messages.error(request, "Please type 'DELETE' to confirm.")

    return render(request, 'poc/poc_reset.html')

# poc/views.py - Add this new view

# poc/views.py - Update the manual creation view

@login_required
def poc_create_loan_manual(request, payment_id):
    """Manually create a loan from a payment"""
    from payments.models import PaymentRecord
    from loans.services.loan_creation_service import LoanCreationService
    import logging

    logger = logging.getLogger(__name__)

    payment = get_object_or_404(PaymentRecord, id=payment_id)

    if request.method == 'POST':
        try:
            logger.info(f"🔄 Manual loan creation triggered for payment {payment.receipt_number}")
            loan = LoanCreationService.handle_deposit_confirmation(payment)

            if loan:
                messages.success(request, f"✅ Loan {loan.loan_id} created successfully!")
                return redirect('poc_step3_view_loan', loan_id=loan.id)
            else:
                messages.error(request, "❌ Failed to create loan. Check server logs for details.")

                # Log more details
                logger.error(f"Manual loan creation returned None for payment {payment.receipt_number}")
                logger.error(f"  Payment status: {payment.status}")
                logger.error(f"  Application: {payment.application}")
                logger.error(f"  Auto-create: {payment.auto_create_loan}")

        except Exception as e:
            logger.error(f"❌ Manual loan creation error: {str(e)}", exc_info=True)
            messages.error(request, f"Error creating loan: {str(e)}")

    return redirect('poc_step2_view_payment', payment_id=payment.id)