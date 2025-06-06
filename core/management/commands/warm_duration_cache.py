from django.core.management.base import BaseCommand
from django.core.cache import cache
from core.models import CourseCurriculum
from core.utils import get_video_duration
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Pre-warm the video duration cache for all curriculum videos'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-calculation even if duration is already cached',
        )
        parser.add_argument(
            '--course-id',
            type=int,
            help='Only process videos for a specific course ID',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of videos to process in each batch (default: 50)',
        )
    
    def handle(self, *args, **options):
        force = options['force']
        course_id = options['course_id']
        batch_size = options['batch_size']
        
        # Build queryset
        queryset = CourseCurriculum.objects.filter(
            video_url__isnull=False
        ).exclude(video_url='')
        
        if course_id:
            queryset = queryset.filter(course_id=course_id)
            self.stdout.write(f"Processing videos for course ID: {course_id}")
        
        queryset = queryset.select_related('course')
        total = queryset.count()
        
        if total == 0:
            self.stdout.write(
                self.style.WARNING("No videos found to process")
            )
            return
        
        self.stdout.write(f"Found {total} videos to process")
        
        processed = 0
        skipped = 0
        errors = 0
        
        # Process in batches
        for i in range(0, total, batch_size):
            batch = queryset[i:i + batch_size]
            
            for video in batch:
                try:
                    # Check if already cached (unless force is True)
                    import hashlib
                    url_hash = hashlib.md5(video.video_url.encode()).hexdigest()
                    cache_key = f"video_duration_v3_{url_hash}"
                    
                    if not force and cache.get(cache_key) is not None:
                        skipped += 1
                        continue
                    
                    # Calculate duration
                    duration = get_video_duration(video.video_url, use_cache=True)
                    processed += 1
                    
                    # Log progress
                    if processed % 10 == 0:
                        self.stdout.write(
                            f"Processed: {processed}, Skipped: {skipped}, "
                            f"Errors: {errors}, Total: {total}"
                        )
                    
                    # Detailed logging for individual videos
                    self.stdout.write(
                        f"Video ID {video.id} ({video.course.title}): {duration} minutes",
                        ending='\r'
                    )
                    
                except Exception as e:
                    errors += 1
                    logger.error(f"Failed to process video {video.id}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error processing video ID {video.id}: {str(e)}"
                        )
                    )
        
        # Final summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(
            self.style.SUCCESS(
                f"Duration cache warming completed!\n"
                f"Processed: {processed}\n"
                f"Skipped (already cached): {skipped}\n"
                f"Errors: {errors}\n"
                f"Total: {total}"
            )
        )
        
        if errors > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{errors} videos had errors. Check logs for details."
                )
            )