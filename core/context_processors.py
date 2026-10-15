from dashboard.models import BoutiqueSettings
from .security_flags import live_security_enabled


def boutique_settings(request):
    from dashboard.security_views import authorized
    return {"boutique_settings": BoutiqueSettings.get_solo(), "live_security_enabled": live_security_enabled(), "can_view_live_security": live_security_enabled() and authorized(request.user)}
