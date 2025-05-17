import boto3
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.conf import settings
from botocore.exceptions import ClientError, NoCredentialsError
import logging

# Fixed imports - using absolute import for s3_utils
from core.s3_utils import (
    check_s3_connectivity, 
    debug_s3_url_parsing, 
    get_s3_key_and_bucket, 
    is_s3_url, 
    generate_presigned_url
)

logger = logging.getLogger(__name__)

class S3DebugView(APIView):
    """
    Debug endpoint to test S3 configuration and URL generation.
    Only accessible to admin users.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]
    
    def post(self, request, *args, **kwargs):
        """
        Debug S3 configuration and URL handling.
        
        Request body:
        {
            "action": "test_connectivity" | "test_url" | "list_objects",
            "url": "s3_url_here",  # for test_url action
            "bucket": "bucket_name",  # for list_objects action
            "prefix": "path/prefix/"  # optional, for list_objects action
        }
        """
        action = request.data.get('action', 'test_connectivity')
        
        if action == 'test_connectivity':
            return self._test_connectivity()
        elif action == 'test_url':
            url = request.data.get('url')
            if not url:
                return Response(
                    {"error": "URL is required for test_url action"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return self._test_url(url)
        elif action == 'list_objects':
            bucket = request.data.get('bucket')
            prefix = request.data.get('prefix', '')
            if not bucket:
                return Response(
                    {"error": "Bucket name is required for list_objects action"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return self._list_objects(bucket, prefix)
        else:
            return Response(
                {"error": f"Unknown action: {action}"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _test_connectivity(self):
        """Test basic S3 connectivity and configuration."""
        # Check AWS settings
        aws_settings = {
            'AWS_ACCESS_KEY_ID': bool(getattr(settings, 'AWS_ACCESS_KEY_ID', None)),
            'AWS_SECRET_ACCESS_KEY': bool(getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)),
            'AWS_REGION': getattr(settings, 'AWS_REGION', None),
            'S3_URL_EXPIRATION': getattr(settings, 'S3_URL_EXPIRATION', 3600)
        }
        
        # Test connectivity
        connectivity_result = check_s3_connectivity()
        
        return Response({
            'aws_settings': aws_settings,
            'connectivity_test': connectivity_result
        })
    
    def _test_url(self, url):
        """Test URL parsing and presigned URL generation."""
        # Parse URL
        debug_info = debug_s3_url_parsing(url)
        bucket_name, object_key = get_s3_key_and_bucket(url)
        
        result = {
            'original_url': url,
            'debug_info': debug_info,
            'bucket_name': bucket_name,
            'object_key': object_key
        }
        
        # Try to generate presigned URL
        if bucket_name and object_key:
            try:
                # Check if object exists
                s3_client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION
                )
                
                # Check object existence
                try:
                    head_response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
                    result['object_exists'] = True
                    result['object_size'] = head_response.get('ContentLength')
                    result['last_modified'] = head_response.get('LastModified')
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        result['object_exists'] = False
                        result['error'] = f"Object not found: s3://{bucket_name}/{object_key}"
                    else:
                        result['object_exists'] = False
                        result['error'] = f"Error checking object: {e}"
                
                # Generate presigned URL
                presigned_url = generate_presigned_url(url, 3600)
                result['presigned_url'] = presigned_url
                result['presigned_url_generated'] = presigned_url != url
                
                # Test the presigned URL (make a HEAD request)
                if presigned_url != url:
                    import requests
                    try:
                        head_response = requests.head(presigned_url, timeout=10)
                        result['presigned_url_test'] = {
                            'status_code': head_response.status_code,
                            'accessible': head_response.status_code == 200,
                            'headers': dict(head_response.headers)
                        }
                    except Exception as e:
                        result['presigned_url_test'] = {
                            'error': str(e),
                            'accessible': False
                        }
                
            except Exception as e:
                result['error'] = f"Error testing URL: {str(e)}"
        
        return Response(result)
    
    def _list_objects(self, bucket_name, prefix=''):
        """List objects in S3 bucket with given prefix."""
        try:
            s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION
            )
            
            # List objects
            response = s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix,
                MaxKeys=20  # Limit to first 20 objects
            )
            
            objects = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    objects.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                        'url': f"s3://{bucket_name}/{obj['Key']}",
                        'https_url': f"https://{bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{obj['Key']}"
                    })
            
            return Response({
                'bucket': bucket_name,
                'prefix': prefix,
                'object_count': len(objects),
                'objects': objects,
                'is_truncated': response.get('IsTruncated', False)
            })
            
        except ClientError as e:
            return Response({
                'error': f"AWS Error: {e.response['Error']['Message']}",
                'code': e.response['Error']['Code']
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': f"Error listing objects: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class GeneratePresignedURLView(APIView):
    """
    Generate a presigned URL for a protected S3 resource.
    Enhanced with better error handling and validation.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        """
        Generate a presigned URL for the given S3 URL.
        
        Request body:
        {
            "url": "https://bucket-name.s3.amazonaws.com/path/to/video.mp4",
            "expiration": 3600  # Optional, defaults to settings.S3_URL_EXPIRATION
        }
        
        Response:
        {
            "success": true,
            "presigned_url": "https://...",
            "expires_in_seconds": 3600,
            "bucket_name": "bucket-name",
            "object_key": "path/to/video.mp4"
        }
        """
        url = request.data.get('url')
        if not url:
            return Response(
                {"error": "URL is required", "success": False},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify the URL is an S3 URL
        if not is_s3_url(url):
            return Response(
                {"error": "Not a valid S3 URL", "success": False, "url": url},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract bucket and key
        bucket_name, object_key = get_s3_key_and_bucket(url)
        if not bucket_name or not object_key:
            return Response(
                {
                    "error": "Could not parse bucket and key from URL",
                    "success": False,
                    "url": url
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get expiration from request or use default
        expiration = request.data.get('expiration', getattr(settings, 'S3_URL_EXPIRATION', 3600))
        try:
            expiration = int(expiration)
            if expiration <= 0 or expiration > 86400:  # Max 24 hours
                expiration = 3600
        except (ValueError, TypeError):
            expiration = 3600
        
        # Generate the presigned URL
        presigned_url = generate_presigned_url(url, expiration)
        
        # Check if generation was successful
        if presigned_url == url:
            return Response(
                {
                    "error": "Failed to generate presigned URL",
                    "success": False,
                    "original_url": url,
                    "bucket_name": bucket_name,
                    "object_key": object_key
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response({
            "success": True,
            "presigned_url": presigned_url,
            "expires_in_seconds": expiration,
            "bucket_name": bucket_name,
            "object_key": object_key,
            "original_url": url
        })