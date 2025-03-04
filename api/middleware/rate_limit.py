from django_ratelimit.decorators import ratelimit
from functools import wraps
from django.http import HttpResponse

class HttpResponseTooManyRequests(HttpResponse):
    status_code = 429

def rate_limit_middleware(get_response):
    def middleware(request):
        # Apply rate limiting based on IP
        @ratelimit(key='ip', rate='100/h', method=['GET', 'POST', 'PUT', 'DELETE'])
        def check_rate_limit(request):
            return get_response(request)
        
        return get_response(request)
        try:
            response = check_rate_limit(request)
            return response if response else HttpResponseTooManyRequests()
        except:
            return HttpResponseTooManyRequests()
            
    return middleware
