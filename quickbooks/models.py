# quickbooks/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class QuickBooksToken(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='qb_token')
    access_token = models.TextField()
    refresh_token = models.TextField()
    realm_id = models.CharField(max_length=50)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def is_expired(self):
        """Check if token is expired"""
        return timezone.now() >= self.expires_at
    
    def __str__(self):
        return f"{self.user.username} - {self.realm_id}"


class QuickBooksSyncLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE_CUSTOMER', 'Create Customer'),
        ('CREATE_INVOICE', 'Create Invoice'),
        ('CREATE_PAYMENT', 'Create Payment'),
    ]
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    loan = models.ForeignKey('loans.LoanProduct', on_delete=models.SET_NULL, null=True, blank=True)
    quickbooks_id = models.CharField(max_length=100, blank=True, null=True)
    data_sent = models.JSONField()
    response_data = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, default='PENDING')
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)