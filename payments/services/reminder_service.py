# payments/services/reminder_service.py

"""
Payment Reminder Service
========================
Handles automated and manual payment reminders for loan installments.
Supports:
- Automated reminders for upcoming payments (3 days before due date)
- Automated reminders for overdue payments (1 day after due date)
- Manual reminders triggered by staff
- Audit logging for all reminder activities
"""

import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404
from applications.emails import send_email_async
from applications.models import EmailLog
from audit.services import log_action
from django.http import JsonResponse
import traceback


# ✅ CORRECT IMPORTS - LoanProduct comes from loans app, not payments
from loans.models import LoanProduct, PaymentSchedule

# Setup logger for this module
logger = logging.getLogger(__name__)


class ReminderService:
    """
    Service for sending automated payment reminders to customers.
    
    This service handles both automated (scheduled) reminders and manual
    reminders triggered by staff members. All reminders are logged for
    audit purposes.
    """

    # ============================================================
    # AUTOMATED REMINDERS (Scheduled Job)
    # ============================================================
    
    @staticmethod
    def send_payment_reminders():
        """
        Send reminders for upcoming and overdue payments.
        This method is designed to be called by a scheduled job (cron).
        
        Returns:
            int: Count of reminders successfully sent
        
        Reminder Types:
            - Upcoming: Sent 3 days before due date
            - Overdue: Sent 1 day after due date
        """
        today = timezone.now().date()
        reminders_sent = 0
        
        logger.info("=" * 50)
        logger.info("🔔 Starting automated payment reminder job")
        logger.info(f"   Date: {today}")
        logger.info("=" * 50)

        # ✅ 1. Upcoming reminders (3 days before due date)
        upcoming_date = today + timedelta(days=3)
        upcoming_payments = PaymentSchedule.objects.filter(
            due_date=upcoming_date,
            status='PENDING'  # Only send reminders for unpaid installments
        ).select_related('loan', 'loan__customer')  # ✅ Optimize query with select_related

        upcoming_count = upcoming_payments.count()
        logger.info(f"📅 Upcoming payments (due {upcoming_date}): {upcoming_count}")

        for schedule in upcoming_payments:
            if ReminderService._send_reminder(schedule, 'upcoming'):
                reminders_sent += 1

        # ✅ 2. Overdue reminders (1 day overdue)
        overdue_date = today - timedelta(days=1)
        overdue_payments = PaymentSchedule.objects.filter(
            due_date=overdue_date,
            status='PENDING'
        ).select_related('loan', 'loan__customer')

        overdue_count = overdue_payments.count()
        logger.info(f"📅 Overdue payments (due {overdue_date}): {overdue_count}")

        for schedule in overdue_payments:
            if ReminderService._send_reminder(schedule, 'overdue'):
                reminders_sent += 1

        logger.info("=" * 50)
        logger.info(f"✅ Reminders sent: {reminders_sent}")
        logger.info("=" * 50)

        return reminders_sent

    # ============================================================
    # SINGLE REMINDER (For testing or re-sending)
    # ============================================================

    @staticmethod
    def send_reminder_for_schedule(schedule, reminder_type='upcoming'):
        """
        Send a single reminder for a specific payment schedule.
        Useful for testing or manually re-sending a reminder.
        
        Args:
            schedule: PaymentSchedule object
            reminder_type: 'upcoming', 'overdue', or 'manual'
        
        Returns:
            bool: True if sent successfully, False otherwise
        """
        return ReminderService._send_reminder(schedule, reminder_type)

    # ============================================================
    # CORE REMINDER SENDING LOGIC (Internal)
    # ============================================================

    @staticmethod
    def _send_reminder(schedule, reminder_type, user=None):
        """
        Internal method to send a single reminder.
        This is the core logic that actually sends the email.
        
        Args:
            schedule: PaymentSchedule object
            reminder_type: 'upcoming', 'overdue', or 'manual'
        
        Returns:
            bool: True if sent successfully, False otherwise
        
        Steps:
            1. Validate customer and email exists
            2. Prepare email subject and content
            3. Render email templates (HTML + plain text)
            4. Send email via async function
            5. Log success/failure with audit trail
        """
        try:
            # ==========================================
            # STEP 1: GET LOAN AND CUSTOMER DATA
            # ==========================================
            loan = schedule.loan
            customer = loan.customer
            
            # ✅ Validate customer exists
            if not customer:
                logger.error(f"❌ No customer found for loan {loan.loan_id}")
                return False
            
            # ✅ Validate customer has an email address
            if not customer.email:
                logger.error(f"❌ No email for customer {customer.id}")
                return False

            # ==========================================
            # STEP 2: PREPARE EMAIL DATA
            # ==========================================
            due_date = schedule.due_date
            amount = schedule.total_due
            days_until_due = (due_date - timezone.now().date()).days

            # ✅ Subject based on reminder type
            if reminder_type == 'overdue':
                subject = f"⏰ Payment Overdue - {loan.loan_id}"
            elif reminder_type == 'upcoming':
                subject = f"🔔 Payment Reminder - {loan.loan_id}"
            else:
                subject = f"Payment Reminder - {loan.loan_id}"

            # ✅ Context for email templates
            context = {
                'customer_name': customer.get_full_name() or customer.username,
                'loan_id': loan.loan_id,
                'installment_number': schedule.installment_number,
                'due_date': due_date.strftime('%B %d, %Y'),
                'amount': f"${amount:,.2f}",
                'outstanding_balance': f"${loan.outstanding_balance:,.2f}",
                'days_until_due': days_until_due,
                'reminder_type': reminder_type,
                'payment_url': f"{settings.SITE_URL}/loans/{loan.id}/pay/",
                'support_email': settings.DEFAULT_FROM_EMAIL,
            }

            # ==========================================
            # STEP 3: RENDER EMAIL TEMPLATES
            # ==========================================
            try:
                # ✅ Render HTML version (for rich email clients)
                html_message = render_to_string(
                    f'emails/reminder_{reminder_type}.html',
                    context
                )
                # ✅ Render plain text version (for fallback)
                plain_message = render_to_string(
                    f'emails/reminder_{reminder_type}.txt',
                    context
                )
            except Exception as template_error:
                # ✅ Fallback message if templates don't exist
                logger.warning(f"Template not found, using fallback: {template_error}")
                html_message = f"""
                <h2>Payment Reminder</h2>
                <p>Dear {context['customer_name']},</p>
                <p>This is a reminder for your payment on loan <strong>{context['loan_id']}</strong>.</p>
                <p><strong>Installment #{context['installment_number']}</strong></p>
                <p><strong>Due Date:</strong> {context['due_date']}</p>
                <p><strong>Amount Due:</strong> {context['amount']}</p>
                <p><strong>Outstanding Balance:</strong> {context['outstanding_balance']}</p>
                <p><a href="{context['payment_url']}">Make Payment</a></p>
                <p>Thank you,<br>Essco Finance Team</p>
                """
                plain_message = f"""
                Payment Reminder
                
                Dear {context['customer_name']},
                
                This is a reminder for your payment on loan {context['loan_id']}.
                
                Installment #{context['installment_number']}
                Due Date: {context['due_date']}
                Amount Due: {context['amount']}
                Outstanding Balance: {context['outstanding_balance']}
                
                Make Payment: {context['payment_url']}
                
                Thank you,
                Essco Finance Team
                """

            # ==========================================
            # STEP 4: SEND EMAIL
            # ==========================================
            send_email_async(
                subject=subject,
                body=plain_message,
                to_email=customer.email,
                html_content=html_message,
                email_type='REMINDER'  # ✅ Tag for email tracking
            )

            # ==========================================
            # STEP 5: LOG SUCCESS
            # ==========================================
            logger.info(f"📧 Reminder sent to {customer.email} for {loan.loan_id} installment #{schedule.installment_number}")
            
            # ✅ Determine action based on reminder type
            if reminder_type == 'manual':
                action = 'MANUAL_REMINDER_SENT'
            else:
                action = 'REMINDER_SENT'
            
            # ✅ DEBUG - Check what user is being passed
            logger.info(f"🔍 DEBUG: user = {user}")
            if user:
                logger.info(f"🔍 DEBUG: user.username = {user.username}")
            else:
                logger.info(f"🔍 DEBUG: user is None (automated reminder)")
                
            # ✅ AUDIT LOG - Record the reminder action
            log_action(
                request=None,
                user=user,  # None = System (automated reminder)
                action=action,
                description=(
                    f"{reminder_type.capitalize()} reminder sent to {customer.email} "
                    f"for loan {loan.loan_id}, installment #{schedule.installment_number}, "
                    f"amount ${amount:,.2f}, due {due_date.strftime('%Y-%m-%d')}"
                ),
                loan=loan,
                ip_address=None
            )

            return True

        except Exception as e:
            # ==========================================
            # STEP 6: LOG ERROR
            # ==========================================
            logger.error(f"❌ Failed to send reminder for schedule {schedule.id}: {e}")
            logger.error(traceback.format_exc())
            return False

    # ============================================================
    # MANUAL REMINDERS (Staff Triggered)
    # ============================================================

    @staticmethod
    def send_manual_reminder(request, schedule_id):
        """
        Admin view to manually send a reminder (AJAX)
        Returns JSON response
        """
        logger.info(f"🔔 send_manual_reminder called for schedule {schedule_id}")
        
        try:
            schedule = get_object_or_404(PaymentSchedule, id=schedule_id)
            logger.info(f"   Schedule found: #{schedule.installment_number}")
            logger.info(f"   Loan: {schedule.loan.loan_id}")
            logger.info(f"   Status: {schedule.status}")
            
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
    
            logger.info(f"   Customer: {customer}")
            logger.info(f"   Customer Email: {customer.email}")
    
            if not customer.email:
                logger.error(f"   Customer has no email")
                return JsonResponse({
                    'success': False,
                    'error': 'Customer has no email address'
                }, status=400)
    
            # ✅ Send reminder - PASS THE USER
            logger.info(f"   Calling ReminderService._send_reminder...")
            success = ReminderService._send_reminder(schedule, 'manual', user=request.user)  # ✅ ADD user=request.user
            logger.info(f"   Result: {success}")
    
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