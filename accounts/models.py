from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.

class User(AbstractUser):
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('officer', 'Officer'),
        ('manager', 'Manager'),
        ('admin', 'Admin'),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='customer'
    )
    customer_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

     # Add these helper properties
    @property
    def is_customer(self):
        """Return True if user is a customer"""
        return self.role == 'customer'

    @property
    def is_officer(self):
        """Return True if user is an officer"""
        return self.role == 'officer'

    @property
    def is_manager(self):
        """Return True if user is a manager"""
        return self.role == 'manager'

    @property
    def is_admin(self):
        """Return True if user is an admin"""
        return self.role == 'admin' or self.is_superuser


class SiteSettings(models.Model):
    maintenance_mode = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Site Setting"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(id=1)
        return settings