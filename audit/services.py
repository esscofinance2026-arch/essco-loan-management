# audit/services.py
from .models import AuditLog
import logging
import geocoder

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Get client IP address from request."""
    if not request:
        return None

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')

    return ip or '0.0.0.0'


def get_geo_location(ip):
    """
    Get city and country from IP address using geocoder.
    """
    if not ip or ip == '0.0.0.0' or ip.startswith('127.'):
        return {'city': 'Local', 'country': 'Localhost'}

    try:
        # ✅ Use geocoder like your login does
        g = geocoder.ip(ip)

        if g.ok:
            return {
                'city': g.city or 'Unknown',
                'country': g.country or 'Unknown'
            }
        else:
            logger.debug(f"geocoder lookup failed for IP: {ip}")
            return {'city': 'Unknown', 'country': 'Unknown'}

    except Exception as e:
        logger.error(f"Failed to get location for IP {ip}: {e}")
        return {'city': 'Unknown', 'country': 'Unknown'}


def get_location_display(ip):
    """
    Get formatted location string from IP.
    Returns: "City, Country (IP: x.x.x.x)" or "IP: x.x.x.x"
    """
    geo = get_geo_location(ip)

    if geo['city'] != 'Unknown' and geo['country'] != 'Unknown':
        return f"{geo['city']}, {geo['country']} (IP: {ip})"
    else:
        return f"IP: {ip}"


def log_action(request, user, action, application=None, loan=None, description="", ip_address=None):
    """Simple function-based audit logging."""
    try:
        # If user is a string, try to get User object
        if isinstance(user, str):
            from django.contrib.auth.models import User
            try:
                user_obj = User.objects.get(username=user)
            except User.DoesNotExist:
                user_obj = None
        else:
            user_obj = user

        # Get IP if not provided
        if not ip_address and request:
            ip_address = get_client_ip(request)

        # Create audit log entry
        audit_entry = AuditLog.objects.create(
            user=user_obj,
            action=action,
            application=application,
            loan=loan,
            description=description,
            ip_address=ip_address,
        )

        logger.info(
            f"AUDIT | Action: {action} | User: {user_obj.username if user_obj else 'Anonymous'} | "
            f"App: {application.id if application else 'None'} | IP: {ip_address}"
        )

        return audit_entry

    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        return None


class AuditService:
    """Service class for audit logging."""

    @staticmethod
    def get_client_ip(request):
        return get_client_ip(request)

    @staticmethod
    def get_geo_location(ip):
        return get_geo_location(ip)

    @staticmethod
    def get_location_display(ip):
        return get_location_display(ip)

    @staticmethod
    def log_action(request, action, application=None, description="", ip_address=None):
        """Log an action to the audit log."""
        try:
            if request and request.user.is_authenticated:
                user_obj = request.user
                username = request.user.username
            else:
                user_obj = None
                username = 'Anonymous'

            if not ip_address and request:
                ip_address = get_client_ip(request)

            audit_entry = AuditLog.objects.create(
                user=user_obj,
                action=action,
                application=application,
                description=description,
                ip_address=ip_address,
            )

            logger.info(
                f"AUDIT | Action: {action} | User: {username} | "
                f"App: {application.id if application else 'None'} | IP: {ip_address}"
            )

            return audit_entry

        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            return None

    @staticmethod
    def log_application_created(request, application):
        """Log when an application is created."""
        ip = get_client_ip(request)
        location = get_location_display(ip)

        return AuditService.log_action(
            request=request,
            action='CREATE',
            application=application,
            description=(
                f"Application created for {application.Fname} {application.Lname} "
                f"(ID: {application.ID_number}) from {location}"
            ),
            ip_address=ip
        )

    @staticmethod
    def log_email_sent(request, application, email_type='confirmation'):
        """Log when an email is sent successfully."""
        ip = get_client_ip(request)
        location = get_location_display(ip)

        return AuditService.log_action(
            request=request,
            action='EMAIL_SENT',
            application=application,
            description=(
                f"Confirmation email sent to {application.email} for "
                f"{application.Fname} {application.Lname} "
                f"(ID: {application.ID_number}) from {location}"
            ),
            ip_address=ip
        )

    @staticmethod
    def log_email_failed(request, application, error, email_type='confirmation'):
        """Log when an email fails."""
        ip = get_client_ip(request)
        location = get_location_display(ip)

        return AuditService.log_action(
            request=request,
            action='EMAIL_FAILED',
            application=application,
            description=(
                f"Confirmation email FAILED for {application.Fname} {application.Lname} "
                f"(ID: {application.ID_number}) from {location}. "
                f"Error: {str(error)}"
            ),
            ip_address=ip
        )

    @staticmethod
    def log_login(request, success=True):
        """Log user login attempts."""
        ip = get_client_ip(request)
        location = get_location_display(ip)
        user_info = AuditService.get_user_info(request)

        return AuditService.log_action(
            request=request,
            action='LOGIN',
            application=None,
            description=(
                f"{user_info['username']} ({user_info.get('role', 'No role')}) "
                f"login {'successful' if success else 'failed'} from {location}"
            ),
            ip_address=ip
        )

    @staticmethod
    def log_logout(request):
        """Log user logout."""
        ip = get_client_ip(request)
        user_info = AuditService.get_user_info(request)

        return AuditService.log_action(
            request=request,
            action='LOGOUT',
            application=None,
            description=f"{user_info['username']} logged out from IP: {ip}",
            ip_address=ip
        )

    @staticmethod
    def get_user_info(request):
        """Get standardized user information."""
        if request and request.user.is_authenticated:
            return {
                'user': request.user,
                'username': request.user.username,
                'user_id': request.user.id,
                'role': getattr(request.user, 'role', 'No role'),
                'is_authenticated': True,
            }
        return {
            'user': None,
            'username': 'Anonymous',
            'user_id': None,
            'role': None,
            'is_authenticated': False,
        }