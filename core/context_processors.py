from dashboard.models import BoutiqueSettings


def boutique_settings(request):
    return {"boutique_settings": BoutiqueSettings.get_solo()}
