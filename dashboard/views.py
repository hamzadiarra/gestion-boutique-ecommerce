from django.utils.translation import gettext
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q, Max
from django.db import transaction
from django.urls import reverse
from accounts.models import Profile
from accounts.decorators import admin_required
from products.models import Product
from orders.models import Order
from payments.models import Payment
from categories.models import Category
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Vente, JournalActivite, BoutiqueSettings, log_activity
from .vendeur_views import confirmer_commande, _filter_date
import json
from datetime import timedelta
from PIL import Image


@admin_required
def admin_dashboard(request):
    aujourd_hui = timezone.localdate()
    debut_mois = aujourd_hui.replace(day=1)
    # Statistiques globales
    total_produits = Product.objects.count()
    total_commandes = Order.objects.count()
    total_clients = Profile.objects.filter(role="client").count()
    total_vendeurs = Profile.objects.filter(role="vendeur").count()
    total_paiements = Payment.objects.count()

    # Chiffre d'affaires
    paiements_payes = Payment.objects.filter(statut="paye")
    chiffre_affaires = (paiements_payes.aggregate(Sum("montant"))["montant__sum"] or 0) + (Vente.objects.aggregate(Sum("montant_total"))["montant_total__sum"] or 0)
    ca_mois = (paiements_payes.filter(date_creation__date__gte=debut_mois).aggregate(Sum("montant"))["montant__sum"] or 0) + (Vente.objects.filter(date_vente__date__gte=debut_mois).aggregate(Sum("montant_total"))["montant_total__sum"] or 0)

    # CA des ventes directes (vendeurs)
    ca_ventes_directes = Vente.objects.aggregate(Sum("montant_total"))["montant_total__sum"] or 0

    # Dernières commandes
    dernieres_commandes = Order.objects.all().order_by("-date_creation")[:5]

    # Produits les plus vendus
    top_produits = Product.objects.filter(quantite_vendue__gt=0).order_by("-quantite_vendue")[:5]

    # Commandes par statut
    commandes_attente = Order.objects.filter(statut="en_attente").count()
    commandes_confirmees = Order.objects.filter(statut="confirmee").count()
    commandes_expediees = Order.objects.filter(statut="expediee").count()
    commandes_livrees = Order.objects.filter(statut="livree").count()

    # ============================
    # GESTION ADMINS, VENDEURS & CLIENTS
    # ============================

    # Liste des administrateurs
    administrateurs = Profile.objects.filter(
        Q(role="admin") | Q(utilisateur__is_staff=True) | Q(utilisateur__is_superuser=True)
    ).distinct().select_related("utilisateur")

    # Liste des vendeurs
    vendeurs = Profile.objects.filter(role="vendeur").select_related("utilisateur")

    # Liste des clients
    clients = Profile.objects.filter(role="client").select_related("utilisateur")

    # Tous les profils pour la gestion des rôles
    tous_les_profils = Profile.objects.select_related("utilisateur").all().order_by("-date_creation")

    # Ventes par vendeur (top 10)
    ventes_par_vendeur = (
        Vente.objects.values("vendeur__username")
        .annotate(
            total_ventes=Sum("montant_total"),
            nb_ventes=Count("id")
        )
        .order_by("-total_ventes")[:10]
    )

    # Dernières ventes enregistrées
    dernieres_ventes = Vente.objects.select_related("vendeur", "produit").all()[:10]

    # Journal d'activité récent
    journal_recent = JournalActivite.objects.select_related("utilisateur").all()[:20]
    activite_recent = []
    for commande in Order.objects.select_related("utilisateur").order_by("-date_creation")[:6]:
        activite_recent.append({"titre": f"Nouvelle commande #{commande.id}", "detail": f"{commande.utilisateur.username} · {commande.get_statut_display()}", "date": commande.date_creation})
    for paiement in Payment.objects.select_related("commande__utilisateur").order_by("-date_creation")[:6]:
        activite_recent.append({"titre": f"Paiement {paiement.reference or paiement.id}", "detail": f"{paiement.commande.utilisateur.username} · {paiement.get_statut_display()}", "date": paiement.date_creation})
    for profil in Profile.objects.select_related("utilisateur").order_by("-date_creation")[:4]:
        activite_recent.append({"titre": "Nouveau compte utilisateur", "detail": f"{profil.utilisateur.username} · {profil.get_role_display()}", "date": profil.date_creation})
    for event in journal_recent[:8]:
        activite_recent.append({"titre": event.get_action_display(), "detail": event.details, "date": event.date})
    activite_recent.sort(key=lambda item: item["date"], reverse=True)

    # Alertes (actions warning ou danger)
    alertes = JournalActivite.objects.filter(
        niveau__in=["warning", "danger"]
    ).select_related("utilisateur")[:10]

    nb_administrateurs = administrateurs.count()
    nb_vendeurs = vendeurs.count()
    nb_ventes_total = Vente.objects.count()
    nb_ruptures = Product.objects.filter(stock=0, actif=True).count()
    nb_stock_faible = Product.objects.filter(stock__gt=0, stock__lte=5, actif=True).count()
    nb_paiements_attente = Payment.objects.filter(statut="en_attente").count()
    nb_paiements_echoues = Payment.objects.filter(statut="echoue").count()
    paiements_recus_montant = paiements_payes.aggregate(Sum("montant"))["montant__sum"] or 0
    paiements_attente_montant = Payment.objects.filter(statut="en_attente").aggregate(Sum("montant"))["montant__sum"] or 0
    nb_commandes_bloquees = Order.objects.filter(statut="en_attente").count()

    # Événements pour le calendrier des commandes
    events = []
    for order in Order.objects.all():
        events.append({
            "title": f"Commande #{order.id} ({order.total()} FCFA)",
            "start": order.date_creation.strftime("%Y-%m-%d"),
            "url": reverse("order_detail", args=[order.id]),
            "className": "bg-success text-white border-0 p-1" if order.statut == "livree" else "bg-warning text-dark border-0 p-1"
        })

    context = {
        "total_produits": total_produits,
        "total_commandes": total_commandes,
        "total_clients": total_clients,
        "chiffre_affaires": chiffre_affaires,
        "ca_mois": ca_mois,
        "ca_ventes_directes": ca_ventes_directes,
        "dernieres_commandes": dernieres_commandes,
        "top_produits": top_produits,
        "commandes_attente": commandes_attente,
        "commandes_confirmees": commandes_confirmees,
        "commandes_expediees": commandes_expediees,
        "commandes_livrees": commandes_livrees,
        "events_json": json.dumps(events),
        # Surveillance & Utilisateurs
        "administrateurs": administrateurs,
        "nb_administrateurs": nb_administrateurs,
        "vendeurs": vendeurs,
        "clients": clients,
        "tous_les_profils": tous_les_profils,
        "nb_vendeurs": nb_vendeurs,
        "ventes_par_vendeur": ventes_par_vendeur,
        "dernieres_ventes": dernieres_ventes,
        "journal_recent": journal_recent,
        "activite_recent": activite_recent[:8],
        "alertes": alertes,
        "nb_ventes_total": nb_ventes_total,
        "total_vendeurs": total_vendeurs,
        "total_paiements": total_paiements,
        "nb_ruptures": nb_ruptures,
        "nb_stock_faible": nb_stock_faible,
        "nb_paiements_attente": nb_paiements_attente,
        "nb_paiements_echoues": nb_paiements_echoues,
        "paiements_recus_montant": paiements_recus_montant,
        "paiements_attente_montant": paiements_attente_montant,
        "nb_commandes_bloquees": nb_commandes_bloquees,
        "nb_categories": Category.objects.count(),
    }

    return render(request, "dashboard/admin_dashboard.html", context)


