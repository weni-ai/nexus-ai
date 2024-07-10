from django.utils.deprecation import MiddlewareMixin


class SwaggerXFrameOptionsMiddleware(MiddlewareMixin):
    def __init__(self, get_response):
        self.get_response = get_response

    def process_response(self, request, response):
        if request.path == '/':
            response['X-Frame-Options'] = 'SAMEORIGIN'

        response = self.get_response(request)
        return response
