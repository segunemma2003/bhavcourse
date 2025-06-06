import hashlib
import logging
import re
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

class VideoDurationExtractor:
    """
    Utility class for extracting video duration from AWS S3 URLs
    with multiple fallback methods and smart caching
    """
    
    @staticmethod
    def get_video_duration(video_url, use_cache=True):
        """
        Main method to get video duration from URL
        
        Args:
            video_url (str): The video URL (preferably S3)
            use_cache (bool): Whether to use caching
            
        Returns:
            int: Duration in minutes
        """
        if not video_url:
            return 10
        
        if use_cache:
            # Check cache first
            url_hash = hashlib.md5(video_url.encode()).hexdigest()
            cache_key = f"video_duration_v3_{url_hash}"
            cached_duration = cache.get(cache_key)
            
            if cached_duration is not None:
                return cached_duration
        
        duration = 10  # Default
        
        try:
            # Method 1: S3 metadata (fastest and most accurate if available)
            duration = VideoDurationExtractor._get_s3_metadata_duration(video_url)
            
            if duration == 10:
                # Method 2: Filename patterns
                duration = VideoDurationExtractor._extract_from_filename(video_url)
                
                if duration == 10:
                    # Method 3: File size estimation
                    duration = VideoDurationExtractor._estimate_from_filesize(video_url)
                    
                    if duration == 10:
                        # Method 4: Content-based estimation (if enabled)
                        duration = VideoDurationExtractor._advanced_duration_detection(video_url)
        
        except Exception as e:
            logger.debug(f"Duration extraction failed for {video_url}: {str(e)}")
        
        # Cache the result
        if use_cache:
            cache.set(cache_key, duration, 604800)  # Cache for 7 days
        
        return duration
    
    @staticmethod
    def _get_s3_metadata_duration(video_url):
        """Extract duration from S3 object metadata"""
        try:
            from core.s3_utils import get_s3_key_and_bucket, is_s3_url
            import boto3
            
            if not is_s3_url(video_url):
                return 10
            
            bucket_name, object_key = get_s3_key_and_bucket(video_url)
            if not bucket_name or not object_key:
                return 10
            
            # Create S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            
            # Get object metadata
            response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            metadata = response.get('Metadata', {})
            
            # Check various metadata fields
            duration_fields = [
                'duration', 'duration-minutes', 'video-duration', 'video-length',
                'length', 'runtime', 'duration_minutes', 'video_duration_minutes',
                'total-duration', 'play-time', 'media-duration'
            ]
            
            for field in duration_fields:
                if field in metadata:
                    try:
                        value = float(metadata[field])
                        
                        # Handle different time units
                        if any(x in field.lower() for x in ['second', 'sec']):
                            return max(1, int(value / 60))
                        elif any(x in field.lower() for x in ['hour', 'hr']):
                            return max(1, int(value * 60))
                        else:
                            # Assume minutes
                            return max(1, int(value))
                    except (ValueError, TypeError):
                        continue
            
            # Check tags for duration info
            try:
                tags_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=object_key)
                tags = {tag['Key']: tag['Value'] for tag in tags_response.get('TagSet', [])}
                
                for key, value in tags.items():
                    if 'duration' in key.lower() or 'length' in key.lower():
                        try:
                            duration_val = float(value)
                            if 'second' in key.lower():
                                return max(1, int(duration_val / 60))
                            else:
                                return max(1, int(duration_val))
                        except (ValueError, TypeError):
                            continue
            except Exception:
                pass  # Tags might not be accessible
            
        except Exception as e:
            logger.debug(f"S3 metadata extraction failed: {str(e)}")
        
        return 10
    
    @staticmethod
    def _extract_from_filename(video_url):
        """Extract duration from filename patterns"""
        try:
            # Comprehensive filename patterns
            patterns = [
                # Standard patterns
                r'_(\d+)min[_\.\-]',           # _15min_
                r'_(\d+)m[_\.\-]',             # _15m_
                r'-(\d+)min[_\.\-]',           # -15min-
                r'-(\d+)m[_\.\-]',             # -15m-
                r'(\d+)minutes?',              # 15minutes or 15minute
                r'(\d+)mins?',                 # 15mins or 15min
                
                # With keywords
                r'duration[_-](\d+)',          # duration_15
                r'runtime[_-](\d+)',           # runtime_15
                r'length[_-](\d+)',            # length_15
                r'time[_-](\d+)',              # time_15
                
                # Time format patterns
                r'(\d{1,2})m(\d{2})s',         # 15m30s
                r'(\d{1,2}):(\d{2})',          # 15:30
                r'(\d{1,2})\.(\d{2})',         # 15.30
                
                # Course/lesson specific
                r'lesson[_-](\d+)[_-](\d+)',   # lesson_1_15 (lesson 1, 15 minutes)
                r'module[_-](\d+)[_-](\d+)',   # module_1_15
                r'part[_-](\d+)[_-](\d+)',     # part_1_15
                
                # At end of filename
                r'(\d+)min$',                  # ends with 15min
                r'(\d+)m$',                    # ends with 15m
                r'(\d+)minutes?$',             # ends with 15minutes
            ]
            
            for pattern in patterns:
                match = re.search(pattern, video_url, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    
                    if len(groups) == 1:
                        duration = int(groups[0])
                        if 1 <= duration <= 300:  # 1-300 minutes is reasonable
                            return duration
                    
                    elif len(groups) == 2:
                        # Handle time format like 15m30s or 15:30
                        if ':' in match.group() or 'm' in match.group():
                            minutes = int(groups[0])
                            seconds = int(groups[1])
                            total_minutes = minutes + (seconds / 60)
                            if 1 <= total_minutes <= 300:
                                return int(total_minutes)
                        else:
                            # Handle lesson/module format - use second number as duration
                            duration = int(groups[1])
                            if 1 <= duration <= 300:
                                return duration
            
        except Exception as e:
            logger.debug(f"Filename pattern extraction failed: {str(e)}")
        
        return 10
    
    @staticmethod
    def _estimate_from_filesize(video_url):
        """Estimate duration from file size"""
        try:
            from core.s3_utils import get_s3_key_and_bucket, is_s3_url
            import boto3
            
            if not is_s3_url(video_url):
                return 10
            
            bucket_name, object_key = get_s3_key_and_bucket(video_url)
            if not bucket_name or not object_key:
                return 10
            
            # Create S3 client
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            
            # Get file size
            response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            content_length = response.get('ContentLength', 0)
            
            if content_length > 0:
                mb_size = content_length / (1024 * 1024)
                
                # Improved estimation based on video quality indicators in filename
                filename = object_key.lower()
                
                # Determine quality from filename
                if any(q in filename for q in ['4k', 'uhd', '2160p']):
                    # 4K video: ~80-120 MB per minute
                    estimated_minutes = max(2, int(mb_size / 100))
                elif any(q in filename for q in ['1080p', 'fhd', 'hd']):
                    # 1080p video: ~25-50 MB per minute
                    estimated_minutes = max(2, int(mb_size / 35))
                elif any(q in filename for q in ['720p', 'hd']):
                    # 720p video: ~15-30 MB per minute
                    estimated_minutes = max(2, int(mb_size / 20))
                elif any(q in filename for q in ['480p', 'sd']):
                    # 480p video: ~8-15 MB per minute
                    estimated_minutes = max(2, int(mb_size / 12))
                else:
                    # Unknown quality, use medium estimate
                    if mb_size < 50:
                        estimated_minutes = max(2, int(mb_size / 15))
                    elif mb_size < 200:
                        estimated_minutes = max(3, int(mb_size / 30))
                    else:
                        estimated_minutes = max(5, int(mb_size / 50))
                
                # Cap at reasonable limits
                return min(estimated_minutes, 180)  # Max 3 hours
            
        except Exception as e:
            logger.debug(f"File size estimation failed: {str(e)}")
        
        return 10
    
    @staticmethod
    def _advanced_duration_detection(video_url):
        """Advanced duration detection methods (optional, slower)"""
        try:
            # Only run advanced detection if explicitly enabled
            if not getattr(settings, 'ENABLE_ADVANCED_DURATION_DETECTION', False):
                return 10
            
            # Method 1: Try to use ffprobe if available
            duration = VideoDurationExtractor._ffprobe_duration(video_url)
            if duration > 10:
                return duration
            
            # Method 2: Try to extract from video file headers
            # This would require downloading part of the file
            # duration = VideoDurationExtractor._extract_from_headers(video_url)
            
        except Exception as e:
            logger.debug(f"Advanced duration detection failed: {str(e)}")
        
        return 10
    
    @staticmethod
    def _ffprobe_duration(video_url):
        """Use ffprobe to get exact duration (requires ffmpeg installation)"""
        try:
            import subprocess
            import json
            import tempfile
            import os
            
            # Only run in development or if explicitly enabled
            if not getattr(settings, 'ENABLE_FFPROBE_DURATION', False):
                return 10
            
            # Generate presigned URL
            from core.s3_utils import generate_presigned_url
            presigned_url = generate_presigned_url(video_url, 3600)
            
            if presigned_url == video_url:
                return 10
            
            # Run ffprobe with timeout
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', presigned_url
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                # Get duration from format
                if 'format' in data and 'duration' in data['format']:
                    duration_seconds = float(data['format']['duration'])
                    return max(1, int(duration_seconds / 60))
                
                # Get duration from video stream
                if 'streams' in data:
                    for stream in data['streams']:
                        if stream.get('codec_type') == 'video' and 'duration' in stream:
                            duration_seconds = float(stream['duration'])
                            return max(1, int(duration_seconds / 60))
            
        except Exception as e:
            logger.debug(f"ffprobe duration extraction failed: {str(e)}")
        
        return 10


# Convenience function for easy import
def get_video_duration(video_url, use_cache=True):
    """
    Convenience function to get video duration
    
    Usage:
        from core.utils import get_video_duration
        duration = get_video_duration("https://bucket.s3.amazonaws.com/video.mp4")
    """
    return VideoDurationExtractor.get_video_duration(video_url, use_cache)


# Management command helper
class DurationCacheWarmer:
    """Helper class to pre-warm duration cache for all videos"""
    
    @staticmethod
    def warm_all_video_durations():
        """Warm cache for all curriculum videos"""
        from core.models import CourseCurriculum
        
        videos = CourseCurriculum.objects.filter(
            video_url__isnull=False
        ).exclude(video_url='')
        
        total = videos.count()
        processed = 0
        
        logger.info(f"Starting duration cache warming for {total} videos")
        
        for video in videos:
            try:
                duration = get_video_duration(video.video_url)
                processed += 1
                
                if processed % 10 == 0:
                    logger.info(f"Processed {processed}/{total} videos")
                    
            except Exception as e:
                logger.error(f"Failed to process video {video.id}: {str(e)}")
        
        logger.info(f"Completed duration cache warming: {processed}/{total} videos processed")
        return processed