@admin_required
@require_POST
def changer_role_utilisateur(request, profile_id):
    """Modifie un rôle avec protection contre les verrouillages administratifs."""
    nouveau_role = request.POST.get("role", "")
    if nouveau_role not in dict(Profile.ROLE_CHOICES):
        messages.error(request, gettext("Rôle invalide."))
        return redirect("admin_utilisateur_detail", profile_id=profile_id)

    with transaction.atomic():
        profil = get_object_or_404(
            Profile.objects.select_for_update().select_related("utilisateur"),
            id=profile_id,
        )
        if profil.utilisateur_id == request.user.id:
            messages.error(request, gettext("Vous ne pouvez pas modifier votre propre rôle."))
            return redirect("admin_utilisateur_detail", profile_id=profile_id)

        ancien_role = profil.role
        if ancien_role == nouveau_role:
            messages.info(request, gettext("Le rôle est déjà celui sélectionné."))
            return redirect("admin_utilisateur_detail", profile_id=profile_id)

        if ancien_role == "admin" and nouveau_role != "admin" and profil.utilisateur.is_active:
            autres_admins = Profile.objects.select_for_update().filter(
                role="admin", utilisateur__is_active=True
            ).exclude(pk=profil.pk).count()
            autres_superusers = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=profil.utilisateur_id).exists()
            if autres_admins == 0 and not autres_superusers:
                messages.error(request, gettext("Impossible de retirer le rôle du dernier administrateur actif."))
                return redirect("admin_utilisateur_detail", profile_id=profile_id)

        profil.role = nouveau_role
        profil.save(update_fields=["role", "date_modification"])

        if not profil.utilisateur.is_superuser:
            profil.utilisateur.is_staff = nouveau_role == "admin"
            profil.utilisateur.save(update_fields=["is_staff"])

        role_labels = dict(Profile.ROLE_CHOICES)
        log_activity(
            user=request.user,
            action="autre",
            details=(
                f"Modification du rôle de {profil.utilisateur.username} : "
                f"{str(role_labels[ancien_role])} -> {str(role_labels[nouveau_role])} "
                f"({ancien_role} -> {nouveau_role})"
            ),
            request=request,
            niveau="warning",
        )
        messages.success(
            request,
            gettext("Le rôle de {username} a été mis à jour : {role}.").format(
                username=profil.utilisateur.username,
                role=str(profil.get_role_display()),
            ),
        )

    return redirect("admin_utilisateur_detail", profile_id=profile_id)


