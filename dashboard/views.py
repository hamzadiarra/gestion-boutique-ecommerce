from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q
from accounts.models import Profile
from accounts.decorators import admin_required
from products.models import Product
from orders.models import Order
from django.contrib.auth.models import User
from .models import Vente, log_activity
from .services import revenue_periods


@admin_required
def admin_dashboard(request):
    # Statistiques globales
    total_produits = Product.objects.count()
    total_commandes = Order.objects.count()
    total_clients = User.objects.filter(is_staff=False).count()

    revenus = revenue_periods()
    chiffre_affaires = revenus["total_global"]
    ca_ventes_directes = revenus["ventes_total"]["total"] or 0

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

    nb_administrateurs = administrateurs.count()
    nb_vendeurs = vendeurs.count()
    nb_ventes_total = Vente.objects.count()

    context = {
        "total_produits": total_produits,
        "total_commandes": total_commandes,
        "total_clients": total_clients,
        "chiffre_affaires": chiffre_affaires,
        "ca_ventes_directes": ca_ventes_directes,
        "dernieres_commandes": dernieres_commandes,
        "top_produits": top_produits,
        "commandes_attente": commandes_attente,
        "commandes_confirmees": commandes_confirmees,
        "commandes_expediees": commandes_expediees,
        "commandes_livrees": commandes_livrees,
        # Surveillance & Utilisateurs
        "administrateurs": administrateurs,
        "nb_administrateurs": nb_administrateurs,
        "vendeurs": vendeurs,
        "clients": clients,
        "tous_les_profils": tous_les_profils,
        "nb_vendeurs": nb_vendeurs,
        "ventes_par_vendeur": ventes_par_vendeur,
        "dernieres_ventes": dernieres_ventes,
        "nb_ventes_total": nb_ventes_total,
    }

    return render(request, "dashboard/admin_dashboard.html", context)


@admin_required
def changer_role_utilisateur(request, profile_id):
    """Permet à un administrateur de modifier le rôle d'un utilisateur."""
    if request.method == "POST":
        profil = get_object_or_404(Profile, id=profile_id)
        nouveau_role = request.POST.get("role")

        if nouveau_role in ["admin", "vendeur", "client", "comptable"]:
            ancien_role = profil.role
            profil.role = nouveau_role

            # Sauvegarder le rôle du profil EN PREMIER
            profil.save()

            # Synchroniser les permissions staff si rôle admin
            if nouveau_role == "admin":
                profil.utilisateur.is_staff = True
            elif not profil.utilisateur.is_superuser:
                profil.utilisateur.is_staff = False
            profil.utilisateur.save()

            log_activity(
                user=request.user,
                action="autre",
                details=f"Modification du rôle de {profil.utilisateur.username} : {ancien_role} ➔ {nouveau_role}",
                request=request,
                niveau="warning"
            )

            messages.success(
                request,
                f"Rôle de {profil.utilisateur.username} mis à jour avec succès : {profil.get_role_display()}"
            )

    return redirect("admin_dashboard")
