from django.http import HttpResponse
from django.shortcuts import redirect
from . import views as Essco_Views

def unauthenticated_user(view_func):
    def wrapper_func(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(Essco_Views.Essco_Cover)
        else:
            return view_func(request, *args, **kwargs)
    return wrapper_func


def allowed_users(allowed_roles=None):
    if allowed_roles is None:
        allowed_roles = []

    def decorator(view_func):
        def wrapper_func(request, *args, **kwargs):

            # ✅ allow superusers (recommended)
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # ✅ check ALL groups
            if request.user.groups.filter(name__in=allowed_roles).exists():
                return view_func(request, *args, **kwargs)

            # ✅ Check custom role
            if hasattr(request.user, 'role'):
                if request.user.role in allowed_roles:
                    return view_func(request, *args, **kwargs)

            return redirect(Essco_Views.Unauthorized)

        return wrapper_func
    return decorator

# Convenience decorators
def customer_required(view_func):
    return allowed_users(['customer'])(view_func)

def officer_required(view_func):
    return allowed_users(['officer', 'manager', 'admin'])(view_func)

def manager_required(view_func):
    return allowed_users(['manager', 'admin'])(view_func)

def admin_required(view_func):
    return allowed_users(['admin'])(view_func)