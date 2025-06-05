from django.core.cache import cache
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

class CacheMixin:
    """Mixin for intelligent caching"""
    
    def get_cache_timeout(self):
        """Different timeouts for different data types"""
        if self.action == 'list':
            return 3600  # 1 hour for lists
        elif self.action == 'retrieve':
            return 1800  # 30 minutes for details
        return 300  # 5 minutes default
    
    def get_cache_key_prefix(self):
        return f"{self.__class__.__name__.lower()}_{self.action}"
    
    @method_decorator(cache_page(60 * 60))  # Cache view for 1 hour
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)