# loans/admin.py
from django.contrib import admin
from django.utils.html import format_html
from decimal import Decimal
from .models import LoanProduct, PaymentSchedule, LoanFee, LoanNote, LoanStatusHistory, CollectionActivity

@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = [
        'loan_id', 
        'customer', 
        'display_principal', 
        'display_outstanding',  # ✅ Changed from 'outstanding_balance'
        'display_deposit',      # ✅ Added deposit display
        'status', 
        'created_at',
        'quickbooks_sync_status'
    ]
    list_filter = ['status', 'creation_method', 'created_at']
    search_fields = ['loan_id', 'customer__username', 'customer__email', 'application__reference_number']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Identification', {
            'fields': ('loan_id', 'customer', 'application')
        }),
        ('Deposit Information', {
            'fields': ('deposit_paid', 'deposit_paid_date', 'deposit_payment_method', 
                      'deposit_receipt_number', 'deposit_payment')
        }),
        ('Loan Terms', {
            'fields': ('principal_amount', 'interest_rate', 'tenure_months', 'monthly_installment')
        }),
        ('Financial Status', {
            'fields': ('total_interest', 'total_payable', 'outstanding_balance', 'total_paid')
        }),
        ('Dates', {
            'fields': ('start_date', 'first_payment_date', 'maturity_date')
        }),
        ('Status', {
            'fields': ('status', 'creation_method')
        }),
        ('QuickBooks', {
            'fields': ('quickbooks_customer_id', 'quickbooks_invoice_id', 'quickbooks_synced_at')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    # ✅ Add these methods to display calculated values
    def display_principal(self, obj):
        return f"${obj.principal_amount:,.2f}"
    display_principal.short_description = "Principal"
    
    def display_outstanding(self, obj):
        """Display outstanding principal using the property"""
        # Use the outstanding_principal property
        return f"${obj.outstanding_principal:,.2f}"
    display_outstanding.short_description = "Outstanding Principal"
    
    def display_deposit(self, obj):
        """Display deposit progress"""
        return f"${obj.deposit_paid:,.2f} / ${obj.deposit_target:,.2f}"
    display_deposit.short_description = "Deposit Paid / Target"
    
    def quickbooks_sync_status(self, obj):
        """Display QuickBooks sync status"""
        if obj.quickbooks_customer_id:
            return format_html(
                '<span style="color: green;">✅ Synced</span><br>'
                '<small>Customer: {}</small><br>'
                '<small>Invoice: {}</small>',
                obj.quickbooks_customer_id,
                obj.quickbooks_invoice_id or 'N/A'
            )
        return format_html('<span style="color: orange;">⏳ Not Synced</span>')
    quickbooks_sync_status.short_description = 'QuickBooks'


@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ['loan', 'installment_number', 'due_date', 'total_due', 'total_paid', 'status']
    list_filter = ['status', 'due_date']
    search_fields = ['loan__loan_id', 'loan__customer__username']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LoanFee)
class LoanFeeAdmin(admin.ModelAdmin):
    list_display = ['loan', 'fee_type', 'amount', 'due_date', 'is_paid', 'is_waived']
    list_filter = ['fee_type', 'is_paid', 'is_waived']
    search_fields = ['loan__loan_id', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LoanNote)
class LoanNoteAdmin(admin.ModelAdmin):
    list_display = ['loan', 'note_type', 'is_internal', 'created_at', 'created_by']
    list_filter = ['note_type', 'is_internal']
    search_fields = ['loan__loan_id', 'content']


@admin.register(LoanStatusHistory)
class LoanStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['loan', 'previous_status', 'new_status', 'changed_at', 'changed_by']
    list_filter = ['previous_status', 'new_status']
    search_fields = ['loan__loan_id']


@admin.register(CollectionActivity)
class CollectionActivityAdmin(admin.ModelAdmin):
    list_display = ['loan', 'activity_type', 'contact_status', 'created_at', 'created_by']
    list_filter = ['activity_type', 'contact_status']
    search_fields = ['loan__loan_id', 'summary']