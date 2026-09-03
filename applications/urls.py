from django.urls import path
from . import views as essco

urlpatterns = [
    #DashBoard for officers
    path("staff/admin/", essco.admin_dashboard, name="admin_dashboard"),
    path("staff/adminedit/<str:pk>", essco.admin_dashboard_edit, name="admin_dashboard_edit"),
    path("staff/admindelete/<str:pk>", essco.admin_dashboard_delete, name="admin_dashboard_delete"),
    path('analytics/', essco.analytics_dashboard, name='analytics_dashboard'),
    path('team/', essco.team_page, name='team_page'),
    path('settings/', essco.settings, name='settings'),
    path('settings/maintenance/', essco.maintenance_settings, name='maintenance_settings'),
    path('loans/', essco.staff_loan_list, name='staff_loan_list'),
    path('admin/link-application/', essco.admin_link_application, name='admin_link_application'),
    path('admin/unlink-application/', essco.admin_unlink_application, name='admin_unlink_application'),
    path('test-timeout/', essco.test_timeout, name='test_timeout'),
    path('test-force-timeout/', essco.test_force_timeout, name='test_force_timeout'),
    path('staff/email-usage/', essco.email_usage_dashboard, name='email_usage_dashboard'),

    # ============================================================
    # STAFF LOAN MANAGEMENT
    # ============================================================
    path('staff/loans/', essco.staff_loan_list, name='staff_loan_list'),
    path('staff/loans/<int:loan_id>/', essco.staff_loan_detail, name='staff_loan_detail'),
    path('loans/pending/', essco.staff_loan_pending, name='staff_loan_pending'),
    path('manual-create-loan/<int:application_id>/', essco.manual_create_loan, name='manual_create_loan'),

    #Pages for customers to browse and interact
    path("apply/", essco.apply, name="apply"),
    path("location/", essco.location, name="location"),
    path("thankyou/", essco.Thank_You, name="Thank_You"),
    path("finance/", essco.finance, name="finance"),
    path("aboutus/", essco.about_us, name="about_us"),
    path("contactus/", essco.contact_us, name="contact_us"),
    path("terms/", essco.terms, name="terms"),
    path("privacy/", essco.privacy, name="privacy"),
    path("loan-calculator/", essco.loan_calculator, name="loan_calculator"),
    path("rates/", essco.rates, name="rates"),
    path("editrates/<str:pk>", essco.interest_rate_edit, name="interest_rate_edit"),

    #Customer Dashboard
    path("dash/", essco.customer_dashboard, name="customer_dashboard"),
    path("dash/apps", essco.customer_dashboard_apps, name="customer_dashboard_apps"),
    path('dashboard/link-application/', essco.link_application, name='link_application'),
    path('pay-deposit/<int:application_id>/', essco.pay_deposit, name='pay_deposit'),
    path('manual-create-loan/<int:application_id>/', essco.manual_create_loan, name='manual_create_loan'),

    # ===========================================================================================================================================
    # ✅ EMAIL PREVIEW AND SEND (Dashboard)
    # ===========================================================================================================================================
    path('dashboard/preview-email/<str:pk>/', essco.preview_approval_email, name='preview_approval_email'),
    path('dashboard/preview-initial-email/<str:pk>/', essco.preview_ap_initial_email, name='preview_ap_initial_email'),
    path('dashboard/send-email/<int:pk>/', essco.send_approval_email_view, name='send_approval_email'),

]