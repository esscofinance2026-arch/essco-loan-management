# loans/urls.py
from django.urls import path
from . import views

app_name = 'loans'

urlpatterns = [
    # Loan Management
    path('create/<int:application_id>/', views.create_loan_from_application, name='create_loan'),
    path('<int:loan_id>/', views.loan_detail, name='loan_detail'),
    path('<int:loan_id>/activate/', views.activate_loan, name='activate_loan'),
    path('<int:loan_id>/close/', views.close_loan, name='close_loan'),
    path('<int:loan_id>/record-payment/', views.record_payment, name='record_payment'),
    path('loan/<int:loan_id>/auto-repair/', views.admin_auto_repair_loan, name='admin_auto_repair_loan'),


    path('schedule/<int:schedule_id>/edit/', views.edit_payment_schedule, name='edit_schedule'),

    # Payments
    path('<int:loan_id>/pay/', views.process_payment, name='process_payment'),
    #path('payment/<int:payment_id>/reverse/', views.reverse_payment, name='reverse_payment'),

    # QuickBooks Sync
    path('<int:loan_id>/sync/', views.sync_to_quickbooks, name='sync_to_quickbooks'),
    path('<int:loan_id>/sync-status/', views.sync_status, name='sync_status'),

    # Collections
    path('collections/', views.collections_dashboard, name='collections_dashboard'),
    path('<int:loan_id>/collection-log/', views.log_collection_activity, name='log_collection_activity'),
]