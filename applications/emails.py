# emails.py
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from .models import StaffMember
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import logging
import threading
from applications.models import EmailLog
from audit.services import log_action

logger = logging.getLogger(__name__)

# Get the User model
User = get_user_model()


def application_reference(application):
    """Generate application reference number."""
    #return f"ESS-{application.pk:06d}"
    return f"{application.reference_number}"

# ============================================================
# ✅ EMAIL SENDING WITH THREADING (CENTRALIZED)
# ============================================================
# applications/emails.py

def send_email_async(subject, body, to_email, html_content=None, email_type='GENERAL'):
    """
    Send email in background thread with logging
    """
    def _send():
        try:
            # ✅ Create email
            email = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
            )
            if html_content:
                email.attach_alternative(html_content, "text/html")

            # ✅ Send email
            email.send()

            # ✅ Log the email in database
            EmailLog.objects.create(
                email_type=email_type,
                recipient=to_email,
                subject=subject[:255],
                status='sent',
                message_id=email.extra_headers.get('Message-ID', '')
            )

            logger.info(f"✅ Email sent to {to_email} ({email_type})")

        except Exception as e:
            logger.error(f"❌ Email failed to {to_email}: {e}")
            # ✅ Log failure too
            EmailLog.objects.create(
                email_type=email_type,
                recipient=to_email,
                subject=subject[:255],
                status='failed',
            )

    try:
        # ✅ Check if we're near the limit (warning)
        from applications.services.email_counter import EmailCounter
        remaining = EmailCounter.get_remaining()

        if remaining <= 50:
            logger.warning(f"⚠️ Only {remaining} emails remaining today")

        if remaining <= 20:
            logger.warning(f"🚨 CRITICAL: Only {remaining} emails remaining today")

        # ✅ Start thread
        thread = threading.Thread(target=_send)
        thread.daemon = True
        thread.start()
        logger.info(f"📧 Email queued for {to_email} ({email_type})")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to queue email for {to_email}: {e}")
        return False






