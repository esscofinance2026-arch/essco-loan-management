# poc/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.poc_dashboard, name='poc_dashboard'),
    path('step1/<int:application_id>/', views.step1_pay_deposit, name='poc_step1_pay_deposit'),
    path('step2/<int:payment_id>/', views.step2_view_payment, name='poc_step2_view_payment'),
    path('step3/<int:loan_id>/', views.step3_view_loan, name='poc_step3_view_loan'),
    path('step4/<int:loan_id>/', views.step4_push_quickbooks, name='poc_step4_push_quickbooks'),
    path('reset/', views.poc_reset, name='poc_reset'),
    path('create-loan/<int:payment_id>/', views.poc_create_loan_manual, name='poc_create_loan_manual'),
    path('my-loans/', views.my_loans, name='my_loans'),
    path('my-payments/', views.my_payments, name='my_payments'),
    path('make-payment/', views.make_payment, name='make_payment'),
    path('profile/', views.profile, name='profile'),
]