def _admin_page(request, queryset, per_page=15):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


@admin_required
def admin_utilisateurs(request):
    recherche = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    profils = Profile.objects.select_related("utilisateur").order_by("-date_creation")
    if recherche:
        profils = profils.filter(
            Q(utilisateur__username__icontains=recherche)
            | Q(utilisateur__email__icontains=recherche)
            | Q(utilisateur__first_name__icontains=recherche)
            | Q(utilisateur__last_name__icontains=recherche)
        )
    if role in dict(Profile.ROLE_CHOICES):
        profils = profils.filter(role=role)
    page_obj = _admin_page(request, profils)
    return render(request, "dashboard/admin_utilisateurs.html", {
        "page_obj": page_obj, "recherche": recherche, "role": role,
        "roles": Profile.ROLE_CHOICES,
    })


@admin_required
def admin_vendeurs(request):
    query = request.GET.copy()
    query["role"] = "vendeur"
    request.GET = query
    return admin_utilisateurs(request)


@admin_required
def admin_utilisateur_detail(request, profile_id):
    profil = get_object_or_404(Profile.objects.select_related("utilisateur"), id=profile_id)
    return render(request, "dashboard/admin_utilisateur_detail.html", {
        "profil": profil,
        "commandes": Order.objects.filter(utilisateur=profil.utilisateur).order_by("-date_creation")[:8],
        "ventes": Vente.objects.filter(vendeur=profil.utilisateur).select_related("produit")[:8],
    })


@admin_required
def admin_produits(request):
    recherche = request.GET.get("q", "").strip()
    actif = request.GET.get("actif", "")
    stock = request.GET.get("stock", "")
    produits = Product.objects.select_related("categorie").order_by("-date_creation")
    if recherche:
        produits = produits.filter(
            Q(nom__icontains=recherche)
            | Q(nom_en__icontains=recherche)
            | Q(marque__icontains=recherche)
            | Q(description__icontains=recherche)
            | Q(description_en__icontains=recherche)
        )
    if actif == "actif":
        produits = produits.filter(actif=True)
    elif actif == "inactif":
        produits = produits.filter(actif=False)
    if stock == "rupture":
        produits = produits.filter(stock=0)
    elif stock == "faible":
        produits = produits.filter(stock__gt=0, stock__lte=5)
    return render(request, "dashboard/admin_liste.html", {
        "page_obj": _admin_page(request, produits), "titre": "Produits", "kicker": "Catalogue",
        "type_liste": "produits", "recherche": recherche, "actif": actif, "stock": stock,
    })


