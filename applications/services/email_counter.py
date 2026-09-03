# applications/services/email_counter.py

from django.utils import timezone
from datetime import timedelta
from applications.models import EmailLog

class EmailCounter:
    """Count emails sent via Django"""

    @staticmethod
    def get_today_count():
        """Get count of emails sent today"""
        today = timezone.now().date()
        return EmailLog.objects.filter(
            sent_at__date=today
        ).count()

    @staticmethod
    def get_count_for_type(email_type):
        """Get count for a specific email type today"""
        today = timezone.now().date()
        return EmailLog.objects.filter(
            sent_at__date=today,
            email_type=email_type
        ).count()

    @staticmethod
    def get_remaining(limit=300):
        """Get remaining emails for today"""
        used = EmailCounter.get_today_count()
        return max(0, limit - used)

    @staticmethod
    def is_over_limit(limit=300):
        """Check if daily limit is exceeded"""
        return EmailCounter.get_today_count() >= limit

    @staticmethod
    def get_usage_summary():
        """Get complete usage summary"""
        today = timezone.now().date()
        total = EmailCounter.get_today_count()
        remaining = EmailCounter.get_remaining()

        return {
            'used': total,
            'limit': 300,
            'remaining': remaining,
            'percentage': round((total / 300) * 100, 1),
            'by_type': {
                'APPROVAL': EmailCounter.get_count_for_type('APPROVAL'),
                'STAFF_NOTIFICATION': EmailCounter.get_count_for_type('STAFF_NOTIFICATION'),
                'APPLICATION_CONFIRMATION': EmailCounter.get_count_for_type('APPLICATION_CONFIRMATION'),
                'REGISTRATION': EmailCounter.get_count_for_type('REGISTRATION'),
                'REMINDER': EmailCounter.get_count_for_type('REMINDER'),
            }
        }