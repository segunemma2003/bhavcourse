import boto3
import re
from urllib.parse import urlparse
from django.conf import settings
import logging
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.client import Config
from datetime import datetime, timezone
import time
import urllib.parse

logger = logging.getLogger(__name__)

# Regex patterns to identify S3 URLs (improved)
S3_URL_PATTERNS = [
    r'^https?://([^.]+)\.s3[.-]([^.]*\.)?amazonaws\.com/(.+)$',  # bucket.s3.region.amazonaws.com/key
    r'^https?://s3[.-]([^.]*\.)?amazonaws\.com/([^/]+)/(.+)$',   # s3.region.amazonaws.com/bucket/key
    r'^s3://([^/]+)/(.+)$'  # s3://bucket/key
]

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
        
    return any(re.match(pattern, url, re.IGNORECASE) for pattern in S3_URL_PATTERNS)

def get_s3_key_and_bucket(url):
    """
    Extract bucket and key from S3 URL with improved parsing and URL decoding.
    """
    if not url:
        return None, None
    
    # First, check if this is already a presigned URL and extract the base URL
    parsed_url = urlparse(url)
    
    # Remove query parameters to get the base S3 URL
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    
    # Handle s3:// protocol URLs
    s3_protocol_match = re.match(r'^s3://([^/]+)/(.+)$', base_url)
    if s3_protocol_match:
        bucket = s3_protocol_match.group(1)
        key = urllib.parse.unquote(s3_protocol_match.group(2))
        return bucket, key
    
    # Handle bucket.s3.region.amazonaws.com/key format
    bucket_subdomain_match = re.match(r'^https?://([^.]+)\.s3[.-]([^.]*\.)?amazonaws\.com/(.+)$', base_url, re.IGNORECASE)
    if bucket_subdomain_match:
        bucket = bucket_subdomain_match.group(1)
        key = urllib.parse.unquote(bucket_subdomain_match.group(3))
        return bucket, key
    
    # Handle s3.region.amazonaws.com/bucket/key format
    path_style_match = re.match(r'^https?://s3[.-]([^.]*\.)?amazonaws\.com/([^/]+)/(.+)$', base_url, re.IGNORECASE)
    if path_style_match:
        bucket = path_style_match.group(2)
        key = urllib.parse.unquote(path_style_match.group(3))
        return bucket, key
    
    # Fallback: parse as standard URL
    try:
        if 's3' in parsed_url.netloc.lower() and parsed_url.netloc.endswith('.amazonaws.com'):
            netloc_parts = parsed_url.netloc.split('.')
            if netloc_parts[0] != 's3':  # bucket.s3.region.amazonaws.com
                bucket_name = netloc_parts[0]
                object_key = urllib.parse.unquote(parsed_url.path.lstrip('/'))
                return bucket_name, object_key
            else:  # s3.region.amazonaws.com/bucket/key
                path_parts = parsed_url.path.strip('/').split('/', 1)
                if len(path_parts) >= 2:
                    bucket = path_parts[0]
                    key = urllib.parse.unquote(path_parts[1])
                    return bucket, key
    except Exception as e:
        logger.error(f"Error parsing S3 URL {url}: {e}")
    
    return None, None

def get_credential_expiry_time(s3_client):
    """
    Get the expiry time of the current credentials if they are temporary.
    
    Args:
        s3_client: boto3 S3 client
        
    Returns:
        datetime or None: Expiry time if temporary credentials, None otherwise
    """
    try:
        # Try to get STS credentials info
        sts_client = boto3.client('sts', 
                                 aws_access_key_id=s3_client._client_config.__dict__.get('_user_provided_options', {}).get('aws_access_key_id'),
                                 aws_secret_access_key=s3_client._client_config.__dict__.get('_user_provided_options', {}).get('aws_secret_access_key'),
                                 region_name=s3_client._client_config.region_name)
        
        # Get caller identity to check if using temporary credentials
        identity = sts_client.get_caller_identity()
        
        # If using temporary credentials, the ARN will contain 'assumed-role'
        if 'assumed-role' in identity.get('Arn', ''):
            # This is a rough estimation - AWS temporary credentials from roles typically last 1 hour by default
            # In practice, you might want to implement a more sophisticated method to track this
            logger.warning("Using temporary credentials - presigned URLs may expire before requested time")
            return None  # Can't determine exact expiry without additional AWS calls
            
    except Exception as e:
        logger.debug(f"Could not determine credential type: {e}")
    
    return None

