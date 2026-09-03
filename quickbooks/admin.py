from django.contrib import admin
from .models import QuickBooksToken, QuickBooksSyncLog

@admin.register(QuickBooksToken)
class QuickBooksTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'realm_id', 'expires_at', 'is_expired']
    list_filter = ['created_at', 'expires_at']
    search_fields = ['user__username', 'realm_id']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(QuickBooksSyncLog)
class QuickBooksSyncLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'status', 'quickbooks_id', 'created_at', 'synced_at']
    list_filter = ['action', 'status', 'created_at']
    search_fields = ['quickbooks_id', 'error_message']
    readonly_fields = ['created_at', 'synced_at']
