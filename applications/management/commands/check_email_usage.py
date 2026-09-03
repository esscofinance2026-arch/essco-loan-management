from django.core.management.base import BaseCommand
from applications.services.email_counter import EmailCounter

class Command(BaseCommand):
    help = 'Check email usage and send alerts if needed'
    
    def handle(self, *args, **options):
        usage = EmailCounter.get_usage_summary()
        
        if usage['remaining'] < 20:
            self.stdout.write(self.style.ERROR(
                f"🚨 CRITICAL: Only {usage['remaining']} emails remaining today!"
            ))
            # Send alert to staff
        elif usage['remaining'] < 50:
            self.stdout.write(self.style.WARNING(
                f"⚠️ Warning: Only {usage['remaining']} emails remaining today"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✅ {usage['used']} emails sent today ({usage['remaining']} remaining)"
            ))