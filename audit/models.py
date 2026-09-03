from django.db import models
from django.conf import settings


# Create your models here.

class AuditLog(models.Model):
    ACTIONS = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("DELETE", "Delete"),
        ("LOGIN", "Login"),
        ("LOGOUT", "Logout"),
        ("EMAIL_SENT", "Email Sent"),
        ("EMAIL_FAILED", "Email Failed"),
        ("EMAIL", "Email"),
        ("ERROR", "Error"),
        ("PAYMENT_MADE", "Payment Made"),
        ("PAYMENT_REVERSED", "Payment Reversed"),
        ("PAYMENT_REVERSED_BY_ADMIN", "Payment Reversed by admin"),
        ("PAYMENT_REINSTATED_BY_ADMIN", "Payment Reinstated by admin"),
        ("LOAN_CREATED", "Loan Created"),
        ("LOAN_ACTIVATED", "Loan Activated"),
        ("LOAN_CLOSED", "Loan Closed"),
        ("LOAN_REPAIRED", "Loan Repaired"),
        ("HP_ACCOUNT_CREATED", "HP Account Created"),
        ("QB_SYNC_SUCCESS", "QuickBooks Sync Success"),
        ("QB_SYNC_FAILED", "QuickBooks Sync Failed"),
        ("DEPOSIT_RECEIVED", "Deposit Received"),
        ("CASH_DEPOSIT_RECORDED_BY_ADMIN", "Cash Deposit Recorded by Admin"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,)

    action = models.CharField(max_length=50, choices=ACTIONS)

    application = models.ForeignKey("applications.ApplicationModel", null=True, blank=True, on_delete=models.SET_NULL,)

    loan = models.ForeignKey("loans.LoanProduct", null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_logs')

    description = models.TextField(blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]