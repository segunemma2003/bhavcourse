from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import CourseCurriculum
from core.s3_utils import is_s3_url

@receiver(post_save, sender=CourseCurriculum)
def handle_curriculum_save(sender, instance, created, **kwargs):
    """Optimized signal handler"""
    if created and instance.video_url and is_s3_url(instance.video_url):
        # Queue immediately without extra DB write
        from core.tasks import generate_presigned_url_async
        generate_presigned_url_async.apply_async(
            args=[instance.id],
            countdown=5,  # Reduced delay
            queue='url_generation'
        )
    elif created and instance.video_url:
        # Update non-S3 URLs in bulk later
        from core.tasks import bulk_update_non_s3_status
        bulk_update_non_s3_status.apply_async(countdown=30)