@admin_required
def admin_categories(request):
    from categories.models import Category
    recherche = request.GET.get("q", "").strip()
    categories = Category.objects.all().order_by("nom")
    if recherche:
        categories = categories.filter(Q(nom__icontains=recherche) | Q(nom_en__icontains=recherche))
    return render(request, "dashboard/admin_liste.html", {
        "page_obj": _admin_page(request, categories), "titre": "Catégories", "kicker": "Catalogue",
        "type_liste": "categories", "recherche": recherche,
    })


@admin_required
def admin_commandes(request):
    recherche = request.GET.get("q", "").strip()
    statut = request.GET.get("statut", "")
    paiement = request.GET.get("paiement", "")
    date_debut = _filter_date(request.GET.get("date_debut", ""))
    date_fin = _filter_date(request.GET.get("date_fin", ""))
    commandes = Order.objects.select_related("utilisateur", "vendeur_confirmateur", "payment").order_by("-date_creation")
    if recherche:
        filtres = Q(utilisateur__username__icontains=recherche) | Q(utilisateur__email__icontains=recherche)
        if recherche.isdigit():
            filtres |= Q(id=int(recherche))
        commandes = commandes.filter(filtres)
    if statut in {value for value, _ in Order.STATUT_CHOICES}:
        commandes = commandes.filter(statut=statut)
    if paiement == "paye":
        commandes = commandes.filter(payment__statut="paye")
    elif paiement in {"en_attente", "echoue", "annule"}:
        commandes = commandes.filter(payment__statut=paiement)
    if date_debut:
        commandes = commandes.filter(date_creation__date__gte=date_debut)
    if date_fin:
        commandes = commandes.filter(date_creation__date__lte=date_fin)
    return render(request, "dashboard/admin_liste.html", {
        "page_obj": _admin_page(request, commandes), "titre": "Commandes", "kicker": "Opérations",
        "type_liste": "commandes", "recherche": recherche, "statut": statut, "paiement": paiement, "date_debut": date_debut, "date_fin": date_fin,
        "statuts": Order.STATUT_CHOICES,
    })


@admin_required
def admin_paiements(request):
    recherche = request.GET.get("q", "").strip()
    statut = request.GET.get("statut", "")
    methode = request.GET.get("methode", "")
    date_debut = _filter_date(request.GET.get("date_debut", ""))
    date_fin = _filter_date(request.GET.get("date_fin", ""))
    paiements = Payment.objects.select_related("commande__utilisateur", "commande__vendeur_confirmateur").order_by("-date_creation")
    if recherche:
        filtres = Q(reference__icontains=recherche) | Q(commande__utilisateur__username__icontains=recherche)
        if recherche.isdigit():
            filtres |= Q(commande_id=int(recherche))
        paiements = paiements.filter(filtres)
    if statut in {value for value, _ in Payment.STATUTS}:
        paiements = paiements.filter(statut=statut)
    if methode in {value for value, _ in Payment.METHODES}:
        paiements = paiements.filter(methode=methode)
    if date_debut:
        paiements = paiements.filter(date_creation__date__gte=date_debut)
    if date_fin:
        paiements = paiements.filter(date_creation__date__lte=date_fin)
    return render(request, "dashboard/admin_liste.html", {
        "page_obj": _admin_page(request, paiements), "titre": "Paiements", "kicker": "Finance",
        "type_liste": "paiements", "recherche": recherche, "statut": statut, "methode": methode, "date_debut": date_debut, "date_fin": date_fin,
        "statuts": Payment.STATUTS, "methodes": Payment.METHODES,
    })


@admin_required
@require_POST
def admin_commande_statut(request, commande_id):
    commande = get_object_or_404(Order, id=commande_id)
    nouveau_statut = request.POST.get("statut")
    if nouveau_statut != commande.statut:
        action = {"confirmee": "confirmer", "expediee": "expediee", "livree": "livree", "annulee": "annuler"}.get(nouveau_statut)
        if action:
            confirmer_commande(request, commande.id, action=action)
        else:
            messages.error(request, gettext("Cette transition de commande n'est pas autorisée."))
    return redirect("admin_commandes")


