import json
import re
from django.utils.deprecation import MiddlewareMixin
from .s3_utils import is_s3_url, generate_presigned_url

class S3PresignedURLMiddleware(MiddlewareMixin):
    """
    Middleware to transform S3 URLs to presigned URLs in API responses.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # URL patterns to match for API endpoints that might contain video URLs
        self.api_url_patterns = [
            r'^/api/courses/',
            r'^/api/curriculum/',
        ]
    
    def is_api_request(self, request):
        """Check if this is an API request that might contain video URLs"""
        path = request.path_info
        return any(re.match(pattern, path) for pattern in self.api_url_patterns)
    
    def process_response(self, request, response):
        """Process the response and replace S3 URLs with presigned URLs"""
        # Only process JSON responses from API endpoints
        if (not self.is_api_request(request) or 
            'application/json' not in response.get('Content-Type', '')):
            return response
            
        try:
            # Parse and possibly modify the response content
            content = response.content.decode('utf-8')
            data = json.loads(content)
            
            # Process the data to replace S3 URLs with presigned URLs
            processed_data = self.process_data(data)
            
            # Update the response with the processed data
            response.content = json.dumps(processed_data).encode('utf-8')
            
        except (UnicodeDecodeError, json.JSONDecodeError, Exception):
            # If any error occurs, just return the original response
            pass
            
        return response
    
    def process_data(self, data):
        """Recursively process data to replace S3 URLs with presigned URLs"""
        if isinstance(data, dict):
            # Process dictionary
            for key, value in data.items():
                # Check if this field might contain a video URL
                if key in ('video_url', 'presigned_video_url'):
                    if isinstance(value, str) and is_s3_url(value):
                        data[key] = generate_presigned_url(value)
                else:
                    # Recursively process nested structures
                    data[key] = self.process_data(value)
                    
        elif isinstance(data, list):
            # Process lists recursively
            data = [self.process_data(item) for item in data]
            
        return data