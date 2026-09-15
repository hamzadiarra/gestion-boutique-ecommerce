from django import template
from dashboard.finance_services import liquidites

register = template.Library()


@register.inclusion_tag("dashboard/finance/_liquidites.html")
def financial_liquidity():
    return liquidites()


@register.inclusion_tag("dashboard/clotures/_dashboard.html")
def financial_closures():
    from dashboard.cloture_services import indicateurs_clotures
    return indicateurs_clotures()
