# payments/management/commands/send_payment_reminders.py
from datetime import timedelta
from django.core.management.base import BaseCommand
from payments.services.reminder_service import ReminderService

class Command(BaseCommand):
    help = 'Send automated payment reminders to customers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write('📋 DRY RUN MODE - No emails will be sent')
            # Show what would be sent
            from loans.models import PaymentSchedule
            from django.utils import timezone

            today = timezone.now().date()
            upcoming_date = today + timedelta(days=3)

            upcoming = PaymentSchedule.objects.filter(
                due_date=upcoming_date,
                status='PENDING'
            ).select_related('loan', 'loan__customer')

            self.stdout.write(f'📋 Would send {upcoming.count()} upcoming reminders')
            for s in upcoming:
                self.stdout.write(f'  - {s.loan.loan_id}: {s.due_date} (${s.total_due})')

            return

        # ✅ Send reminders
        self.stdout.write('📧 Sending payment reminders...')
        count = ReminderService.send_payment_reminders()
        self.stdout.write(self.style.SUCCESS(f'✅ Sent {count} reminders'))