@admin_required
@require_POST
def admin_paiement_statut(request, paiement_id):
    paiement = get_object_or_404(Payment, id=paiement_id)
    nouveau_statut = request.POST.get("statut")
    if nouveau_statut == "paye":
        confirmer_commande(request, paiement.commande_id, action="confirmer")
    elif nouveau_statut in dict(Payment.STATUTS):
        with transaction.atomic():
            commande = Order.objects.select_for_update().get(pk=paiement.commande_id)
            paiement = Payment.objects.select_for_update().get(pk=paiement.pk)
            if paiement.statut == nouveau_statut:
                return redirect("admin_paiements")
            if paiement.statut == "paye" or commande.statut != "en_attente":
                messages.error(request, gettext("Ce paiement ne peut plus changer de statut."))
            elif nouveau_statut == "annule":
                confirmer_commande(request, commande.id, action="annuler")
            elif nouveau_statut == "echoue":
                confirmer_commande(request, commande.id, action="rejeter_paiement")
            else:
                paiement.statut = "en_attente"
                paiement.date_paiement = None
                paiement.save(update_fields=["statut", "date_paiement"])
                log_activity(request.user, "autre", f"Paiement {paiement.reference or paiement.id} remis en attente.", request, "warning")
                messages.success(request, gettext("Statut du paiement mis à jour."))
    return redirect("admin_paiements")


