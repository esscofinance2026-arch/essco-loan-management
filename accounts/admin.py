from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from . import models as Essco_Models


@admin.register(Essco_Models.User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Custom Fields", {"fields": ("role", "customer_id")}),
    )

    list_display = ('username', 'email', 'role', 'customer_id', 'is_staff')
    search_fields = ('username', 'email', 'customer_id')

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Custom Fields", {"fields": ("role",)}),
    )


@admin.register(Essco_Models.SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'maintenance_mode', 'updated_at', 'updated_by']  # Remove maintenance_title and maintenance_message
    list_filter = ['maintenance_mode']
    search_fields = ['updated_by']
    readonly_fields = ['updated_at']

    fieldsets = (
        ('Maintenance Settings', {
            'fields': ('maintenance_mode',)
        }),
        ('Metadata', {
            'fields': ('updated_at', 'updated_by'),
            'classes': ('collapse',)
        }),
    )