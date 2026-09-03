# payments/context_processors.py
from .models import PaymentRecord

def pending_payment_count(request):
    """
    Context processor to add pending payment count to all templates
    """
    if request.user.is_authenticated and request.user.is_staff:
        return {
            'pending_payments_count': PaymentRecord.objects.filter(status='PENDING').count()
        }
    return {}