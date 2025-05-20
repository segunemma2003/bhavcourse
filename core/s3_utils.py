import boto3
import re
from urllib.parse import urlparse
from django.conf import settings
import logging
from botocore.exceptions import ClientError, NoCredentialsError

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
    Extract bucket and key from S3 URL with improved parsing.
    
    Args:
        url (str): S3 URL
        
    Returns:
        tuple: (bucket_name, object_key) or (None, None) if not valid
    """
    if not url:
        return None, None
    
    # Handle s3:// protocol URLs
    s3_protocol_match = re.match(r'^s3://([^/]+)/(.+)$', url)
    if s3_protocol_match:
        # URL decode the key (replace '+' with spaces)
        key = s3_protocol_match.group(2).replace('+', ' ')
        return s3_protocol_match.group(1), key
    
    # Handle bucket.s3.region.amazonaws.com/key format
    bucket_subdomain_match = re.match(r'^https?://([^.]+)\.s3[.-]([^.]*\.)?amazonaws\.com/(.+)$', url, re.IGNORECASE)
    if bucket_subdomain_match:
        # URL decode the key (replace '+' with spaces)
        key = bucket_subdomain_match.group(3).replace('+', ' ')
        return bucket_subdomain_match.group(1), key
    
    # Handle s3.region.amazonaws.com/bucket/key format
    path_style_match = re.match(r'^https?://s3[.-]([^.]*\.)?amazonaws\.com/([^/]+)/(.+)$', url, re.IGNORECASE)
    if path_style_match:
        # URL decode the key (replace '+' with spaces)
        key = path_style_match.group(3).replace('+', ' ')
        return path_style_match.group(2), key
    
    # Fallback: parse as URL and extract from path
    try:
        parsed_url = urlparse(url)
        
        # Check if host contains 's3'
        if 's3' in parsed_url.netloc.lower():
            # Extract bucket from subdomain if using virtual-hosted-style
            if parsed_url.netloc.endswith('.amazonaws.com'):
                netloc_parts = parsed_url.netloc.split('.')
                if netloc_parts[0] != 's3':  # bucket.s3.region.amazonaws.com
                    bucket_name = netloc_parts[0]
                    # URL decode the key (replace '+' with spaces)
                    object_key = parsed_url.path.lstrip('/').replace('+', ' ')
                    return bucket_name, object_key
                else:  # s3.region.amazonaws.com/bucket/key
                    path_parts = parsed_url.path.strip('/').split('/', 1)
                    if len(path_parts) >= 2:
                        # URL decode the key (replace '+' with spaces)
                        key = path_parts[1].replace('+', ' ')
                        return path_parts[0], key
    except Exception as e:
        logger.error(f"Error parsing S3 URL {url}: {e}")
    
    return None, None

# def generate_presigned_url(url, expiration=3600):
#     """
#     Generate a pre-signed URL for an S3 object with improved error handling.
    
#     Args:
#         url (str): S3 URL
#         expiration (int): Expiration time in seconds (default: 1 hour)
        
#     Returns:
#         str: Pre-signed URL or original URL if not an S3 URL or if error occurs
#     """
#     if not is_s3_url(url):
#         logger.warning(f"URL is not an S3 URL: {url}")
#         return url
    
#     try:
#         bucket_name, object_key = get_s3_key_and_bucket(url)
        
#         if not bucket_name or not object_key:
#             logger.warning(f"Could not extract bucket and key from S3 URL: {url}")
#             return url
        
#         # Verify AWS settings are configured
#         if not all([
#             getattr(settings, 'AWS_ACCESS_KEY_ID', None),
#             getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
#             getattr(settings, 'AWS_REGION', None)
#         ]):
#             logger.error("AWS credentials or region not properly configured")
#             return url
        
#         # Create S3 client with explicit configuration
#         s3_client = boto3.client(
#             's3',
#             aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
#             aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
#             region_name=settings.AWS_REGION
#         )
        
#         # Verify the object exists before generating presigned URL
#         try:
#             s3_client.head_object(Bucket=bucket_name, Key=object_key)
#             logger.info(f"Object exists: s3://{bucket_name}/{object_key}")
#         except ClientError as e:
#             if e.response['Error']['Code'] == '404':
#                 logger.error(f"Object not found: s3://{bucket_name}/{object_key}")
#                 return url
#             else:
#                 logger.error(f"Error checking object existence: {e}")
#                 return url
        
#         # Generate presigned URL
#         presigned_url = s3_client.generate_presigned_url(
#             'get_object',
#             Params={
#                 'Bucket': bucket_name,
#                 'Key': object_key
#             },
#             ExpiresIn=expiration
#         )
        
#         # Replace %20 with spaces in the final URL
#         presigned_url = presigned_url.replace('%20', ' ')
        
#         print(presigned_url)
#         logger.info(f"Generated presigned URL for s3://{bucket_name}/{object_key}")
#         return presigned_url
        
#     except NoCredentialsError:
#         logger.error("AWS credentials not found")
#         return url
#     except ClientError as e:
#         logger.error(f"AWS ClientError generating presigned URL: {e}")
#         return url
#     except Exception as e:
#         logger.error(f"Unexpected error generating presigned URL: {e}")
#         return url



def generate_presigned_url(url, expiration=3600):
    """
    Generate a pre-signed URL for an S3 object using AWS CLI to preserve spaces.
    
    Args:
        url (str): S3 URL
        expiration (int): Expiration time in seconds (default: 1 hour)
        
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
        
        # Use subprocess to run AWS CLI command
        import subprocess
        import os
        
        # Create the s3:// URL format with proper spaces
        s3_path = f's3://{bucket_name}/{object_key}'
        
        # Set environment variables for AWS CLI
        env = os.environ.copy()
        env['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
        env['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
        env['AWS_DEFAULT_REGION'] = settings.AWS_REGION
        
        # Create the AWS CLI command - using shell=True to handle spaces in the path
        cmd = f'aws s3 presign "{s3_path}" --region {settings.AWS_REGION} --expires-in {expiration}'
        
        # Run the command
        process = subprocess.run(
            cmd,
            shell=True,
            env=env,
            capture_output=True,
            text=True
        )
        
        if process.returncode != 0:
            logger.error(f"Error generating presigned URL with AWS CLI: {process.stderr}")
            return url
        
        # Get the output URL and strip any whitespace
        presigned_url = process.stdout.strip()
        
        print(presigned_url)
        logger.info(f"Generated presigned URL for s3://{bucket_name}/{object_key}")
        return presigned_url
        
    except Exception as e:
        logger.error(f"Unexpected error generating presigned URL: {e}")
        return url

def check_s3_connectivity():
    """
    Test S3 connectivity and permissions.
    
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
            region_name=settings.AWS_REGION
        )
        
        # List buckets (simplest test)
        response = s3_client.list_buckets()
        
        return {
            'success': True,
            'buckets': [bucket['Name'] for bucket in response.get('Buckets', [])],
            'region': settings.AWS_REGION
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

# Additional utility for debugging
def debug_s3_url_parsing(url):
    """
    Debug function to test URL parsing.
    
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
        ]
    }
    
# url = "https://bybhavaniapp.s3.ap-south-1.amazonaws.com/Anarkali+16+Panel/Chapter+1+Anarkali+Paper+Drafting.mp4"
# debug_info = debug_s3_url_parsing(url)
# print(debug_info)

# Should generate the same command as what you manually used:
# aws s3 presign "s3://bybhavaniapp/Anarkali 16 Panel/Chapter 1 Anarkali Paper Drafting.mp4" --region ap-south-1 --expires-in 3600