@admin_required
def admin_dashboard_v2(request):
    """Dashboard admin Phase 1: CA direct + paiements e-commerce payes."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    seven_days_start = today - timedelta(days=6)

    direct_sales = Vente.objects.all()
    paid_payments = Payment.objects.filter(statut="paye")

    def paid_on(day):
        return paid_payments.filter(
            Q(date_paiement__date=day)
            | Q(date_paiement__isnull=True, date_creation__date=day)
        )

    def revenue(sales, payments):
        direct_total = sales.aggregate(total=Sum("montant_total"))["total"] or 0
        web_total = payments.aggregate(total=Sum("montant"))["total"] or 0
        return direct_total + web_total

    today_sales = direct_sales.filter(date_vente__date=today)
    today_payments = paid_on(today)
    month_sales = direct_sales.filter(date_vente__date__gte=month_start)
    month_payments = paid_payments.filter(
        Q(date_paiement__date__gte=month_start)
        | Q(date_paiement__isnull=True, date_creation__date__gte=month_start)
    )
    revenue_today = revenue(today_sales, today_payments)
    revenue_month = revenue(month_sales, month_payments)
    paid_today = today_payments.aggregate(total=Sum("montant"))["total"] or 0
    operation_count_today = today_sales.count() + today_payments.count()

    chart = []
    for offset in range(7):
        day = seven_days_start + timedelta(days=offset)
        chart.append({
            "label": day.strftime("%d/%m"),
            "value": float(revenue(
                direct_sales.filter(date_vente__date=day),
                paid_on(day),
            )),
        })
    category_chart = list(direct_sales.values("produit__categorie__nom").annotate(total=Sum("montant_total")).order_by("-total")[:8])
    seller_chart = list(direct_sales.values("vendeur__username").annotate(total=Sum("montant_total")).order_by("-total")[:8])

    context = {
        "revenue_today": revenue_today,
        "revenue_month": revenue_month,
        "counter_sales_today": today_sales.count(),
        "web_orders_today": today_payments.count(),
        "paid_today": paid_today,
        "pending_payments": Payment.objects.filter(statut="en_attente").count(),
        "average_today": revenue_today / operation_count_today if operation_count_today else 0,
        "pending_orders": Order.objects.filter(statut="en_attente").count(),
        "confirmed_orders": Order.objects.filter(statut="confirmee").count(),
        "active_products": Product.objects.filter(actif=True).count(),
        "out_products": Product.objects.filter(actif=True, stock=0).count(),
        "low_products": Product.objects.filter(actif=True, stock__gt=0, stock__lte=5).count(),
        "top_products": Product.objects.filter(quantite_vendue__gt=0).select_related("categorie").order_by("-quantite_vendue")[:5],
        "recent_sales": direct_sales.select_related("vendeur", "produit").order_by("-date_vente")[:8],
        "recent_orders": Order.objects.select_related("utilisateur", "vendeur_confirmateur").order_by("-date_creation")[:8],
        "revenue_chart": chart,
        "category_chart": category_chart,
        "seller_chart": seller_chart,
    }
    return render(request, "dashboard/admin_dashboard_v2.html", context)


def _performance_period(request):
    today = timezone.localdate()
    period = request.GET.get("periode", "month")
    if period == "today":
        return period, today
    if period == "7":
        return period, today - timedelta(days=6)
    if period == "all":
        return period, None
    return "month", today.replace(day=1)


def _seller_performance_row(profile, start):
    sales = Vente.objects.filter(vendeur=profile.utilisateur)
    orders = Order.objects.filter(
        vendeur_confirmateur=profile.utilisateur,
        statut__in=["confirmee", "expediee", "livree"],
    )
    if start is not None:
        sales = sales.filter(date_vente__date__gte=start)
        orders = orders.filter(date_confirmation__date__gte=start)
    sale_totals = sales.aggregate(total=Sum("montant_total"))
    confirmed_payments = Payment.objects.filter(
        commande__in=orders,
        statut="paye",
    )
    confirmed_totals = confirmed_payments.aggregate(total=Sum("montant"))
    last_sale = sales.order_by("-date_vente").first()
    last_order = orders.order_by("-date_confirmation").first()
    last_activity = JournalActivite.objects.filter(
        utilisateur=profile.utilisateur,
    ).order_by("-date").first()
    return {
        "profile": profile,
        "sales_count": sales.count(),
        "sales_total": sale_totals["total"] or 0,
        "orders_count": orders.count(),
        "orders_total": confirmed_totals["total"] or 0,
        "cancellations": Order.objects.filter(
            vendeur_confirmateur=profile.utilisateur,
            statut="annulee",
        ).count(),
        "last_sale": last_sale,
        "last_order": last_order,
        "last_activity": last_activity,
        "operations": sales.count() + orders.count(),
    }


@admin_required
def admin_vendeurs_performance(request):
    period, start = _performance_period(request)
    rows = [
        _seller_performance_row(profile, start)
        for profile in Profile.objects.filter(role="vendeur")
        .select_related("utilisateur")
    ]
    rows.sort(key=lambda row: (row["sales_total"] + row["orders_total"], row["operations"]), reverse=True)
    return render(request, "dashboard/admin_performance.html", {
        "rows": rows,
        "period": period,
        "period_label": {"today": gettext("Aujourd'hui"), "7": gettext("7 derniers jours"), "month": gettext("Mois en cours"), "all": gettext("Tout")}[period],
    })


@admin_required
def admin_vendeur_performance_detail(request, profile_id):
    profile = get_object_or_404(
        Profile.objects.select_related("utilisateur"),
        id=profile_id,
        role="vendeur",
    )
    period, start = _performance_period(request)
    stats = _seller_performance_row(profile, start)
    sales = Vente.objects.filter(vendeur=profile.utilisateur).select_related(
        "produit", "produit__categorie"
    ).order_by("-date_vente")
    orders = Order.objects.filter(
        vendeur_confirmateur=profile.utilisateur,
        statut__in=["confirmee", "expediee", "livree"],
    ).select_related("utilisateur").order_by("-date_confirmation")
    if start is not None:
        sales = sales.filter(date_vente__date__gte=start)
        orders = orders.filter(date_confirmation__date__gte=start)
    top_products = sales.values("produit__nom").annotate(
        quantity=Sum("quantite"), total=Sum("montant_total")
    ).order_by("-quantity")[:5]
    activities = JournalActivite.objects.filter(
        utilisateur=profile.utilisateur,
    ).order_by("-date")[:10]
    return render(request, "dashboard/admin_vendeur_detail.html", {
        "profile": profile,
        "stats": stats,
        "sales": sales[:10],
        "orders": orders[:10],
        "top_products": top_products,
        "activities": activities,
        "period": period,
        "period_label": {"today": gettext("Aujourd'hui"), "7": gettext("7 derniers jours"), "month": gettext("Mois en cours"), "all": gettext("Tout")}[period],
    })


@admin_required
def admin_alertes(request):
    """Alertes dérivées des stocks, commandes, paiements et produits réels."""
    now = timezone.now()
    overdue = now - timedelta(hours=24)
    alerts = []

    for product in Product.objects.filter(actif=True, stock=0).select_related("categorie"):
        alerts.append({"level": "critique", "type": "stock", "title": "Rupture de stock", "detail": f"{product.nom} · {product.categorie.nom}", "meta": "Stock : 0", "url": f"{reverse('admin_produits')}?q={product.nom}"})
    for product in Product.objects.filter(actif=True, stock__gt=0, stock__lte=5).select_related("categorie"):
        alerts.append({"level": "attention", "type": "stock", "title": "Stock faible", "detail": f"{product.nom} · {product.categorie.nom}", "meta": f"Stock : {product.stock}", "url": f"{reverse('admin_produits')}?q={product.nom}"})
    for order in Order.objects.filter(statut="en_attente", date_creation__lt=overdue).select_related("utilisateur"):
        alerts.append({"level": "attention", "type": "commandes", "title": f"Commande #{order.id} non traitée", "detail": order.utilisateur.username, "meta": f"{order.date_creation:%d/%m/%Y %H:%M} · {order.total()} FCFA", "url": reverse("admin_commandes") + "?statut=en_attente"})
    for payment in Payment.objects.filter(statut="echoue").select_related("commande__utilisateur"):
        alerts.append({"level": "critique", "type": "paiements", "title": "Paiement échoué", "detail": f"Réf. {payment.reference or payment.id} · commande #{payment.commande_id}", "meta": f"{payment.montant} FCFA · {payment.get_methode_display()}", "url": reverse("admin_paiements") + "?statut=echoue"})
    for payment in Payment.objects.filter(statut="en_attente", date_creation__lt=overdue).select_related("commande__utilisateur"):
        alerts.append({"level": "attention", "type": "paiements", "title": "Paiement en attente", "detail": f"Réf. {payment.reference or payment.id} · commande #{payment.commande_id}", "meta": f"{payment.montant} FCFA · {payment.get_methode_display()}", "url": reverse("admin_paiements") + "?statut=en_attente"})
    for product in Product.objects.filter(actif=False).select_related("categorie"):
        alerts.append({"level": "information", "type": "catalogue", "title": "Produit inactif", "detail": f"{product.nom} · {product.categorie.nom}", "meta": "Produit masqué du catalogue", "url": reverse("admin_produits") + "?actif=inactif"})

    selected_level = request.GET.get("niveau", "")
    selected_type = request.GET.get("type", "")
    if selected_level in {"critique", "attention", "information"}:
        alerts = [alert for alert in alerts if alert["level"] == selected_level]
    if selected_type in {"stock", "commandes", "paiements", "catalogue"}:
        alerts = [alert for alert in alerts if alert["type"] == selected_type]
    counts = {level: sum(alert["level"] == level for alert in alerts) for level in ("critique", "attention", "information")}
    return render(request, "dashboard/admin_alertes.html", {"alerts": alerts, "counts": counts, "total": len(alerts), "selected_level": selected_level, "selected_type": selected_type})


@admin_required
def admin_activites(request):
    logs = JournalActivite.objects.select_related("utilisateur", "utilisateur__profile").order_by("-date")
    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    action = request.GET.get("action", "")
    niveau = request.GET.get("niveau", "")
    utilisateur = request.GET.get("utilisateur", "").strip()
    date_debut = _filter_date(request.GET.get("date_debut", ""))
    date_fin = _filter_date(request.GET.get("date_fin", ""))
    if query:
        logs = logs.filter(Q(details__icontains=query) | Q(utilisateur__username__icontains=query))
    if role in {value for value, _ in Profile.ROLE_CHOICES}:
        logs = logs.filter(utilisateur__profile__role=role)
    if action in {value for value, _ in JournalActivite.ACTION_CHOICES}:
        logs = logs.filter(action=action)
    if niveau in {value for value, _ in JournalActivite.NIVEAU_CHOICES}:
        logs = logs.filter(niveau=niveau)
    if utilisateur:
        logs = logs.filter(Q(utilisateur__username__icontains=utilisateur) | Q(utilisateur_id=utilisateur if utilisateur.isdigit() else -1))
    if date_debut:
        logs = logs.filter(date__date__gte=date_debut)
    if date_fin:
        logs = logs.filter(date__date__lte=date_fin)
    return render(request, "dashboard/admin_activites.html", {"page_obj": _admin_page(request, logs, 25), "query": query, "role": role, "action": action, "niveau": niveau, "utilisateur": utilisateur, "date_debut": date_debut, "date_fin": date_fin, "roles": Profile.ROLE_CHOICES, "actions": JournalActivite.ACTION_CHOICES, "niveaux": JournalActivite.NIVEAU_CHOICES})


@admin_required
def admin_clients(request):
    clients = Profile.objects.filter(role="client").select_related("utilisateur").annotate(
        order_count=Count("utilisateur__order", distinct=True),
        spent=Sum("utilisateur__order__payment__montant", filter=Q(utilisateur__order__payment__statut="paye")),
        last_order=Max("utilisateur__order__date_creation"),
    ).order_by("-last_order", "-id")
    query = request.GET.get("q", "").strip()
    filtre = request.GET.get("filtre", "")
    if query:
        clients = clients.filter(Q(utilisateur__username__icontains=query) | Q(utilisateur__email__icontains=query) | Q(telephone__icontains=query) | Q(utilisateur__first_name__icontains=query) | Q(utilisateur__last_name__icontains=query))
    if filtre == "commandes":
        clients = clients.filter(order_count__gt=0)
    elif filtre == "sans_commandes":
        clients = clients.filter(order_count=0)
    return render(request, "dashboard/admin_clients.html", {"page_obj": _admin_page(request, clients), "query": query, "filtre": filtre})


@admin_required
def admin_parametres(request):
    settings = BoutiqueSettings.get_solo()
    if request.method == "POST":
        settings.nom = request.POST.get("nom", "").strip() or settings.nom
        settings.telephone = request.POST.get("telephone", "").strip()
        settings.whatsapp = request.POST.get("whatsapp", "").strip()
        settings.email = request.POST.get("email", "").strip()
        settings.pays = request.POST.get("pays", "").strip()
        settings.ville = request.POST.get("ville", "").strip()
        settings.adresse = request.POST.get("adresse", "").strip()
        settings.nif = request.POST.get("nif", "").strip()
        settings.rccm = request.POST.get("rccm", "").strip()
        settings.devise = request.POST.get("devise", "FCFA").strip() or "FCFA"
        settings.livraison_active = request.POST.get("livraison_active") == "on"
        settings.message_recu = request.POST.get("message_recu", "").strip()
        settings.afficher_message_recu = request.POST.get("afficher_message_recu") == "on"
        try:
            settings.seuil_stock_faible = max(0, int(request.POST.get("seuil_stock_faible", settings.seuil_stock_faible)))
        except (TypeError, ValueError):
            messages.error(request, gettext("Le seuil de stock doit être un nombre entier."))
            return render(request, "dashboard/admin_parametres.html", {"settings": settings})
        logo = request.FILES.get("logo")
        if logo:
            if logo.size > 5 * 1024 * 1024 or getattr(logo, "content_type", "") not in {"image/jpeg", "image/png", "image/webp"}:
                messages.error(request, gettext("Le logo doit être une image JPG, PNG ou WebP de 5 Mo maximum."))
                return render(request, "dashboard/admin_parametres.html", {"settings": settings})
            try:
                with Image.open(logo) as image:
                    image.verify()
                    image_format = image.format
                logo.seek(0)
                allowed_formats = {
                    "image/jpeg": {"JPEG"},
                    "image/png": {"PNG"},
                    "image/webp": {"WEBP"},
                }
                if image_format not in allowed_formats.get(getattr(logo, "content_type", ""), set()):
                    raise ValueError("MIME mismatch")
            except (OSError, ValueError, Image.UnidentifiedImageError):
                messages.error(request, gettext("Le fichier du logo n'est pas une image valide."))
                return render(request, "dashboard/admin_parametres.html", {"settings": settings})
            settings.logo = logo
        settings.save()
        log_activity(request.user, "autre", "Paramètres de la boutique modifiés.", request, "warning")
        messages.success(request, gettext("Les paramètres de la boutique ont été mis à jour."))
        return redirect("admin_parametres")
    return render(request, "dashboard/admin_parametres.html", {"settings": settings})

