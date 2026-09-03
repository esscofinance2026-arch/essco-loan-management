# payments/admin.py
from django.contrib import admin
from .models import PaymentMethod, PaymentRecord

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'method_type', 'is_active', 'requires_manual_confirmation']
    list_filter = ['method_type', 'is_active']
    search_fields = ['name']


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = [
        'receipt_number', 
        'customer', 
        'category', 
        'amount', 
        'status', 
        'created_at',
        'loan_link'
    ]
    list_filter = ['category', 'status', 'payment_method', 'created_at']
    search_fields = ['receipt_number', 'customer__username', 'customer__email', 'application__reference_number']
    readonly_fields = ['created_at', 'updated_at']  # ❌ Removed payment_date from here
    
    fieldsets = (
        ('Payment Info', {
            'fields': ('receipt_number', 'customer', 'category', 'amount', 'payment_method')
            # ❌ Removed 'payment_date' - it's auto-set
        }),
        ('Related To', {
            'fields': ('application', 'loan')
        }),
        ('Status', {
            'fields': ('status', 'confirmed_by', 'confirmed_at')
        }),
        ('Allocation', {
            'fields': ('principal_applied', 'interest_applied', 'fees_applied')
        }),
        ('Additional', {
            'fields': ('auto_create_loan', 'notes')
        }),
        ('Audit', {
            'fields': ('recorded_by', 'created_at', 'updated_at')
        }),
    )
    
    def loan_link(self, obj):
        """Display loan link in admin"""
        if obj.loan:
            return f'<a href="/admin/loans/loanproduct/{obj.loan.id}/">{obj.loan.loan_id}</a>'
        return '-'
    loan_link.allow_tags = True
    loan_link.short_description = 'Loan'