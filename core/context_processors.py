from dashboard.models import BoutiqueSettings
from .security_flags import live_security_enabled


def boutique_settings(request):
    return {"boutique_settings": BoutiqueSettings.get_solo(), "live_security_enabled": live_security_enabled()}
