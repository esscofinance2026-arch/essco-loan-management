from django.contrib import admin
from . import models as Essco_Models

# Register your models here.

@admin.register(Essco_Models.InterestRate)
class InterestRateAdmin(admin.ModelAdmin):
    """
    Basic admin interface for managing interest rates.
    """

    # Display these fields in the list view
    list_display = [
        'name',
        'rate',
        'min_loan_amount',
        'max_loan_amount',
        'is_active',
        'created_at',
        'updated_at',
    ]

    # Add search functionality
    search_fields = [
        'name',
        'notes',
    ]

    # Add filters in the sidebar
    list_filter = [
        'is_active',
    ]

    # Default ordering
    ordering = ['-is_active', 'rate']

    # Make these fields editable directly from the list view
    list_editable = [
        'is_active',
    ]

    # Fields to show in the edit form
    fields = [
        'name',
        'rate',
        'min_loan_amount',
        'max_loan_amount',
        'is_active',
        'notes',
        'created_by',
        'updated_by',
        'created_at',
        'updated_at',
    ]

    # Make these fields read-only in the edit form
    readonly_fields = [
        'created_at',
        'updated_at',
        'created_by',
        'updated_by',
    ]

    # Number of items to show per page
    list_per_page = 25

    # =============================================================
    # Automatically set created_by and updated_by
    # =============================================================

    def save_model(self, request, obj, form, change):
        """Set created_by on creation and updated_by on update"""
        if not change:  # New object
            obj.created_by = request.user
        else:  # Update existing object
            obj.updated_by = request.user
        obj.save()


@admin.register(Essco_Models.StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'role', 'is_approval_recipient', 'is_active']
    list_filter = ['role', 'is_approval_recipient', 'is_active']
    search_fields = ['name', 'email', 'role']
    list_editable = ['is_approval_recipient', 'is_active']

    fieldsets = (
        ('Personal Information', {
            'fields': ('name', 'email', 'role')
        }),
        ('Notification Settings', {
            'fields': ('is_approval_recipient', 'is_active'),
            'description': 'Check "Approval Recipient" to receive application approval emails'
        }),
    )

@admin.register(Essco_Models.ApplicationModel)
class ApplicationModelAdmin(admin.ModelAdmin):
    # =============================================================
    # ✅ LIST DISPLAY - Shows ID_number
    # =============================================================
    list_display = [
        'id',
        'ID_number',
        'reference_number',
        'Fname',
        'Lname',
        'email',
        'Gross_Monthly_Income',
        'Approval_Status',
        'created',
    ]

    # =============================================================
    # ✅ SEARCH FIELDS
    # =============================================================
    search_fields = [
        'ID_number',
        'reference_number',
        'Fname',
        'Lname',
        'email',
        'Cell_Phone',
    ]

    # =============================================================
    # ✅ FILTERS
    # =============================================================
    list_filter = [
        'Approval_Status',
        'Final_Approval',
        'created',
        'Employer_Type',
    ]

    # =============================================================
    # ✅ CLICKABLE LINKS
    # =============================================================
    list_display_links = ['id', 'ID_number', 'Fname', 'Lname']

    # =============================================================
    # ✅ ORDERING
    # =============================================================
    ordering = ['-created']

    # =============================================================
    # ✅ ROWS PER PAGE
    # =============================================================
    list_per_page = 50