"""Compatible baseline CSP; full script nonces require a separate template migration."""
class ResponseSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        return response
