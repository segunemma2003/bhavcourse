from datetime import timezone
import boto3
import re
from urllib.parse import urlparse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Regex to identify S3 URLs
S3_URL_PATTERN = r'^https?://(?:([^.]+)\.)?s3[.-](?:[^.]+[.-])?amazonaws\.com/(.+)$'
S3_URL_PATTERN_ALT = r'^https?://s3\.amazonaws\.com/([^/]+)/(.+)$'

def is_s3_url(url):
    """
    Determine if a URL is an S3 URL.
    
    Args:
        url (str): URL to check
        
    Returns:
        bool: True if URL is an S3 URL, False otherwise
    """
    if not url:
        return False
        
    return bool(re.match(S3_URL_PATTERN, url) or re.match(S3_URL_PATTERN_ALT, url))

def get_s3_key_and_bucket(url):
    """
    Extract bucket and key from S3 URL.
    
    Args:
        url (str): S3 URL
        
    Returns:
        tuple: (bucket_name, object_key) or (None, None) if not valid
    """
    # Check for standard S3 URL format
    match = re.match(S3_URL_PATTERN, url)
    if match:
        bucket_name = match.group(1)
        object_key = match.group(2)
        return bucket_name, object_key
        
    # Check for alternate format
    match = re.match(S3_URL_PATTERN_ALT, url)
    if match:
        bucket_name = match.group(1)
        object_key = match.group(2)
        return bucket_name, object_key
        
    # Try to parse as a URL and extract path components
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip('/').split('/')
    
    # If host includes s3 and there are path components
    if 's3' in parsed_url.netloc and len(path_parts) >= 2:
        bucket_name = path_parts[0]
        object_key = '/'.join(path_parts[1:])
        return bucket_name, object_key
        
    return None, None

def generate_presigned_url(url, expiration=3600):
    """
    Generate a pre-signed URL for an S3 object.
    
    Args:
        url (str): S3 URL
        expiration (int): Expiration time in seconds (default: 1 hour)
        
    Returns:
        str: Pre-signed URL or original URL if not an S3 URL
    """
    if not is_s3_url(url):
        return url
        
    try:
        bucket_name, object_key = get_s3_key_and_bucket(url)
        
        if not bucket_name or not object_key:
            logger.warning(f"Could not extract bucket and key from S3 URL: {url}")
            return url
            
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': object_key
            },
            ExpiresIn=expiration
        )
        
        return presigned_url
    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}")
        return url
    
class ProfilePictureStorageHandler:
    """
    Backend handler for different storage systems
    """
    
    @staticmethod
    def save_to_s3(file_content, filename, user_id):
        """Save file directly to S3 with custom metadata"""
        try:
            from django.conf import settings
            import boto3
            
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
            
            # Upload with metadata
            s3_client.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=filename,
                Body=file_content,
                ContentType='image/jpeg',
                Metadata={
                    'user_id': str(user_id),
                    'upload_timestamp': str(timezone.now().timestamp())
                },
                ACL='private'  # Ensure privacy
            )
            
            return f"s3://{settings.AWS_STORAGE_BUCKET_NAME}/{filename}"
            
        except Exception as e:
            logger.error(f"S3 upload failed: {str(e)}")
            raise
    
    @staticmethod
    def delete_from_s3(file_path):
        """Delete file from S3"""
        try:
            if file_path.startswith('s3://'):
                # Extract bucket and key from S3 path
                path_parts = file_path.replace('s3://', '').split('/', 1)
                bucket = path_parts[0]
                key = path_parts[1]
                
                from django.conf import settings
                import boto3
                
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
                
                s3_client.delete_object(Bucket=bucket, Key=key)
                logger.info(f"Deleted from S3: {file_path}")
        except Exception as e:
            logger.error(f"S3 deletion failed: {str(e)}")