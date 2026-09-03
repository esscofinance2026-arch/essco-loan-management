# helpers.py - CURRENT VERSION (Application phase only)
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from .models import ApplicationModel
from .permissions import ApplicationPermissions, CustomerPermissions
from loans.models import LoanProduct
from payments.models import PaymentRecord
from django.db.models import Sum

def get_user_applications(user):
    """
    Get all applications the user can see.

    Args:
        user: The requesting user

    Returns:
        QuerySet: Applications the user can view
    """
    # Staff and superusers can see everything
    if user.is_superuser or user.is_staff:
        return ApplicationModel.objects.all()

    # ✅ Regular users can ONLY see their own applications
    # Using the foreign key (customer) - NOT email
    return ApplicationModel.objects.filter(customer=user)

def get_user_application(app_id, user):
    """
    Get a specific application with permission checks.

    Args:
        app_id: Application ID
        user: The requesting user

    Returns:
        ApplicationModel: The application object

    Raises:
        PermissionDenied: If user doesn't have permission
        Http404: If application doesn't exist
    """
    application = get_object_or_404(ApplicationModel, id=app_id)

    # ✅ Check if user can view this application
    if not ApplicationPermissions.can_view(user, application):
        raise PermissionDenied("You don't have permission to view this application")

    return application

def get_customer_context1(user):
    """
    Get common context data for customer dashboard.
    """
    if not user.is_authenticated:
        return {}

    applications = get_user_applications(user)

    context = {
        'user_email': user.email,
        'applications': applications,
        'application_count': applications.count(),
        'has_applications': applications.exists(),
    }

    return context

def get_customer_context(user):
    """
    Get common context data for customer dashboard.
    """
    if not user.is_authenticated:
        return {}

    # Get applications
    applications = get_user_applications(user)

    # Get loans for this customer
    loans = LoanProduct.objects.filter(customer=user)
    active_loans = loans.exclude(status='PAID_OFF').exclude(status='CLOSED').count()

    # Get recent payments
    recent_payments = PaymentRecord.objects.filter(
        customer=user
    ).order_by('-created_at')[:5]

    # Get recent applications
    recent_applications = applications.order_by('-created')[:5]

    # Calculate total spent (confirmed payments only)
    total_spent = PaymentRecord.objects.filter(
        customer=user,
        status='CONFIRMED'
    ).aggregate(total=Sum('amount'))['total'] or 0

    context = {
        'user_email': user.email,
        'applications': applications,
        'application_count': applications.count(),
        'has_applications': applications.exists(),

        # Loan data
        'loans': loans,
        'active_loans': active_loans,
        'total_loans': loans.count(),

        # Payment data
        'recent_payments': recent_payments,
        'total_spent': total_spent,
        'total_payments': PaymentRecord.objects.filter(customer=user).count(),

        # Recent applications (for dashboard)
        'recent_applications': recent_applications,

        # You can add overdue payments if you have that logic
        # 'overdue_payments': calculate_overdue_payments(user),
    }

    return context