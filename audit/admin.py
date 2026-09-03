from django.contrib import admin
from . import models as Essco_Models

# Register your models here.

@admin.register(Essco_Models.AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created", "user", "action", "application", "ip_address",)

    list_filter = ("action", "created",)

    search_fields = ("user__username", "description", "ip_address",)

    readonly_fields = ("created", "user", "action", "application", "description", "ip_address",)

    ordering = ("-created",)

    list_per_page = 50

    date_hierarchy = "created"