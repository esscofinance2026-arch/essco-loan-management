from django.shortcuts import render
from accounts.models import SiteSettings


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # default safe fallback
        maintenance_mode = False

        settings = SiteSettings.objects.first()
        if settings:
            maintenance_mode = settings.maintenance_mode

        exempt_urls = (
            "/admin/",
            "/login/",
            "/static/",
            "/media/",
        )

        # ALWAYS allow exempt URLs
        if request.path.startswith(exempt_urls):
            return self.get_response(request)

        if maintenance_mode:

            # allow superuser
            if request.user.is_authenticated and request.user.is_superuser:
                return self.get_response(request)

            # allow staff roles
            if request.user.is_authenticated and request.user.role in ["admin", "manager", "officer"]:
                return self.get_response(request)

            # block everyone else
            return render(request, "maintenance.html")

        # IMPORTANT: normal request flow
        return self.get_response(request)