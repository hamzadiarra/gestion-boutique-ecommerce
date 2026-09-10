from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q
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
from .models import Vente, JournalActivite, log_activity
import json


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
    """Permet à un administrateur de modifier le rôle d'un utilisateur."""
    profil = get_object_or_404(Profile.objects.select_related("utilisateur"), id=profile_id)
    nouveau_role = request.POST.get("role")

    if nouveau_role in ["admin", "vendeur", "client", "comptable"]:
        ancien_role = profil.role
        profil.role = nouveau_role

        # Sauvegarder le rôle du profil EN PREMIER
        profil.save(update_fields=["role", "date_modification"])

        # Synchroniser les permissions staff si rôle admin
        if nouveau_role == "admin":
            profil.utilisateur.is_staff = True
        elif not profil.utilisateur.is_superuser:
            profil.utilisateur.is_staff = False
        profil.utilisateur.save(update_fields=["is_staff"])

        log_activity(
            user=request.user,
            action="autre",
            details=f"Modification du rôle de {profil.utilisateur.username} : {ancien_role} -> {nouveau_role}",
            request=request,
            niveau="warning",
        )

        messages.success(
            request,
            f"Rôle de {profil.utilisateur.username} mis à jour avec succès : {profil.get_role_display()}"
        )

    return redirect("admin_dashboard")


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
    if role in {"admin", "vendeur", "client", "comptable"}:
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
        produits = produits.filter(Q(nom__icontains=recherche) | Q(marque__icontains=recherche))
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
        categories = categories.filter(nom__icontains=recherche)
    return render(request, "dashboard/admin_liste.html", {
        "page_obj": _admin_page(request, categories), "titre": "Catégories", "kicker": "Catalogue",
        "type_liste": "categories", "recherche": recherche,
    })


@admin_required
def admin_commandes(request):
    recherche = request.GET.get("q", "").strip()
    statut = request.GET.get("statut", "")
    commandes = Order.objects.select_related("utilisateur").order_by("-date_creation")
    if recherche:
        filtres = Q(utilisateur__username__icontains=recherche) | Q(utilisateur__email__icontains=recherche)
        if recherche.isdigit():
            filtres |= Q(id=int(recherche))
        commandes = commandes.filter(filtres)
    if statut in {value for value, _ in Order.STATUT_CHOICES}:
        commandes = commandes.filter(statut=statut)
    return render(request, "dashboard/admin_liste.html", {
        "page_obj": _admin_page(request, commandes), "titre": "Commandes", "kicker": "Opérations",
        "type_liste": "commandes", "recherche": recherche, "statut": statut,
        "statuts": Order.STATUT_CHOICES,
    })


@admin_required
def admin_paiements(request):
    recherche = request.GET.get("q", "").strip()
    statut = request.GET.get("statut", "")
    methode = request.GET.get("methode", "")
    paiements = Payment.objects.select_related("commande__utilisateur").order_by("-date_creation")
    if recherche:
        filtres = Q(reference__icontains=recherche) | Q(commande__utilisateur__username__icontains=recherche)
        if recherche.isdigit():
            filtres |= Q(commande_id=int(recherche))
        paiements = paiements.filter(filtres)
    if statut in {value for value, _ in Payment.STATUTS}:
        paiements = paiements.filter(statut=statut)
    if methode in {value for value, _ in Payment.METHODES}:
        paiements = paiements.filter(methode=methode)
    return render(request, "dashboard/admin_liste.html", {
        "page_obj": _admin_page(request, paiements), "titre": "Paiements", "kicker": "Finance",
        "type_liste": "paiements", "recherche": recherche, "statut": statut, "methode": methode,
        "statuts": Payment.STATUTS, "methodes": Payment.METHODES,
    })


@admin_required
@require_POST
def admin_commande_statut(request, commande_id):
    commande = get_object_or_404(Order, id=commande_id)
    nouveau_statut = request.POST.get("statut")
    if nouveau_statut in dict(Order.STATUT_CHOICES):
        ancien = commande.get_statut_display()
        commande.statut = nouveau_statut
        commande.save(update_fields=["statut"])
        log_activity(request.user, "autre", f"Commande #{commande.id} : {ancien} → {commande.get_statut_display()}", request, "warning")
        messages.success(request, f"Commande #{commande.id} mise à jour.")
    return redirect("admin_commandes")


@admin_required
@require_POST
def admin_paiement_statut(request, paiement_id):
    paiement = get_object_or_404(Payment, id=paiement_id)
    nouveau_statut = request.POST.get("statut")
    if nouveau_statut in dict(Payment.STATUTS):
        paiement.statut = nouveau_statut
        paiement.save(update_fields=["statut"])
        log_activity(request.user, "autre", f"Paiement {paiement.reference or paiement.id} : statut modifié en {paiement.get_statut_display()}", request, "warning")
        messages.success(request, "Statut du paiement mis à jour.")
    return redirect("admin_paiements")

