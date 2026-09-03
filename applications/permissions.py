# permissions.py - CURRENT VERSION (Application phase only)
from django.core.exceptions import PermissionDenied

class ApplicationPermissions:
    """Application-specific permissions"""
    
    @staticmethod
    def can_view(user, application):
        """✅ Check if user can view an application"""
        if not user.is_authenticated:
            return False
        
        # Superusers see everything
        if user.is_superuser:
            return True
        
        # Staff can view (but not necessarily edit)
        if user.is_staff:
            return True
        
        # ✅ Regular users can ONLY view their own applications
        # Check by customer field (foreign key)
        if hasattr(application, 'customer') and application.customer == user:
            return True
        
        # Fallback: Check by email (for older applications without customer)
        if hasattr(application, 'email') and application.email == user.email:
            return True
        
        return False
    
    @staticmethod
    def can_edit(user, application):
        """Check if user can edit an application"""
        if not user.is_authenticated:
            return False
        
        # Only staff and superusers can edit
        if user.is_superuser:
            return True
        
        # Staff can edit with restrictions
        if user.is_staff:
            # Staff can't edit their own applications
            if hasattr(application, 'created_by') and application.created_by == user:
                return False
            return True
        
        # Regular users can't edit
        return False
    
    @staticmethod
    def can_delete(user, application):
        """Check if user can delete an application"""
        # Only superusers can delete
        return user.is_superuser

class CustomerPermissions:
    """Customer-specific permissions"""
    
    @staticmethod
    def can_view_dashboard(user):
        """Check if user can view the customer dashboard"""
        if not user.is_authenticated:
            return False
        
        # Any authenticated user with an email can view dashboard
        return user.is_authenticated and bool(user.email)
    
    @staticmethod
    def can_view_applications(user):
        """Check if user can view applications"""
        if not user.is_authenticated:
            return False
        
        # Any authenticated user can view their own applications
        return user.is_authenticated