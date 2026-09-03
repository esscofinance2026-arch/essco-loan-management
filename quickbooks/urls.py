# quickbooks/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('connect/', views.connect_quickbooks, name='connect_quickbooks'),
    path('callback/', views.oauth_callback, name='quickbooks_callback'),
    path('disconnect/', views.disconnect_quickbooks, name='disconnect_quickbooks'),
    path('dashboard/', views.sync_dashboard, name='sync_dashboard'),
    path('sync/loan/<int:loan_id>/', views.sync_loan_to_quickbooks, name='sync_loan'),
    path('sync/all/', views.sync_all_loans, name='sync_all_loans'),
    path('sync/retry/<int:log_id>/', views.retry_sync, name='retry_sync'),
    path('status/', views.connection_status, name='quickbooks_status'),
    path('verify/<int:loan_id>/', views.verify_loan_sync, name='verify_loan_sync'),
    path('comparison/', views.quickbooks_comparison, name='quickbooks_comparison'),
]