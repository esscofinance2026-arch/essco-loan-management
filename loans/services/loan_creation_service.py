# loans/services/loan_creation_service.py

import logging

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from loans.models import LoanProduct, PaymentSchedule

from quickbooks.services import QuickBooksPushService
from quickbooks.models import QuickBooksToken

logger = logging.getLogger(__name__)


class LoanCreationService:

    # ============================================================
    # COMMON SETTINGS
    # ============================================================

    DEFAULT_INTEREST_RATE = Decimal("12.00")
    DEFAULT_TENURE = 24

    TERM_MAPPING = {
        "Six": 6,
        "Twelve": 12,
        "Eighteen": 18,
        "Twenty Four": 24,
        "Thirty": 30,
        "Thirty Six": 36,
    }

    CENT = Decimal("0.01")


    # ============================================================
    # CALCULATION FOR THE LOAN
    # ============================================================
    @staticmethod
    def _calculate_reducing_balance_loan(principal, interest_rate, tenure_months):
        """
        Calculate a hire-purchase loan using reducing-balance simple/periodic interest.

        Interest is calculated monthly on the remaining principal balance.

        Args:
            principal: Amount financed after deposit
            interest_rate: Annual interest rate as a percentage (e.g. 12.00)
            tenure_months: Number of monthly installments

        Returns:
            dict containing:
                monthly_installment
                total_interest
                total_payable
        """

        # Convert everything to Decimal
        principal = Decimal(str(principal)).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )

        interest_rate = Decimal(str(interest_rate))

        tenure_months = int(tenure_months)

        if principal <= 0:
            raise ValueError("Principal amount must be greater than zero.")

        if tenure_months <= 0:
            raise ValueError("Tenure must be greater than zero.")

        if interest_rate < 0:
            raise ValueError("Interest rate cannot be negative.")

        # ------------------------------------------------------------
        # MONTHLY INTEREST RATE
        # ------------------------------------------------------------
        # Example:
        # Annual rate = 12%
        #
        # 12 / 100 / 12
        # = 0.01 per month
        #
        monthly_rate = (
            interest_rate / Decimal('100')
        ) / Decimal('12')

        # ------------------------------------------------------------
        # MONTHLY PAYMENT
        # ------------------------------------------------------------

        if monthly_rate == Decimal('0'):
            # Zero-interest loan
            monthly_installment = (
                principal / Decimal(str(tenure_months))
            )

        else:
            # Reducing-balance amortization formula:
            #
            # M = P × r × (1+r)^n
            #     ----------------
            #     (1+r)^n - 1
            #
            factor = (
                Decimal('1') + monthly_rate
            ) ** tenure_months

            monthly_installment = (
                principal
                * monthly_rate
                * factor
                / (factor - Decimal('1'))
            )

        # Round monthly payment to cents
        monthly_installment = monthly_installment.quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )

        # ------------------------------------------------------------
        # GENERATE THE AMORTIZATION CALCULATION
        # ------------------------------------------------------------

        remaining_principal = principal
        total_interest = Decimal('0.00')
        total_principal = Decimal('0.00')

        for month in range(1, tenure_months + 1):

            # Interest is calculated on the CURRENT balance
            interest_due = (
                remaining_principal * monthly_rate
            ).quantize(
                Decimal('0.01'),
                rounding=ROUND_HALF_UP
            )

            # For the final month, clear whatever principal remains.
            if month == tenure_months:

                principal_due = remaining_principal

            else:

                principal_due = (
                    monthly_installment - interest_due
                ).quantize(
                    Decimal('0.01'),
                    rounding=ROUND_HALF_UP
                )

                # Safety check
                if principal_due > remaining_principal:
                    principal_due = remaining_principal

            # Update totals
            total_interest += interest_due
            total_principal += principal_due

            # Reduce balance
            remaining_principal -= principal_due

            # Prevent tiny Decimal rounding residue
            if abs(remaining_principal) < Decimal('0.01'):
                remaining_principal = Decimal('0.00')

        # ------------------------------------------------------------
        # FINAL TOTALS
        # ------------------------------------------------------------

        total_interest = total_interest.quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )

        total_payable = (
            principal + total_interest
        ).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )

        # ------------------------------------------------------------
        # RETURN ALL CALCULATED VALUES
        # ------------------------------------------------------------

        result = {
            'principal': principal,
            'interest_rate': interest_rate,
            'tenure_months': tenure_months,
            'monthly_rate': monthly_rate,
            'monthly_installment': monthly_installment,
            'total_interest': total_interest,
            'total_payable': total_payable,
        }

        logger.info("📊 Reducing Balance Loan Calculation")
        logger.info(f"   Principal: ${principal}")
        logger.info(f"   Annual Rate: {interest_rate}%")
        logger.info(f"   Monthly Rate: {monthly_rate}")
        logger.info(f"   Term: {tenure_months} months")
        logger.info(f"   Monthly Installment: ${monthly_installment}")
        logger.info(f"   Total Interest: ${total_interest}")
        logger.info(f"   Total Payable: ${total_payable}")

        return result

    # ============================================================
    # AUTOMATIC LOAN CREATION
    # ============================================================

    @staticmethod
    @transaction.atomic
    def handle_deposit_confirmation(payment):
        """
        Handle confirmed deposit and create the loan automatically.

        The reducing-balance calculation is handled centrally by:
            _calculate_reducing_balance_loan()
        """

        logger.info(
            f"🔍 Starting loan creation for payment {payment.receipt_number}"
        )
        logger.info(f"   Auto-create: {payment.auto_create_loan}")
        logger.info(f"   Payment status: {payment.status}")

        # ------------------------------------------------------------
        # CHECK AUTO-CREATE
        # ------------------------------------------------------------
        if not payment.auto_create_loan:
            logger.info(
                f"Auto-create is OFF for payment {payment.receipt_number}"
            )
            return None

        # ------------------------------------------------------------
        # GET APPLICATION
        # ------------------------------------------------------------
        application = payment.application

        if not application:
            logger.error(
                f"No application linked to payment "
                f"{payment.receipt_number}"
            )
            return None

        logger.info(f"   Application ID: {application.id}")
        logger.info(
            f"   Application reference: {application.reference_number}"
        )

        # ------------------------------------------------------------
        # CHECK IF LOAN ALREADY EXISTS
        # ------------------------------------------------------------
        existing_loan = LoanProduct.objects.filter(
            application=application
        ).first()

        if existing_loan:
            logger.info(
                f"Loan already exists for application "
                f"{application.id}: {existing_loan.loan_id}"
            )
            return existing_loan

        try:

            # --------------------------------------------------------
            # GET INTEREST RATE
            # --------------------------------------------------------
            rate_obj = application.get_rate_for_status()

            if rate_obj:
                interest_rate = Decimal(str(rate_obj.rate))
            else:
                interest_rate = Decimal('12.00')

            logger.info(
                f"   Interest rate: {interest_rate}%"
            )

            # --------------------------------------------------------
            # GET TENURE
            # --------------------------------------------------------
            term_mapping = {
                'Six': 6,
                'Twelve': 12,
                'Eighteen': 18,
                'Twenty Four': 24,
                'Thirty': 30,
                'Thirty Six': 36,
            }

            tenure_months = term_mapping.get(
                application.Term,
                24
            )

            logger.info(
                f"   Tenure: {tenure_months} months"
            )

            # --------------------------------------------------------
            # GET PRINCIPAL
            # --------------------------------------------------------
            #
            # IMPORTANT:
            # Financed_Amt should represent the amount being financed
            # AFTER the deposit.
            #
            # If Financed_Amt is not available, fall back to
            # Purchase_Value.
            #


            principal = (
                application.Financed_Amt
                if application.Financed_Amt and application.Financed_Amt > 0
                else application.Purchase_Value
            )

            principal = Decimal(str(principal))

            if principal <= 0:
                logger.error(
                    f"Invalid principal for application "
                    f"{application.id}"
                )
                return None

            logger.info(
                f"   Principal financed: ${principal}"
            )

            # --------------------------------------------------------
            # CENTRAL REDUCING-BALANCE CALCULATION
            # --------------------------------------------------------
            calculation = (
                LoanCreationService
                ._calculate_reducing_balance_loan(
                    principal=principal,
                    interest_rate=interest_rate,
                    tenure_months=tenure_months
                )
            )

            monthly_installment = calculation[
                'monthly_installment'
            ]

            total_interest = calculation[
                'total_interest'
            ]

            total_payable = calculation[
                'total_payable'
            ]

            #outstanding_balance = total_payable - payment.amount
            outstanding_balance = total_payable
            deposit_target = application.Deposit or Decimal('0.00')
            # --------------------------------------------------------
            # CREATE LOAN
            # --------------------------------------------------------
            loan = LoanProduct(
                loan_id=LoanCreationService._generate_loan_id(),

                customer=application.customer,
                application=application,

                # Loan terms
                principal_amount=principal,
                interest_rate=interest_rate,
                tenure_months=tenure_months,
                monthly_installment=monthly_installment,

                # Financials
                total_interest=total_interest,
                total_payable=total_payable,

                # Deposit has already been accounted for
                # in the financed principal.
                outstanding_balance=outstanding_balance,

                # Deposit information
                deposit_paid=payment.amount,
                deposit_target=deposit_target,
                deposit_complete=payment.amount >= deposit_target,
                deposit_paid_date=payment.payment_date,
                deposit_payment_method=(
                    payment.payment_method.name
                    if payment.payment_method
                    else 'Cash'
                ),
                deposit_receipt_number=payment.receipt_number,
                deposit_payment=payment,

                # Status
                status='ACTIVE' if payment.amount >= deposit_target else 'DRAFT',
                creation_method='AUTO',

                created_by=(
                    payment.confirmed_by
                    or payment.recorded_by
                ),

                notes=(
                    f"Auto-created from deposit "
                    f"{payment.receipt_number}"
                )
            )

            # --------------------------------------------------------
            # SET DATES
            # --------------------------------------------------------
            today = timezone.now().date()

            loan.start_date = today

            loan.first_payment_date = (
                today + timedelta(days=30)
            )

            loan.maturity_date = (
                today + timedelta(days=30 * tenure_months)
            )

            # --------------------------------------------------------
            # SAVE LOAN
            # --------------------------------------------------------
            loan.save()

            # --------------------------------------------------------
            # ✅ LINK THE CUSTOMER (if not set)
            # --------------------------------------------------------
            if not loan.customer and application.customer:
                loan.customer = application.customer
                loan.save()

            # --------------------------------------------------------
            # GENERATE PAYMENT SCHEDULE
            # --------------------------------------------------------
            LoanCreationService._generate_payment_schedule(
                loan
            )

            # --------------------------------------------------------
            # LINK PAYMENT TO LOAN
            # --------------------------------------------------------
            payment.loan = loan
            payment.save()

            # --------------------------------------------------------
            # UPDATE APPLICATION
            # --------------------------------------------------------
            application.deposit_status = 'TRANSFERRED'
            application.save()

            try:
                # Check if QuickBooks is connected
                if QuickBooksToken.objects.filter(user=payment.customer).exists():
                    service = QuickBooksPushService(payment.customer)

                    # Sync customer
                    customer_data = {
                        'email': payment.customer.email,
                        'first_name': payment.customer.first_name,
                        'last_name': payment.customer.last_name,
                        'display_name': f"{payment.customer.first_name} {payment.customer.last_name}",
                        'phone': getattr(payment.customer, 'phone', ''),
                        'customer_id': payment.customer.customer_id,
                    }
                    customer_result = service.create_customer(customer_data)
                    loan.quickbooks_customer_id = customer_result['Customer']['Id']

                    # Sync invoice
                    invoice_data = {
                        'doc_number': f"LOAN-{loan.loan_id}",
                        'customer_ref': loan.quickbooks_customer_id,
                        'amount': float(loan.principal_amount),
                        'description': f"HP Loan {loan.loan_id}",
                        'invoice_id': str(loan.id),
                        'loan_id': loan.loan_id,
                    }
                    invoice_result = service.create_invoice(invoice_data)
                    loan.quickbooks_invoice_id = invoice_result['Invoice']['Id']

                    # Sync deposit payment
                    payment_data = {
                        'PaymentRefNum': f"DEP-{loan.loan_id}",
                        'customer_ref': loan.quickbooks_customer_id,
                        'invoice_ref': loan.quickbooks_invoice_id,
                        'amount': float(payment.amount),
                        'payment_date': payment.payment_date,
                    }
                    service.create_payment(payment_data)

                    # Save loan with QuickBooks IDs
                    loan.save()

                    logger.info(f"✅ Loan {loan.loan_id} auto-synced to QuickBooks")

            except Exception as e:
                logger.error(f"❌ Auto-sync failed for loan {loan.loan_id}: {str(e)}")




            logger.info(
                f"✅ Loan {loan.loan_id} created successfully "
                f"from payment {payment.receipt_number}"
            )

            return loan

        except Exception as e:

            logger.error(
                f"❌ Loan creation failed: {str(e)}",
                exc_info=True
            )

            raise

    # ============================================================
    # MANUAL LOAN CREATION
    # ============================================================

    @staticmethod
    @transaction.atomic
    def manual_create_loan(application, payment, principal, interest_rate, tenure_months, user):
        """
        Manually create a loan from an application.

        Uses the same reducing-balance calculation as
        automatic loan creation.
        """

        logger.info(
            f"🔧 Manual loan creation for application "
            f"{application.id}"
        )

        # ------------------------------------------------------------
        # CHECK IF LOAN ALREADY EXISTS
        # ------------------------------------------------------------
        existing_loan = LoanProduct.objects.filter(
            application=application
        ).first()

        if existing_loan:
            logger.info(
                f"Loan already exists: "
                f"{existing_loan.loan_id}"
            )
            return existing_loan

        try:

            # --------------------------------------------------------
            # CONVERT INPUTS TO DECIMAL / INTEGER
            # --------------------------------------------------------
            principal = Decimal(str(principal))
            interest_rate = Decimal(str(interest_rate))
            tenure_months = int(tenure_months)

            # --------------------------------------------------------
            # CENTRAL REDUCING-BALANCE CALCULATION
            # --------------------------------------------------------
            calculation = (
                LoanCreationService
                ._calculate_reducing_balance_loan(
                    principal=principal,
                    interest_rate=interest_rate,
                    tenure_months=tenure_months
                )
            )

            monthly_installment = calculation[
                'monthly_installment'
            ]

            total_interest = calculation[
                'total_interest'
            ]

            total_payable = calculation[
                'total_payable'
            ]

            logger.info(
                f"   Principal: ${principal}"
            )
            logger.info(
                f"   Interest Rate: {interest_rate}%"
            )
            logger.info(
                f"   Tenure: {tenure_months} months"
            )
            logger.info(
                f"   Monthly Installment: "
                f"${monthly_installment}"
            )
            logger.info(
                f"   Total Interest: "
                f"${total_interest}"
            )
            logger.info(
                f"   Total Payable: "
                f"${total_payable}"
            )

            outstanding_balance = total_payable - payment.amount
            deposit_target = application.Deposit or Decimal('0.00')
            # --------------------------------------------------------
            # CREATE LOAN
            # --------------------------------------------------------
            loan = LoanProduct(
                loan_id=LoanCreationService._generate_loan_id(),

                customer=application.customer,
                application=application,

                # Loan terms
                principal_amount=principal,
                interest_rate=interest_rate,
                tenure_months=tenure_months,
                monthly_installment=monthly_installment,

                # Financials
                total_interest=total_interest,
                total_payable=total_payable,

                # Deposit already accounted for in principal
                outstanding_balance=outstanding_balance,

                # Total paid should be 0
                #total_paid=payment.amount,
                # Total paid should be the deposit amount
                total_paid = 0,

                # Deposit information
                deposit_paid=payment.amount,
                deposit_target=deposit_target,
                deposit_complete=payment.amount >= deposit_target,
                deposit_paid_date=payment.payment_date,
                deposit_payment_method=(
                    payment.payment_method.name
                    if payment.payment_method
                    else 'Cash'
                ),
                deposit_receipt_number=payment.receipt_number,
                deposit_payment=payment,

                # Status
                status='ACTIVE' if payment.amount >= deposit_target else 'DRAFT',
                creation_method='MANUAL',

                created_by=user,

                notes=(
                    f"Manually created from application "
                    f"{application.reference_number} "
                    f"by {user.username}"
                )
            )

            # --------------------------------------------------------
            # SET DATES
            # --------------------------------------------------------
            today = timezone.now().date()

            loan.start_date = today

            loan.first_payment_date = (
                today + timedelta(days=30)
            )

            loan.maturity_date = (
                today + timedelta(days=30 * tenure_months)
            )

            # --------------------------------------------------------
            # SAVE
            # --------------------------------------------------------
            loan.save()

            # --------------------------------------------------------
            # ✅ LINK THE CUSTOMER (if not set)
            # --------------------------------------------------------
            if not loan.customer and application.customer:
                loan.customer = application.customer
                loan.save()

            # --------------------------------------------------------
            # GENERATE PAYMENT SCHEDULE
            # --------------------------------------------------------
            LoanCreationService._generate_payment_schedule(
                loan
            )

            # --------------------------------------------------------
            # LINK PAYMENT TO LOAN
            # --------------------------------------------------------
            payment.loan = loan
            payment.save()

            # --------------------------------------------------------
            # UPDATE APPLICATION
            # --------------------------------------------------------
            application.deposit_status = 'TRANSFERRED'
            application.save()

            logger.info(
                f"✅ Manual loan {loan.loan_id} "
                f"created successfully"
            )

            return loan

        except Exception as e:

            logger.error(
                f"❌ Manual loan creation failed: {str(e)}",
                exc_info=True
            )

            return None

    # ============================================================
    # COMMON LOAN CREATION ENGINE
    # ============================================================

    @staticmethod
    def _create_loan(
        application,
        payment,
        principal,
        interest_rate,
        tenure_months,
        user=None,
        creation_method="AUTO",
        notes="",
    ):
        """
        THE ONE AND ONLY PLACE WHERE A LOAN IS CREATED.

        Both:

            handle_deposit_confirmation()

        and:

            manual_create_loan()

        come through this function.

        Interest method:

            REDUCING BALANCE

        Monthly interest:

            Remaining Principal × Monthly Interest Rate
        """

        # --------------------------------------------------------
        # Double-check existing loan
        # --------------------------------------------------------

        existing_loan = LoanProduct.objects.filter(
            application=application
        ).first()

        if existing_loan:
            logger.info(
                f"Loan already exists: "
                f"{existing_loan.loan_id}"
            )

            return existing_loan

        # --------------------------------------------------------
        # Decimal conversion
        # --------------------------------------------------------

        principal = Decimal(str(principal)).quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

        interest_rate = Decimal(str(interest_rate)).quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

        tenure_months = int(tenure_months)

        # --------------------------------------------------------
        # Monthly interest rate
        #
        # Example:
        #
        # Annual rate = 12%
        #
        # Monthly rate =
        #
        # 12 / 100 / 12
        #
        # = 0.01
        #
        # = 1% per month
        # --------------------------------------------------------

        monthly_rate = (
            interest_rate / Decimal("100")
        ) / Decimal("12")

        logger.info(
            f"   Monthly reducing-balance rate: "
            f"{monthly_rate}"
        )

        # --------------------------------------------------------
        # Calculate EMI
        # --------------------------------------------------------

        monthly_installment = (
            LoanCreationService._calculate_monthly_payment(
                principal=principal,
                monthly_rate=monthly_rate,
                tenure_months=tenure_months,
            )
        )

        logger.info(
            f"   Monthly installment: "
            f"${monthly_installment}"
        )

        # --------------------------------------------------------
        # Dates
        # --------------------------------------------------------

        today = timezone.now().date()

        first_payment_date = today + timedelta(days=30)

        maturity_date = (
            today + timedelta(days=30 * tenure_months)
        )

        # --------------------------------------------------------
        # Create initial loan
        #
        # total_interest and total_payable are temporarily
        # calculated from the schedule after the loan exists.
        # --------------------------------------------------------

        loan = LoanProduct(
            loan_id=LoanCreationService._generate_loan_id(),

            customer=application.customer,

            application=application,

            principal_amount=principal,

            interest_rate=interest_rate,

            tenure_months=tenure_months,

            monthly_installment=monthly_installment,

            total_interest=Decimal("0.00"),

            total_payable=Decimal("0.00"),

            # Principal is already the financed amount.
            # Therefore we do NOT subtract the deposit here.
            outstanding_balance=Decimal("0.00"),

            deposit_paid=payment.amount,

            deposit_paid_date=payment.payment_date,

            deposit_payment_method=(
                payment.payment_method.name
                if payment.payment_method
                else "Cash"
            ),

            deposit_receipt_number=payment.receipt_number,

            deposit_payment=payment,

            status="ACTIVE",

            creation_method=creation_method,

            created_by=user,

            notes=notes,

            start_date=today,

            first_payment_date=first_payment_date,

            maturity_date=maturity_date,
        )

        loan.save()

        logger.info(
            f"   Loan created: {loan.loan_id}"
        )

        # --------------------------------------------------------
        # Generate reducing-balance schedule
        # --------------------------------------------------------

        schedule_totals = (
            LoanCreationService._generate_payment_schedule(
                loan
            )
        )

        total_principal = schedule_totals[
            "total_principal"
        ]

        total_interest = schedule_totals[
            "total_interest"
        ]

        total_payable = schedule_totals[
            "total_payable"
        ]

        remaining_balance = schedule_totals[
            "remaining_balance"
        ]

        # --------------------------------------------------------
        # Update loan totals from ACTUAL schedule
        # --------------------------------------------------------

        loan.total_interest = total_interest.quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

        loan.total_payable = total_payable.quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

        loan.outstanding_balance = total_payable.quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

        loan.save(
            update_fields=[
                "total_interest",
                "total_payable",
                "outstanding_balance",
            ]
        )

        # --------------------------------------------------------
        # Update payment
        # --------------------------------------------------------

        payment.loan = loan
        payment.save(update_fields=["loan"])

        # --------------------------------------------------------
        # Update application
        # --------------------------------------------------------

        application.deposit_status = "TRANSFERRED"
        application.save(
            update_fields=["deposit_status"]
        )

        logger.info(
            f"✅ Loan {loan.loan_id} created successfully"
        )

        logger.info(
            f"   Principal: ${total_principal}"
        )

        logger.info(
            f"   Interest: ${total_interest}"
        )

        logger.info(
            f"   Total Payable: ${total_payable}"
        )

        logger.info(
            f"   Outstanding: ${loan.outstanding_balance}"
        )

        return loan

    # ============================================================
    # MONTHLY PAYMENT CALCULATION
    # ============================================================

    @staticmethod
    def _calculate_monthly_payment(
        principal,
        monthly_rate,
        tenure_months,
    ):
        """
        Calculate the regular monthly payment for a
        reducing-balance loan.

        Formula:

            Payment =
                P × r × (1+r)^n
                ----------------
                   (1+r)^n - 1

        Where:

            P = principal
            r = monthly interest rate
            n = number of months
        """

        principal = Decimal(str(principal))
        monthly_rate = Decimal(str(monthly_rate))
        tenure_months = int(tenure_months)

        # --------------------------------------------------------
        # Zero interest
        # --------------------------------------------------------

        if monthly_rate == Decimal("0"):
            return (
                principal / Decimal(str(tenure_months))
            ).quantize(
                LoanCreationService.CENT,
                rounding=ROUND_HALF_UP,
            )

        # --------------------------------------------------------
        # Reducing balance formula
        # --------------------------------------------------------

        factor = (
            Decimal("1") + monthly_rate
        ) ** tenure_months

        payment = (
            principal
            * monthly_rate
            * factor
            / (factor - Decimal("1"))
        )

        return payment.quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

    # ============================================================
    # PAYMENT SCHEDULE
    # ============================================================

    @staticmethod
    def _generate_payment_schedule(loan):
        """
        Generate a reducing-balance hire-purchase schedule.

        Every month:

            Interest =
                Outstanding Principal × Monthly Rate

            Principal Paid =
                Monthly Payment - Interest

        The final payment is adjusted so the principal
        reaches exactly zero.
        """

        # --------------------------------------------------------
        # Starting principal
        # --------------------------------------------------------

        remaining_principal = Decimal(
            str(loan.principal_amount)
        ).quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

        annual_rate = Decimal(
            str(loan.interest_rate)
        )

        monthly_rate = (
            annual_rate / Decimal("100")
        ) / Decimal("12")

        regular_payment = Decimal(
            str(loan.monthly_installment)
        ).quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

        payment_date = loan.first_payment_date

        total_interest = Decimal("0.00")
        total_principal = Decimal("0.00")
        total_payable = Decimal("0.00")

        # --------------------------------------------------------
        # Generate each installment
        # --------------------------------------------------------

        for i in range(1, loan.tenure_months + 1):

            if remaining_principal <= Decimal("0.00"):
                break

            # ----------------------------------------------------
            # Interest on CURRENT outstanding principal
            # ----------------------------------------------------

            interest_due = (
                remaining_principal * monthly_rate
            ).quantize(
                LoanCreationService.CENT,
                rounding=ROUND_HALF_UP,
            )

            # ----------------------------------------------------
            # Last payment
            # ----------------------------------------------------

            if i == loan.tenure_months:

                principal_due = remaining_principal

                total_due = (
                    principal_due + interest_due
                ).quantize(
                    LoanCreationService.CENT,
                    rounding=ROUND_HALF_UP,
                )

            else:

                principal_due = (
                    regular_payment - interest_due
                ).quantize(
                    LoanCreationService.CENT,
                    rounding=ROUND_HALF_UP,
                )

                # Safety check
                if principal_due < Decimal("0.00"):
                    principal_due = Decimal("0.00")

                # Never pay more principal than remains
                if principal_due > remaining_principal:
                    principal_due = remaining_principal

                total_due = (
                    principal_due + interest_due
                ).quantize(
                    LoanCreationService.CENT,
                    rounding=ROUND_HALF_UP,
                )

            # ----------------------------------------------------
            # Create schedule row
            # ----------------------------------------------------

            PaymentSchedule.objects.create(
                loan=loan,

                installment_number=i,

                due_date=payment_date,

                principal_due=principal_due,

                interest_due=interest_due,

                total_due=total_due,

                status="PENDING",
            )

            # ----------------------------------------------------
            # Update totals
            # ----------------------------------------------------

            remaining_principal -= principal_due

            remaining_principal = remaining_principal.quantize(
                LoanCreationService.CENT,
                rounding=ROUND_HALF_UP,
            )

            total_interest += interest_due

            total_principal += principal_due

            total_payable += total_due

            # ----------------------------------------------------
            # Next payment
            # ----------------------------------------------------

            payment_date += timedelta(days=30)

        # --------------------------------------------------------
        # Make sure rounding did not leave a tiny balance
        # --------------------------------------------------------

        if abs(remaining_principal) < Decimal("0.01"):
            remaining_principal = Decimal("0.00")

        # --------------------------------------------------------
        # Log results
        # --------------------------------------------------------

        logger.info(
            f"✅ Reducing-balance schedule generated "
            f"for {loan.loan_id}"
        )

        logger.info(
            f"   Principal: ${total_principal:.2f}"
        )

        logger.info(
            f"   Interest: ${total_interest:.2f}"
        )

        logger.info(
            f"   Total Payable: ${total_payable:.2f}"
        )

        logger.info(
            f"   Final Principal Balance: "
            f"${remaining_principal:.2f}"
        )

        return {
            "total_principal": total_principal,
            "total_interest": total_interest,
            "total_payable": total_payable,
            "remaining_balance": remaining_principal,
        }

    # ============================================================
    # GET INTEREST RATE
    # ============================================================

    @staticmethod
    def _get_interest_rate(application):
        """
        Get the interest rate from the application's
        current rate configuration.
        """

        try:
            rate_obj = application.get_rate_for_status()

            if rate_obj:
                return Decimal(
                    str(rate_obj.rate)
                ).quantize(
                    LoanCreationService.CENT,
                    rounding=ROUND_HALF_UP,
                )

        except Exception as e:

            logger.warning(
                f"Could not get application interest rate: "
                f"{str(e)}"
            )

        return LoanCreationService.DEFAULT_INTEREST_RATE

    # ============================================================
    # GET TENURE
    # ============================================================

    @staticmethod
    def _get_tenure(application):
        """
        Convert application Term into months.
        """

        return LoanCreationService.TERM_MAPPING.get(
            application.Term,
            LoanCreationService.DEFAULT_TENURE,
        )

    # ============================================================
    # GET PRINCIPAL
    # ============================================================

    @staticmethod
    def _get_principal(application):
        """
        Get the financed amount.

        Prefer Financed_Amt.

        If unavailable, use Purchase_Value.
        """

        financed_amount = (
            application.Financed_Amt
            if application.Financed_Amt
            else Decimal("0.00")
        )

        purchase_value = (
            application.Purchase_Value
            if application.Purchase_Value
            else Decimal("0.00")
        )

        principal = (
            financed_amount
            if financed_amount > 0
            else purchase_value
        )

        if principal <= 0:
            raise ValueError(
                "Application has no valid financed amount "
                "or purchase value."
            )

        return Decimal(str(principal)).quantize(
            LoanCreationService.CENT,
            rounding=ROUND_HALF_UP,
        )

    # ============================================================
    # GENERATE LOAN ID
    # ============================================================

    @staticmethod
    def _generate_loan_id():
        """
        Generate unique loan ID.
        """

        year = timezone.now().year

        last_loan = LoanProduct.objects.filter(
            loan_id__startswith=f"LOAN-{year}"
        ).order_by("-loan_id").first()

        if last_loan:

            try:
                last_number = int(
                    last_loan.loan_id.split("-")[-1]
                )

                next_number = last_number + 1

            except (ValueError, IndexError):

                next_number = 1

        else:

            next_number = 1

        return (
            f"LOAN-{year}-{next_number:06d}"
        )