def send_email_async1(subject, body, to_email, html_content=None):
    """
    Send email in background thread with proper error handling
    """
    def _send():
        try:
            # ✅ Create email
            email = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
            )
            if html_content:
                email.attach_alternative(html_content, "text/html")

            # ✅ Send email
            email.send()

            logger.info(f"✅ Email sent to {to_email}")
            #logger.info(f"✅ Email sent to {to_email} ({email_type})")

        except Exception as e:
            logger.error(f"❌ Email failed to {to_email}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    try:
        # ✅ Start thread
        thread = threading.Thread(target=_send)
        thread.daemon = True
        thread.start()
        logger.info(f"📧 Email queued for {to_email}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to queue email for {to_email}: {e}")
        return False

###########################################################################################################################################################################
def send_application_confirmation(application):
    """
    Sends a confirmation email to the customer after
    a loan application has been submitted.

    🔒 Security features:
    - Email validation
    - Subject sanitization
    - Auto-escaping templates
    - Hardcoded sender
    - No user CC/BCC
    """
    try:
        # ============================================================
        # ⭐ 1. VALIDATE EMAIL (Prevent injection)
        # ============================================================
        try:
            validate_email(application.email)
        except ValidationError as e:
            logger.error(f"❌ Invalid email address: {application.email} - {e}")
            return False

        # ============================================================
        # ⭐ 2. SANITIZE SUBJECT (Remove newlines)
        # ============================================================
        subject = "ESSCO Finance - Application Received"
        # Remove any newlines to prevent header injection
        clean_subject = subject.replace('\n', '').replace('\r', '').strip()

        if not clean_subject:
            clean_subject = "ESSCO Finance - Application"
            logger.warning("Subject was empty, using default")

        # ============================================================
        # ⭐ 3. PREPARE CONTEXT
        # ============================================================
        context = {
            "application": application,
            "reference": f"{application.reference_number}",
            "name": f"{application.Fname} {application.Lname}",
        }

        # ============================================================
        # ⭐ 4. RENDER TEMPLATES (Django auto-escapes by default)
        # ============================================================
        text_content = render_to_string(
            "emails/application_received.txt",
            context,
        )

        html_content = render_to_string(
            "emails/application_received1.html",
            context,
        )

        # ============================================================
        # ⭐ 5. ✅ SEND EMAIL ASYNCHRONOUSLY (NON-BLOCKING!)
        # ============================================================
        send_email_async(
            subject=clean_subject,
            body=text_content,
            to_email=application.email,
            html_content=html_content,  # ✅ Attach HTML version
            email_type='APPLICATION_CONFIRMATION'  # ✅ Added
        )

        logger.info(f"✅ Confirmation email queued for {application.email}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to queue confirmation email: {e}")
        return False


#######################################################################################################################################################

def send_application_ap_confirmation(application):
    """
    Sends a confirmation email to the customer after
    a loan application has been submitted (Approved Pending status).

    🔒 Security: Email validation, subject sanitization, no user CC/BCC
    """
    try:
        # ============================================================
        # ⭐ 1. VALIDATE EMAIL
        # ============================================================
        try:
            validate_email(application.email)
        except ValidationError as e:
            logger.error(f"❌ Invalid email address: {application.email} - {e}")
            return False

        # ============================================================
        # ⭐ 2. SANITIZE SUBJECT
        # ============================================================
        subject = "ESSCO Finance - Application Received"
        clean_subject = subject.replace('\n', '').replace('\r', '').strip()

        if not clean_subject:
            clean_subject = "ESSCO Finance - Application Update"
            logger.warning("Subject was empty, using default")

        # ============================================================
        # ⭐ 3. PREPARE CONTEXT
        # ============================================================
        context = {
            "application": application,
            "reference": f"{application.reference_number}",
            "name": f"{application.Fname} {application.Lname}",
        }

        # ============================================================
        # ⭐ 4. RENDER TEMPLATES
        # ============================================================
        text_content = render_to_string(
            "emails/application_received.txt",
            context,
        )

        html_content = render_to_string(
            "emails/application_received_ap.html",
            context,
        )

        # ============================================================
        # ⭐ 5. CREATE EMAIL
        # ============================================================
        send_email_async(
            subject=clean_subject,
            body=text_content,
            to_email=application.email,
            html_content=html_content,  # ✅ Attach HTML version
            email_type='APPLICATION_CONFIRMATION'  # ✅ Added
        )

        logger.info(f"✅ AP Confirmation email sent to {application.email}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send AP confirmation email: {e}")
        return False
########################################################################################################################################################

def send_approval_email(application):
    """
    Sends an approval email to the customer when their
    loan application has been approved.

    🔒 Security: Email validation, subject sanitization, no user CC/BCC
    """
    try:
        # ============================================================
        # ⭐ 1. VALIDATE EMAIL (Prevent injection)
        # ============================================================
        try:
            validate_email(application.email)
        except ValidationError as e:
            logger.error(f"❌ Invalid email address: {application.email} - {e}")
            return False

        # ============================================================
        # ⭐ 2. SANITIZE SUBJECT (Remove newlines to prevent header injection)
        # ============================================================
        subject = "🎉 ESSCO Finance - Application Approved!"
        clean_subject = subject.replace('\n', '').replace('\r', '').strip()

        if not clean_subject:
            clean_subject = "ESSCO Finance - Application Approved"
            logger.warning("Subject was empty, using default")

        # ============================================================
        # ⭐ 3. PREPARE CONTEXT (with safe formatting)
        # ============================================================
        # Safely format currency values
        def safe_currency(value):
            if value is None:
                return "TBD"
            try:
                return f"${float(value):,.2f}"
            except (ValueError, TypeError):
                return "TBD"

        context = {
            "application": application,
            "reference": f"{application.reference_number}",
            "name": f"{application.Fname} {application.Lname}",
            "item_name": getattr(application, 'item_name', 'Not specified'),
            "item_sku": getattr(application, 'item_sku', 'N/A'),
            "item_price": safe_currency(getattr(application, 'item_price', None)),
            "credit_limit": safe_currency(application.Total_Credit_Allowed),
            "Deposit": safe_currency(application.Deposit),
            'Financed_Amt': safe_currency(application.Financed_Amt),
            "term": application.Term or "Not specified",
            "monthly_payment": None,
            "next_steps": [
                "Visit our store to complete your purchase",
                "Bring your valid ID and this approval email",
                "Our team will assist you with the final steps",
            ],
        }

        # Get monthly payment based on term (with safe access)
        term_mapping = {
            "Six": "Six",
            "Twelve": "Twelve",
            "Eighteen": "Eighteen",
            "Twenty Four": "Twenty_Four",
            "Thirty": "Thirty",
            "Thirty Six": "Thirty_Six",
        }

        for display_term, field_name in term_mapping.items():
            if application.Term == display_term:
                amount = getattr(application, field_name, None)
                if amount:
                    context["monthly_payment"] = safe_currency(amount)
                break

        # ============================================================
        # ⭐ 4. RENDER TEMPLATES (Django auto-escapes by default)
        # ============================================================
        text_content = render_to_string(
            "emails/application_approved.txt",
            context,
        )

        html_content = render_to_string(
            "emails/application_approved1.html",
            context,
        )

        # ======================================================================================================================================================================
        # Send EMAIL ASYNCHRONOUSLY (NON-BLOCKING!)
        # ============================================================
        send_email_async(
            subject=clean_subject,
            body=text_content,
            to_email=application.email,
            html_content=html_content,
            email_type='APPROVAL'  # ✅ Added
        )


        #email = EmailMultiAlternatives(
        #    subject=clean_subject,
        #    body=text_content,
        #    from_email=settings.DEFAULT_FROM_EMAIL,
        #    to=[application.email],
        #)
        #email.attach_alternative(html_content, "text/html")
        #email.send()

        logger.info(f"✅ Approval email sent to {application.email}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send approval email: {e}")
        return False






def send_rejection_email(application):
    """
    Sends a rejection email to the customer when their
    loan application has been rejected.

    🔒 Security: Email validation, subject sanitization, no user CC/BCC
    """
    try:
        # ============================================================
        # ⭐ 1. VALIDATE EMAIL (Prevent injection)
        # ============================================================
        try:
            validate_email(application.email)
        except ValidationError as e:
            logger.error(f"❌ Invalid email address: {application.email} - {e}")
            return False

        # ============================================================
        # ⭐ 2. SANITIZE SUBJECT (Remove newlines to prevent header injection)
        # ============================================================
        subject = "ESSCO Finance - Application Status Update"
        clean_subject = subject.replace('\n', '').replace('\r', '').strip()

        if not clean_subject:
            clean_subject = "ESSCO Finance - Application Update"
            logger.warning("Subject was empty, using default")

        # ============================================================
        # ⭐ 3. PREPARE CONTEXT
        # ============================================================
        context = {
            "application": application,
            "reference": f"{application.reference_number}",
            "name": f"{application.Fname} {application.Lname}",
        }

        # ============================================================
        # ⭐ 4. RENDER TEMPLATES (Django auto-escapes by default)
        # ============================================================
        text_content = render_to_string(
            "emails/application_rejected.txt",
            context,
        )

        html_content = render_to_string(
            "emails/application_rejected.html",
            context,
        )

        # ============================================================
        # ⭐ 5. CREATE EMAIL (Hardcoded sender, no user CC/BCC)
        # ============================================================
        send_email_async(
            subject=clean_subject,
            body=text_content,
            to_email=application.email,
            html_content=html_content,  # ✅ Attach HTML version
            email_type='REJECTION'  # ✅ Added
        )

        logger.info(f"✅ Rejection email sent to {application.email}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send rejection email: {e}")
        return False







def get_approval_recipient():
    """Get the staff member designated to receive approval emails"""
    try:
        recipient = StaffMember.objects.filter(
            is_approval_recipient=True,
            is_active=True
        ).first()

        if recipient:
            return recipient.email
        else:
            logger.warning("No approval recipient configured.")
            return None

    except Exception as e:
        logger.error(f"Error getting approval recipient: {e}")
        return None


def get_approval_recipient_details():
    """Get full details of the approval recipient"""
    try:
        recipient = StaffMember.objects.filter(
            is_approval_recipient=True,
            is_active=True
        ).first()

        if recipient:
            return {
                'email': recipient.email,
                'name': recipient.name,
                'role': recipient.role
            }
        return None
    except Exception as e:
        logger.error(f"Error getting approval recipient details: {e}")
        return None


def set_approval_recipient(staff_member_id):
    """Set a specific staff member as the approval recipient"""
    StaffMember.objects.filter(is_approval_recipient=True).update(is_approval_recipient=False)
    staff = StaffMember.objects.get(id=staff_member_id)
    staff.is_approval_recipient = True
    staff.save()
    return staff




#############################################################################################################################################################################

def send_staff_approval_notification(application):
    """
    Send notification email to staff member about approved application.

    🔒 Security: Email validation, subject sanitization, no user CC/BCC
    """
    try:
        # ============================================================
        # ⭐ 1. GET AND VALIDATE RECIPIENT EMAIL
        # ============================================================
        recipient_email = get_approval_recipient()

        if not recipient_email:
            logger.error("No staff recipient configured. Staff notification not sent.")
            return False

        # ⭐ Validate recipient email
        try:
            validate_email(recipient_email)
        except ValidationError as e:
            logger.error(f"❌ Invalid staff email address: {recipient_email} - {e}")
            return False

        # Get recipient details
        recipient_details = get_approval_recipient_details()
        recipient_name = recipient_details['name'] if recipient_details else "Staff Member"

        # ============================================================
        # ⭐ 2. SANITIZE SUBJECT (Remove newlines to prevent header injection)
        # ============================================================
        subject = f'📋 Application Approved - {application.Fname} {application.Lname}'
        clean_subject = subject.replace('\n', '').replace('\r', '').strip()

        if not clean_subject:
            clean_subject = "ESSCO Finance - Application Approved"
            logger.warning("Subject was empty, using default")

        # ============================================================
        # ⭐ 3. VALIDATE APPLICATION EMAIL (if used in email)
        # ============================================================
        try:
            validate_email(application.email)
        except ValidationError:
            logger.warning(f"⚠️ Applicant email may be invalid: {application.email}")

        # ============================================================
        # ⭐ 4. SAFELY FORMAT CURRENCY VALUES
        # ============================================================
        def safe_currency(value):
            if value is None:
                return "N/A"
            try:
                return f"${float(value):,.2f}"
            except (ValueError, TypeError):
                return "N/A"

        # Get monthly payment based on term (with safe access)
        monthly_payment = None
        term_mapping = {
            "Six": "Six",
            "Twelve": "Twelve",
            "Eighteen": "Eighteen",
            "Twenty Four": "Twenty_Four",
            "Thirty": "Thirty",
            "Thirty Six": "Thirty_Six",
        }

        for display_term, field_name in term_mapping.items():
            if application.Term == display_term:
                amount = getattr(application, field_name, None)
                if amount:
                    monthly_payment = safe_currency(amount)
                break

        # ============================================================
        # ⭐ 5. PREPARE CONTEXT
        # ============================================================
        context = {
            'application': application,
            'applicant_name': f"{application.Fname} {application.Lname}",
            'applicant_email': application.email,
            'applicant_phone': application.Cell_Phone,
            'application_id': application.id,
            'item_name': getattr(application, 'item_name', 'N/A'),
            'sku': getattr(application, 'item_sku', 'N/A'),
            'credit_limit': safe_currency(application.Total_Credit_Allowed),
            'payment_term': application.Term or "Not specified",
            'deposit': safe_currency(application.Deposit),
            'Purchase_Value': application.Purchase_Value,
            'Financed_Amt': safe_currency(application.Financed_Amt),
            'monthly_payment': monthly_payment,
            'recipient_name': recipient_name,
            'submission_date': application.created.strftime("%B %d, %Y") if hasattr(application, 'created') and application.created else "N/A",
        }

        # ============================================================
        # ⭐ 6. RENDER TEMPLATES (Django auto-escapes by default)
        # ============================================================
        html_content = render_to_string('emails/staff_approval_notification.html', context)
        text_content = strip_tags(html_content)

        # ==============================================================================================================================================================
        # ⭐ 7. CREATE AND SEND EMAIL
        # ============================================================
        send_email_async(
            subject=clean_subject,
            body=text_content,
            to_email=recipient_email,
            html_content=html_content,  # ✅ HTML version
            email_type='STAFF_NOTIFICATION'  # ✅ Added
        )

        #email = EmailMultiAlternatives(
        #    subject=clean_subject,
        #    body=text_content,
        #    from_email=settings.DEFAULT_FROM_EMAIL,
        #    to=[recipient_email],
        #)
        #email.attach_alternative(html_content, "text/html")
        #email.send()

        logger.info(f"✅ Staff approval email sent to {recipient_email} for application {application.id}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send staff approval notification: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False



########################################################################################################################################


def send_registration_link_debug(email, set_password_url, is_new_user=True):
    """
    Send registration link email - ONLY FOR CUSTOMERS
    """
    print("=" * 60)
    print(f"🔵 send_registration_link called")
    print(f"📧 Email: {email}")
    print(f"🆕 is_new_user: {is_new_user}")
    print("=" * 60)

    # =============================================================
    # STEP 1: Check if this email belongs to a customer
    # =============================================================
    try:
        print("🔍 STEP 1: Checking user...")
        user = User.objects.get(email=email)
        print(f"✅ User found: {user.email}")
        print(f"👤 User role: '{user.role}'")

        if user.role and user.role.lower() != 'customer':
            print(f"❌ User is NOT a customer! Role is: '{user.role}'")
            logger.warning(f"Attempted to send registration link to non-customer: {email}")
            return False

        print(f"✅ User is a customer, proceeding...")

    except User.DoesNotExist:
        print(f"ℹ️ User does not exist - new user, proceeding...")
        pass
    except Exception as e:
        print(f"❌ Error checking user: {e}")
        logger.error(f"Error checking user: {e}")
        return False

    # =============================================================
    # STEP 2: Prepare email content (SAME AS WORKING FUNCTION)
    # =============================================================
    print("📝 STEP 2: Preparing email content...")
    try:
        # Define the subject FIRST
        if is_new_user:
            subject = "Complete Your Registration - ESSCO Finance"
        else:
            subject = "Reset Your Password - ESSCO Finance"

        # ✅ Sanitize subject
        clean_subject = subject.replace('\n', '').replace('\r', '').strip()
        print(f"📋 Subject: {clean_subject}")

        context = {
            'email': email,
            'set_password_url': set_password_url,
            'is_new_user': is_new_user,
            'site_name': 'Essco Finance',
            'support_email': 'support@esscofinance.com',
        }

        # Render templates
        text_content = render_to_string('emails/registration_link.txt', context)
        html_content = render_to_string('emails/registration_link.html', context)

        print(f"✅ Text content length: {len(text_content)}")
        print(f"✅ HTML content length: {len(html_content)}")

    except Exception as e:
        print(f"❌ Error rendering templates: {e}")
        logger.error(f"Error rendering templates: {e}")
        return False

    # =============================================================
    # STEP 3: Send email (EXACTLY LIKE WORKING FUNCTION)
    # =============================================================
    print("📤 STEP 3: Sending email...")
    print(f"  From: {settings.DEFAULT_FROM_EMAIL}")
    print(f"  To: {email}")

    try:
        # ✅ EXACTLY MATCH YOUR WORKING FUNCTION
        send_email_async(
            subject=clean_subject,
            body=text_content,
            to_email=email,
            html_content=html_content,
            email_type='REGISTRATION'  # ✅ Added
        )

        print("✅ Email sent successfully!")
        logger.info(f"✅ Registration link sent to {email}")
        return True

    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        logger.error(f"❌ Failed to send registration link to {email}: {e}")
        return False





def send_registration_link(email, set_password_url, is_new_user=True):
    """
    Send registration link email - ONLY FOR CUSTOMERS

    🔒 Security: Email validation, subject sanitization, role validation

    Args:
        email (str): Recipient email address
        set_password_url (str): URL for setting/resetting password
        is_new_user (bool): True for new user registration, False for password reset

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    # ============================================================
    # ⭐ 1. VALIDATE EMAIL (Prevent injection)
    # ============================================================
    try:
        validate_email(email)
    except ValidationError as e:
        logger.error(f"❌ Invalid email address: {email} - {e}")
        return False

    # ============================================================
    # ⭐ 2. SANITIZE EMAIL (Remove whitespace)
    # ============================================================
    clean_email = email.strip().lower()

    # ============================================================
    # ⭐ 3. ROLE VALIDATION (Only customers)
    # ============================================================
    try:
        user = User.objects.get(email=clean_email)

        # Only allow customers to receive registration links
        if user.role and user.role.lower() != 'customer':
            logger.warning(f"⚠️ Attempted to send registration link to non-customer: {email} (role: {user.role})")
            return False

    except User.DoesNotExist:
        # New user - will be created as customer, so it's fine
        pass
    except Exception as e:
        logger.error(f"❌ Error checking user {email}: {e}")
        return False

    # ============================================================
    # ⭐ 4. SANITIZE SUBJECT (Remove newlines)
    # ============================================================
    subject = 'Complete Your Registration - Essco Finance'
    clean_subject = subject.replace('\n', '').replace('\r', '').strip()

    if not clean_subject:
        clean_subject = 'Essco Finance - Registration'
        logger.warning("Subject was empty, using default")

    # ============================================================
    # ⭐ 5. VALIDATE AND SANITIZE SET_PASSWORD_URL
    # ============================================================
    # Ensure the URL starts with HTTPS or HTTP
    if set_password_url:
        # Basic URL validation
        if not set_password_url.startswith(('http://', 'https://')):
            logger.error(f"❌ Invalid set_password_url: {set_password_url}")
            return False

        # Remove any malicious characters from URL
        import re
        if re.search(r'[\n\r\t]', set_password_url):
            logger.error(f"❌ set_password_url contains invalid characters: {set_password_url}")
            return False
    else:
        logger.error("❌ set_password_url is empty")
        return False

    # ============================================================
    # ⭐ 6. PREPARE CONTEXT
    # ============================================================
    try:
        context = {
            'email': clean_email,
            'set_password_url': set_password_url,
            'is_new_user': is_new_user,
            'site_name': 'Essco Finance',
            'support_email': 'support@esscofinance.com',
        }

        # Render both text and HTML versions
        text_content = render_to_string('emails/registration_link.txt', context)
        html_content = render_to_string('emails/registration_link.html', context)

    except Exception as e:
        logger.error(f"❌ Error rendering email templates for {email}: {e}")
        return False

    # ============================================================
    # ⭐ 7. SEND EMAIL (Hardcoded sender, no user CC/BCC)
    # ============================================================
    try:
        email_message = EmailMultiAlternatives(
            subject=clean_subject,  # ✅ Sanitized
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,  # ✅ Hardcoded
            to=[clean_email],  # ✅ Validated
            # ⭐ NO CC or BCC from user input!
        )

        # Attach HTML version
        email_message.attach_alternative(html_content, "text/html")

        # Send the email
        email_message.send()

        logger.info(f"✅ Registration link sent to {clean_email} (new_user={is_new_user})")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send registration link to {email}: {e}")
        return False






def send_registration_link1(email, set_password_url, is_new_user=True):
    """
    Send registration link email - ONLY FOR CUSTOMERS

    Args:
        email (str): Recipient email address
        set_password_url (str): URL for setting/resetting password
        is_new_user (bool): True for new user registration, False for password reset

    Returns:
        bool: True if email sent successfully, False otherwise
    """
    # =============================================================
    # STEP 1: Check if this email belongs to a customer
    # =============================================================
    try:
        user = User.objects.get(email=email)

        # Only allow customers to receive registration links
        if user.role and user.role.lower() != 'customer':
            logger.warning(f"Attempted to send registration link to non-customer: {email} (role: {user.role})")
            return False

    except User.DoesNotExist:
        # New user - will be created as customer, so it's fine
        pass
    except Exception as e:
        logger.error(f"Error checking user {email}: {e}")
        return False

    # =============================================================
    # STEP 2: Prepare email content
    # =============================================================
    try:
        context = {
            'email': email,
            'set_password_url': set_password_url,
            'is_new_user': is_new_user,
            'site_name': 'Essco Finance',
            'support_email': 'support@esscofinance.com',
        }

        # Render both text and HTML versions
        text_content = render_to_string('emails/registration_link.txt', context)
        html_content = render_to_string('emails/registration_link.html', context)

    except Exception as e:
        logger.error(f"Error rendering email templates for {email}: {e}")
        return False

    # =============================================================
    # STEP 3: Send email using EmailMultiAlternatives
    # =============================================================
    try:
        email_message = EmailMultiAlternatives(
            subject='Complete Your Registration - Essco Finance',
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email],
        )

        # Attach HTML version
        email_message.attach_alternative(html_content, "text/html")

        # Send the email
        email_message.send()

        logger.info(f"✅ Registration link sent to {email} (new_user={is_new_user})")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to send registration link to {email}: {e}")
        return False