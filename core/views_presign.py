from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .s3_utils import is_s3_url, generate_presigned_url
from django.conf import settings

class GeneratePresignedURLView(APIView):
    """
    Generate a presigned URL for a protected S3 resource.
    
    This endpoint is useful for frontend JavaScript requests to get fresh
    presigned URLs when needed, such as when a video player's URL expires.
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
            "presigned_url": "https://bucket-name.s3.amazonaws.com/path/to/video.mp4?..."
        }
        """
        url = request.data.get('url')
        if not url:
            return Response(
                {"error": "URL is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify the URL is an S3 URL
        if not is_s3_url(url):
            return Response(
                {"error": "Not a valid S3 URL"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get expiration from request or use default
        expiration = request.data.get('expiration', getattr(settings, 'S3_URL_EXPIRATION', 3600))
        try:
            expiration = int(expiration)
        except (ValueError, TypeError):
            expiration = 3600
        
        # Generate the presigned URL
        presigned_url = generate_presigned_url(url, expiration)
        
        return Response({
            "presigned_url": presigned_url,
            "expires_in_seconds": expiration
        })