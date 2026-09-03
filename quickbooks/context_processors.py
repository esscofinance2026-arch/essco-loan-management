# quickbooks/context_processors.py
from quickbooks.models import QuickBooksToken

def quickbooks_connection(request):
    """Add QuickBooks connection status to template context"""
    is_connected = False
    
    if request.user.is_authenticated:
        is_connected = QuickBooksToken.objects.filter(user=request.user).exists()
    
    return {
        'is_connected': is_connected,
    }