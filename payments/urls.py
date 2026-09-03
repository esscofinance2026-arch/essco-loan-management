# payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Admin Payment Management
    path('admin/payments/', views.admin_payments_list, name='admin_payments_list'),
    path('admin/payments/<int:payment_id>/', views.admin_payment_detail, name='admin_payment_detail'),
    path('admin/pending/', views.admin_pending_payments, name='admin_pending_payments'),
    path('admin/confirm/<int:payment_id>/', views.admin_confirm_payment, name='admin_confirm_payment'),
    path('admin/reject/<int:payment_id>/', views.admin_reject_payment, name='admin_reject_payment'),
    # Payment Reversal
    path('admin/reverse/<int:payment_id>/', views.admin_reverse_payment, name='admin_reverse_payment'),
    # Loan Repair
    #path('admin/loan-repair/<int:loan_id>/', views.admin_loan_repair, name='admin_loan_repair'),
    #path('admin/repair-loan/<int:loan_id>/', views.admin_repair_loan, name='admin_repair_loan'),
    path('admin/reminder/<int:schedule_id>/', views.send_manual_reminder, name='send_manual_reminder'),
    # Manual Depsoit
    path('admin/record-cash-deposit/<int:application_id>/', views.admin_record_payment, name='admin_record_payment'),
    path('payment/<int:payment_id>/un-reverse/', views.admin_un_reverse_payment, name='admin_un_reverse_payment'),
]