def generate_presigned_url(url, expiration=86400):
    """
    Generate a pre-signed URL for an S3 object with improved error handling and credential awareness.
    
    Args:
        url (str): S3 URL
        expiration (int): Expiration time in seconds (default: 24 hours)
        
    Returns:
        str: Pre-signed URL or original URL if not an S3 URL or if error occurs
    """
    if not is_s3_url(url):
        logger.warning(f"URL is not an S3 URL: {url}")
        return url
    
    try:
        bucket_name, object_key = get_s3_key_and_bucket(url)
        
        if not bucket_name or not object_key:
            logger.warning(f"Could not extract bucket and key from S3 URL: {url}")
            return url
        
        # Verify AWS settings are configured
        if not all([
            getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            getattr(settings, 'AWS_REGION', None)
        ]):
            logger.error("AWS credentials or region not properly configured")
            return url
        
        # Create S3 client with explicit configuration and signature version
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
            config=Config(signature_version='s3v4')  # Explicitly use v4 signatures
        )
        
        # Check if using temporary credentials and adjust expiration accordingly
        try:
            # For temporary credentials, limit expiration to maximum safe duration
            sts_client = boto3.client('sts',
                                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                                    region_name=settings.AWS_REGION)
            
            identity = sts_client.get_caller_identity()
            
            # If using temporary credentials (like IAM roles), limit expiration
            if 'assumed-role' in identity.get('Arn', ''):
                # For temporary credentials, use shorter expiration (max 12 hours)
                safe_expiration = min(expiration, 43200)  # 12 hours max
                if safe_expiration != expiration:
                    logger.warning(f"Using temporary credentials: reducing expiration from {expiration} to {safe_expiration} seconds")
                expiration = safe_expiration
                
        except Exception as e:
            logger.debug(f"Could not check credential type: {e}")
            # If we can't determine, use a safer default for potential temporary credentials
            if expiration > 43200:  # More than 12 hours
                logger.warning("Cannot determine credential type - limiting expiration to 12 hours for safety")
                expiration = 43200
        
        # Verify the object exists before generating presigned URL
        try:
            s3_client.head_object(Bucket=bucket_name, Key=object_key)
            logger.debug(f"Object exists: s3://{bucket_name}/{object_key}")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.error(f"Object not found: s3://{bucket_name}/{object_key}")
                return url
            else:
                logger.error(f"Error checking object existence: {e}")
                return url
        
        # Generate presigned URL with error handling
        try:
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': object_key
                },
                ExpiresIn=expiration
            )
            
            # Log successful generation
            logger.info(f"Generated presigned URL for s3://{bucket_name}/{object_key} with {expiration}s expiration")
            
            # Verify the URL was actually generated (not just returned as original)
            if presigned_url and presigned_url != url and 'X-Amz-Signature' in presigned_url:
                return presigned_url
            else:
                logger.error("Failed to generate valid presigned URL")
                return url
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'TokenRefreshRequired':
                logger.error("AWS token refresh required - credentials may be expired")
            else:
                logger.error(f"AWS ClientError generating presigned URL: {e}")
            return url
            
    except NoCredentialsError:
        logger.error("AWS credentials not found")
        return url
    except ClientError as e:
        logger.error(f"AWS ClientError: {e}")
        return url
    except Exception as e:
        logger.error(f"Unexpected error generating presigned URL: {e}")
        return url

def check_s3_connectivity():
    """
    Test S3 connectivity and permissions with enhanced credential checking.
    
    Returns:
        dict: Status information about S3 connectivity
    """
    try:
        # Verify AWS settings
        if not all([
            getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            getattr(settings, 'AWS_REGION', None)
        ]):
            return {
                'success': False,
                'error': 'AWS credentials or region not configured'
            }
        
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
            config=Config(signature_version='s3v4')
        )
        
        # Check credential type
        try:
            sts_client = boto3.client('sts',
                                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                                    region_name=settings.AWS_REGION)
            
            identity = sts_client.get_caller_identity()
            credential_type = "temporary" if 'assumed-role' in identity.get('Arn', '') else "permanent"
            
        except Exception:
            credential_type = "unknown"
        
        # List buckets (simplest test)
        response = s3_client.list_buckets()
        
        return {
            'success': True,
            'buckets': [bucket['Name'] for bucket in response.get('Buckets', [])],
            'region': settings.AWS_REGION,
            'credential_type': credential_type,
            'max_safe_expiration': 43200 if credential_type == "temporary" else 604800  # 12h vs 7d
        }
        
    except NoCredentialsError:
        return {
            'success': False,
            'error': 'AWS credentials not found or invalid'
        }
    except ClientError as e:
        return {
            'success': False,
            'error': f'AWS ClientError: {e.response["Error"]["Message"]}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }

def debug_s3_url_parsing(url):
    """
    Debug function to test URL parsing with enhanced information.
    
    Args:
        url (str): URL to test
        
    Returns:
        dict: Debug information
    """
    return {
        'url': url,
        'is_s3_url': is_s3_url(url),
        'bucket_and_key': get_s3_key_and_bucket(url),
        'patterns_tested': [
            {
                'pattern': pattern,
                'matches': bool(re.match(pattern, url, re.IGNORECASE))
            }
            for pattern in S3_URL_PATTERNS
        ],
        'connectivity_test': check_s3_connectivity()
    }

# Enhanced caching mechanism for presigned URLs
_presigned_url_cache = {}
_cache_duration = 3600  # 1 hour cache duration

def get_cached_presigned_url(url, expiration=86400):
    """
    Get presigned URL with caching to reduce AWS API calls.
    
    Args:
        url (str): S3 URL
        expiration (int): Expiration time in seconds
        
    Returns:
        str: Cached or newly generated presigned URL
    """
    current_time = time.time()
    cache_key = f"{url}_{expiration}"
    
    # Check if we have a valid cached URL
    if cache_key in _presigned_url_cache:
        cached_url, cached_time = _presigned_url_cache[cache_key]
        
        # If cache is still valid (within 1 hour), return cached URL
        if current_time - cached_time < _cache_duration:
            logger.debug(f"Returning cached presigned URL for {url}")
            return cached_url
        else:
            # Remove expired cache entry
            del _presigned_url_cache[cache_key]
    
    # Generate new presigned URL
    presigned_url = generate_presigned_url(url, expiration)
    
    # Cache the result if it's valid
    if presigned_url != url:  # Only cache if we got a real presigned URL
        _presigned_url_cache[cache_key] = (presigned_url, current_time)
        logger.debug(f"Cached new presigned URL for {url}")
    
    return presigned_url



def ensure_presigned_video_url(video_url):
    """Utility function to ensure any video URL is converted to presigned if it's S3"""
    if not video_url:
        return video_url
    
    if is_s3_url(video_url):
        try:
            return generate_presigned_url(video_url, expiration=43200)
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return video_url
    
    return video_url