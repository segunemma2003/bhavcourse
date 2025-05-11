from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

class Command(BaseCommand):
    help = 'Setup periodic tasks for Celery Beat'

    def handle(self, *args, **kwargs):
        # Create schedule for daily tasks
        daily_schedule, created = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.DAYS,
        )
        
        # Schedule subscription expiry reminders (runs daily)
        expiry_task, created = PeriodicTask.objects.get_or_create(
            name='Check for expiring subscriptions',
            task='core.tasks.send_subscription_expiry_reminder',
            interval=daily_schedule,
            args=json.dumps([]),
            kwargs=json.dumps({}),
        )
        
        # Schedule deactivation of expired subscriptions (runs daily)
        deactivate_task, created = PeriodicTask.objects.get_or_create(
            name='Deactivate expired subscriptions',
            task='core.tasks.deactivate_expired_subscriptions',
            interval=daily_schedule,
            args=json.dumps([]),
            kwargs=json.dumps({}),
        )
        
        self.stdout.write(self.style.SUCCESS('Successfully set up periodic tasks'))