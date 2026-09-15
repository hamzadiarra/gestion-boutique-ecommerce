from io import BytesIO
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from categories.models import Category
from products.models import Product
from orders.models import Order
from .models import Vente, BoutiqueSettings, JournalActivite, log_activity
from payments.models import Payment
from PIL import Image


class DashboardPermissionTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("vendeur_dashboard"))
        self.assertRedirects(response, reverse("login"))

    def test_client_cannot_open_professional_spaces(self):
        User.objects.create_user("client", password="secret123")
        self.client.login(username="client", password="secret123")
        self.assertRedirects(self.client.get(reverse("vendeur_dashboard")), reverse("home"))
        self.assertRedirects(self.client.get(reverse("comptable_dashboard")), reverse("home"))

    def test_seller_reaches_main_dashboard(self):
        user = User.objects.create_user("seller", password="secret123")
        user.profile.role = "vendeur"
        user.profile.save()
        self.client.login(username="seller", password="secret123")
        response = self.client.get(reverse("vendeur_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="darkModeToggle"')
        self.assertContains(response, "animations.js")

    def test_admin_dashboard_uses_shared_theme_control(self):
        user = User.objects.create_user("admin-theme", password="secret123")
        user.profile.role = "admin"
        user.profile.save()
        self.client.login(username="admin-theme", password="secret123")
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="darkModeToggle"')
        self.assertContains(response, "animations.js")


class AdminRoleManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("role-admin", password="secret123")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.target = User.objects.create_user("role-target", password="secret123")
        self.client.login(username="role-admin", password="secret123")

    def change_role(self, role):
        return self.client.post(
            reverse("changer_role_utilisateur", args=[self.target.profile.id]),
            {"role": role},
        )

    def test_admin_can_change_each_existing_role_and_audit_old_new_labels(self):
        for role in ("vendeur", "livreur", "comptable", "admin", "client"):
            with self.subTest(role=role):
                response = self.change_role(role)
                self.assertRedirects(response, reverse("admin_utilisateur_detail", args=[self.target.profile.id]))
                self.target.profile.refresh_from_db()
                self.assertEqual(self.target.profile.role, role)
        log = JournalActivite.objects.filter(details__contains="role-target").latest("date")
        self.assertIn("Client", log.details)
        self.assertIn("Vendeur", JournalActivite.objects.filter(details__contains="role-target").earliest("date").details)

    def test_admin_list_exposes_role_action_and_active_status(self):
        response = self.client.get(reverse("admin_utilisateurs"))
        self.assertContains(response, "Modifier le rôle")
        self.assertContains(response, "Actif")
        self.assertContains(response, reverse("changer_role_utilisateur", args=[self.target.profile.id]))

    def test_admin_detail_exposes_role_editor_and_success_feedback(self):
        response = self.client.get(reverse("admin_utilisateur_detail", args=[self.target.profile.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rôle actuel")
        self.assertContains(response, "Nouveau rôle")
        self.assertContains(response, "Modifier le rôle")
        response = self.client.post(
            reverse("changer_role_utilisateur", args=[self.target.profile.id]),
            {"role": "vendeur"},
            follow=True,
        )
        self.assertContains(response, "Le rôle de role-target a été mis à jour")
        self.target.profile.refresh_from_db()
        self.assertEqual(self.target.profile.role, "vendeur")

    def test_non_admin_cannot_change_role(self):
        for role in ("client", "vendeur", "livreur", "comptable"):
            with self.subTest(role=role):
                user = User.objects.create_user(f"blocked-{role}", password="secret123")
                user.profile.role = role
                user.profile.save()
                self.client.force_login(user)
                response = self.change_role("vendeur")
                self.assertRedirects(response, reverse("home"))
                self.target.profile.refresh_from_db()
                self.assertEqual(self.target.profile.role, "client")
        self.client.force_login(self.admin)

    def test_self_role_change_is_rejected(self):
        response = self.client.post(
            reverse("changer_role_utilisateur", args=[self.admin.profile.id]),
            {"role": "client"},
        )
        self.assertRedirects(response, reverse("admin_utilisateur_detail", args=[self.admin.profile.id]))
        self.admin.profile.refresh_from_db()
        self.assertEqual(self.admin.profile.role, "admin")
        self.assertFalse(JournalActivite.objects.filter(details__contains="role-admin").exists())

    def test_invalid_or_missing_target_is_rejected(self):
        response = self.change_role("unknown")
        self.assertRedirects(response, reverse("admin_utilisateur_detail", args=[self.target.profile.id]))
        self.target.profile.refresh_from_db()
        self.assertEqual(self.target.profile.role, "client")
        response = self.client.post(reverse("changer_role_utilisateur", args=[999999]), {"role": "vendeur"})
        self.assertEqual(response.status_code, 404)

    def test_role_change_does_not_reactivate_inactive_user(self):
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        self.change_role("livreur")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.target.profile.role, "livreur")

    def test_admin_can_demote_target_when_another_admin_remains(self):
        self.target.profile.role = "admin"
        self.target.profile.save()
        response = self.change_role("client")
        self.assertRedirects(response, reverse("admin_utilisateur_detail", args=[self.target.profile.id]))
        self.target.profile.refresh_from_db()
        self.assertEqual(self.target.profile.role, "client")

    def test_role_change_updates_existing_permission_decorator(self):
        self.change_role("livreur")
        self.client.force_login(self.target)
        self.assertEqual(self.client.get(reverse("livreur_dashboard")).status_code, 200)
        self.client.force_login(self.admin)
        self.change_role("client")
        self.client.force_login(self.target)
        self.assertRedirects(self.client.get(reverse("livreur_dashboard")), reverse("home"))


class CounterSaleFlowTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("seller-flow", password="secret123")
        self.seller.profile.role = "vendeur"
        self.seller.profile.save()
        self.other_seller = User.objects.create_user("other-seller", password="secret123")
        self.other_seller.profile.role = "vendeur"
        self.other_seller.profile.save()
        category = Category.objects.create(nom="Mode")
        self.product = Product.objects.create(
            categorie=category, nom="Veste test", prix=25000, stock=5
        )
        self.client.login(username="seller-flow", password="secret123")

    def test_form_post_creates_sale_decreases_stock_redirects_and_renders_receipt(self):
        response = self.client.post(reverse("enregistrer_vente"), {
            "produit": str(self.product.id),
            "quantite": "2",
            "methode_paiement": "especes",
            "reference_client": "Client comptoir",
            "notes": "Essayage effectué",
        })

        vente = Vente.objects.get()
        self.assertRedirects(response, reverse("vendeur_vente_recu", kwargs={"vente_id": vente.id}))
        self.product.refresh_from_db()
        self.assertEqual(vente.vendeur, self.seller)
        self.assertEqual(vente.produit, self.product)
        self.assertEqual(vente.quantite, 2)
        self.assertEqual(vente.montant_total, 50000)
        self.assertEqual(vente.methode_paiement, "especes")
        self.assertEqual(self.product.stock, 3)

        receipt = self.client.get(reverse("vendeur_vente_recu", kwargs={"vente_id": vente.id}))
        self.assertEqual(receipt.status_code, 200)
        for text in ("VTE-", "Veste test", "Quantité", "25000", "50000", "Espèces", "seller-flow", "Client comptoir", "Imprimer", "Copier", "WhatsApp", "Nouvelle vente"):
            self.assertContains(receipt, text)

    def test_other_seller_cannot_view_receipt(self):
        vente = Vente.objects.create(
            vendeur=self.seller, produit=self.product, quantite=1,
            prix_unitaire=25000, montant_total=25000,
        )
        self.client.login(username="other-seller", password="secret123")
        response = self.client.get(reverse("vendeur_vente_recu", kwargs={"vente_id": vente.id}))
        self.assertEqual(response.status_code, 404)

    def test_counter_sale_accepts_moov_money_and_receipt_displays_it(self):
        response = self.client.post(reverse("enregistrer_vente"), {
            "produit": str(self.product.id),
            "quantite": "1",
            "methode_paiement": "moov_money",
        })
        self.assertEqual(response.status_code, 302)
        vente = Vente.objects.get()
        self.assertEqual(vente.methode_paiement, "moov_money")
        receipt = self.client.get(reverse("vendeur_vente_recu", kwargs={"vente_id": vente.id}))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, "Moov Money")

    def test_counter_sale_form_renders_moov_money(self):
        response = self.client.get(reverse("vendeur_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="moov_money"')
        self.assertContains(response, "Moov Money")

    def test_counter_sale_payment_filter_accepts_moov_money(self):
        Vente.objects.create(
            vendeur=self.seller, produit=self.product, quantite=1,
            prix_unitaire=25000, montant_total=25000, methode_paiement="moov_money",
        )
        response = self.client.get(reverse("historique_ventes"), {"methode": "moov_money"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 1)


class AdminDashboardV2Tests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin-v2", password="secret123")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.seller = User.objects.create_user("seller-v2", password="secret123")
        self.seller.profile.role = "vendeur"
        self.seller.profile.save()
        self.category = Category.objects.create(nom="Pilotage")
        self.product = Product.objects.create(
            categorie=self.category, nom="Produit pilotage", prix=1000, stock=4,
        )

    def test_admin_can_access_dashboard(self):
        self.client.login(username="admin-v2", password="secret123")
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("admin_utilisateurs"))
        self.assertContains(response, "Utilisateurs")

    def test_admin_payment_filter_renders_moov_money(self):
        self.client.login(username="admin-v2", password="secret123")
        response = self.client.get(reverse("admin_paiements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="moov_money"')
        self.assertContains(response, "Moov Money")

    def test_real_admin_users_page_exposes_role_action(self):
        self.client.login(username="admin-v2", password="secret123")
        response = self.client.get(reverse("admin_utilisateurs"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modifier le rôle")
        self.assertContains(response, reverse("changer_role_utilisateur", args=[self.seller.profile.id]))
        response = self.client.get(reverse("admin_utilisateur_detail", args=[self.seller.profile.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modifier le rôle")

    def test_seller_is_refused(self):
        self.client.login(username="seller-v2", password="secret123")
        self.assertRedirects(self.client.get(reverse("admin_dashboard")), reverse("home"))

    def test_empty_database_metrics_render(self):
        self.product.delete()
        self.category.delete()
        self.client.login(username="admin-v2", password="secret123")
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0")
        self.assertContains(response, "revenue-chart-data")

    def test_revenue_uses_counter_sales_and_paid_web_payment_once(self):
        Vente.objects.create(
            vendeur=self.seller, produit=self.product, quantite=1,
            prix_unitaire=1000, montant_total=1000,
        )
        order = Order.objects.create(utilisateur=self.seller, statut="confirmee")
        Payment.objects.create(
            commande=order, montant=2000, methode="especes", statut="paye",
        )
        self.client.login(username="admin-v2", password="secret123")
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.context["revenue_today"], 3000)
        self.assertEqual(response.context["counter_sales_today"], 1)
        self.assertEqual(response.context["web_orders_today"], 1)


class SellerPerformanceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin-performance", password="secret123")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.seller = User.objects.create_user("seller-performance", password="secret123")
        self.seller.profile.role = "vendeur"
        self.seller.profile.save()
        self.other_seller = User.objects.create_user("seller-empty", password="secret123")
        self.other_seller.profile.role = "vendeur"
        self.other_seller.profile.save()
        category = Category.objects.create(nom="Performance")
        self.product = Product.objects.create(categorie=category, nom="Produit vendeur", prix=1000, stock=10)
        self.client.login(username="admin-performance", password="secret123")

    def test_admin_can_access_performance_and_empty_seller_is_listed(self):
        response = self.client.get(reverse("admin_vendeurs_performance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "seller-empty")

    def test_seller_is_refused(self):
        self.client.login(username="seller-performance", password="secret123")
        self.assertRedirects(self.client.get(reverse("admin_vendeurs_performance")), reverse("home"))

    def test_counter_revenue_and_confirmed_order_are_attributed_once(self):
        Vente.objects.create(vendeur=self.seller, produit=self.product, quantite=2, prix_unitaire=1000, montant_total=2000)
        order = Order.objects.create(utilisateur=self.seller, statut="confirmee", vendeur_confirmateur=self.seller, date_confirmation=timezone.now())
        Payment.objects.create(commande=order, montant=3000, methode="especes", statut="paye")
        response = self.client.get(reverse("admin_vendeurs_performance"))
        row = next(item for item in response.context["rows"] if item["profile"].utilisateur == self.seller)
        self.assertEqual(row["sales_total"], 2000)
        self.assertEqual(row["orders_total"], 3000)
        self.assertEqual(row["operations"], 2)

    def test_period_filter_excludes_old_counter_sale(self):
        old_sale = Vente.objects.create(vendeur=self.seller, produit=self.product, quantite=1, prix_unitaire=1000, montant_total=1000)
        Vente.objects.filter(pk=old_sale.pk).update(date_vente=timezone.now() - timedelta(days=40))
        response = self.client.get(reverse("admin_vendeurs_performance") + "?periode=today")
        row = next(item for item in response.context["rows"] if item["profile"].utilisateur == self.seller)
        self.assertEqual(row["sales_count"], 0)


class AdminAlertsAndActivityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin-alerts", password="secret123")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.seller = User.objects.create_user("seller-alerts", password="secret123")
        self.seller.profile.role = "vendeur"
        self.seller.profile.save()
        category = Category.objects.create(nom="Alertes")
        self.out_product = Product.objects.create(categorie=category, nom="Produit rupture", prix=1000, stock=0)
        self.low_product = Product.objects.create(categorie=category, nom="Produit faible", prix=1000, stock=2)
        self.client.login(username="admin-alerts", password="secret123")

    def test_alerts_admin_access_and_empty_database(self):
        response = self.client.get(reverse("admin_alertes"))
        self.assertEqual(response.status_code, 200)
        self.out_product.delete()
        self.low_product.delete()
        response = self.client.get(reverse("admin_alertes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune alerte")

    def test_seller_is_refused_from_alerts_and_activity(self):
        self.client.login(username="seller-alerts", password="secret123")
        self.assertRedirects(self.client.get(reverse("admin_alertes")), reverse("home"))
        self.assertRedirects(self.client.get(reverse("admin_activites")), reverse("home"))

    def test_stock_alert_levels_and_filters(self):
        response = self.client.get(reverse("admin_alertes"))
        self.assertContains(response, "Rupture de stock")
        self.assertContains(response, "Stock faible")
        self.assertContains(response, "Critique")
        filtered = self.client.get(reverse("admin_alertes") + "?niveau=critique&type=stock")
        self.assertContains(filtered, "Rupture de stock")
        self.assertNotContains(filtered, "Stock faible")

    def test_old_pending_order_and_failed_payment_alerts(self):
        order = Order.objects.create(utilisateur=self.seller, statut="en_attente")
        Order.objects.filter(pk=order.pk).update(date_creation=timezone.now() - timedelta(hours=25))
        payment = Payment.objects.create(commande=order, montant=2500, methode="wave", statut="echoue")
        response = self.client.get(reverse("admin_alertes"))
        self.assertContains(response, f"Commande #{order.id}")
        self.assertContains(response, "Paiement échoué")
        self.assertContains(response, str(payment.id))

    def test_activity_search_user_filter_and_pagination(self):
        for index in range(27):
            log_activity(self.seller, "autre", f"Événement audit {index}", niveau="info")
        response = self.client.get(reverse("admin_activites"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.per_page, 25)
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 2)
        searched = self.client.get(reverse("admin_activites") + "?q=Événement+audit+26")
        self.assertContains(searched, "Événement audit 26")
        filtered = self.client.get(reverse("admin_activites") + "?utilisateur=seller-alerts")
        self.assertContains(filtered, "seller-alerts")

    def test_counter_sale_creates_activity(self):
        sale = Vente.objects.create(vendeur=self.seller, produit=self.low_product, quantite=1, prix_unitaire=1000, montant_total=1000)
        log_activity(self.seller, "vente_creee", f"Vente #{sale.id} créée", niveau="info")
        response = self.client.get(reverse("admin_activites") + f"?q=Vente+%23{sale.id}")
        self.assertContains(response, f"Vente #{sale.id}")


class AdminClientsAndSettingsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin-config", password="secret123")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.client_user = User.objects.create_user("client-config", password="secret123", email="client@example.com")
        self.client.login(username="admin-config", password="secret123")

    def test_clients_page_is_accessible_and_searchable(self):
        response = self.client.get(reverse("admin_clients") + "?q=client@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "client-config")

    def test_settings_are_singleton_and_admin_only(self):
        response = self.client.get(reverse("admin_parametres"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BoutiqueSettings.objects.count(), 1)
        response = self.client.post(reverse("admin_parametres"), {"nom": "Boutique Test", "telephone": "000", "email": "shop@example.com", "adresse": "Adresse", "devise": "FCFA", "seuil_stock_faible": "4", "message_recu": "Merci"})
        self.assertRedirects(response, reverse("admin_parametres"))
        self.assertEqual(BoutiqueSettings.objects.get().nom, "Boutique Test")
        self.client.login(username="client-config", password="secret123")
        self.assertRedirects(self.client.get(reverse("admin_parametres")), reverse("home"))

    def test_logo_upload_is_validated_and_reused_in_header(self):
        image_file = BytesIO()
        Image.new("RGB", (16, 16), "navy").save(image_file, format="PNG")
        image_file.seek(0)
        response = self.client.post(reverse("admin_parametres"), {
            "nom": "Boutique Test", "telephone": "000", "email": "shop@example.com",
            "adresse": "Adresse", "devise": "FCFA", "seuil_stock_faible": "4",
            "message_recu": "Merci", "logo": SimpleUploadedFile("logo.png", image_file.read(), content_type="image/png"),
        })
        self.assertRedirects(response, reverse("admin_parametres"))
        shop = BoutiqueSettings.objects.get()
        self.assertTrue(shop.logo.name.startswith("boutique/"))
        self.assertContains(self.client.get(reverse("admin_parametres")), "shop-logo-preview")
        self.assertContains(self.client.get(reverse("admin_dashboard")), shop.logo.url)

    def test_invalid_logo_format_is_rejected(self):
        response = self.client.post(reverse("admin_parametres"), {
            "nom": "Boutique Test", "telephone": "000", "email": "shop@example.com",
            "adresse": "Adresse", "devise": "FCFA", "seuil_stock_faible": "4",
            "message_recu": "Merci", "logo": SimpleUploadedFile("logo.png", b"not-an-image", content_type="image/png"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoutiqueSettings.objects.get().logo)

    def test_settings_page_exposes_sections_navigation_and_controls(self):
        response = self.client.get(reverse("admin_parametres"))
        self.assertEqual(response.status_code, 200)
        for text in ("Paramètres", "Identité de la boutique", "Informations commerciales", "Gestion", "Reçus", "NIF / Identifiant fiscal", "RCCM", "Livraison activée", "Afficher ce message sur les reçus"):
            self.assertContains(response, text)
        self.assertContains(response, reverse("admin_parametres"))
        self.assertNotContains(response, 'name="whatsapp"')

    def test_extended_settings_are_saved_without_changing_permissions(self):
        response = self.client.post(reverse("admin_parametres"), {
            "nom": "Boutique Test", "telephone": "000", "email": "shop@example.com",
            "pays": "Mali", "ville": "Bamako", "adresse": "ACI 2000", "whatsapp": "22370000000",
            "nif": "NIF-1", "rccm": "RCCM-1", "devise": "FCFA", "seuil_stock_faible": "7",
            "livraison_active": "on", "message_recu": "Merci", "afficher_message_recu": "on",
        })
        self.assertRedirects(response, reverse("admin_parametres"))
        shop = BoutiqueSettings.objects.get()
        self.assertEqual((shop.whatsapp, shop.pays, shop.ville, shop.nif, shop.rccm), ("22370000000", "Mali", "Bamako", "NIF-1", "RCCM-1"))
        self.assertTrue(shop.livraison_active)
        self.assertTrue(shop.afficher_message_recu)


class ComptableFinancialV1Tests(TestCase):
    def setUp(self):
        self.accountant = User.objects.create_user("accountant-v1", password="secret123")
        self.accountant.profile.role = "comptable"
        self.accountant.profile.save()
        self.admin = User.objects.create_user("admin-v1", password="secret123")
        self.admin.profile.role = "admin"
        self.admin.profile.save()
        self.seller = User.objects.create_user("seller-v1", password="secret123")
        self.seller.profile.role = "vendeur"
        self.seller.profile.save()
        self.other_seller = User.objects.create_user("seller-v1-other", password="secret123")
        self.other_seller.profile.role = "vendeur"
        self.other_seller.profile.save()
        self.client_user = User.objects.create_user("client-v1", password="secret123", email="client-v1@example.com")
        category = Category.objects.create(nom="Comptabilité")
        self.product = Product.objects.create(categorie=category, nom="Produit comptable", prix=1000, stock=50)
        self.category = category

    def _login_accountant(self):
        self.client.login(username="accountant-v1", password="secret123")

    def _sale(self, amount=1000, method="especes", seller=None, when=None, reference="Client test"):
        sale = Vente.objects.create(
            vendeur=seller or self.seller, produit=self.product, quantite=1,
            prix_unitaire=amount, montant_total=amount,
            methode_paiement=method, reference_client=reference,
        )
        if when:
            Vente.objects.filter(pk=sale.pk).update(date_vente=when)
            sale.refresh_from_db()
        return sale

    def _payment(self, amount=1000, method="orange_money", status="paye", when=None, order=None, confirmer=None):
        order = order or Order.objects.create(
            utilisateur=self.client_user,
            statut="confirmee" if status == "paye" else "en_attente",
            vendeur_confirmateur=confirmer,
        )
        payment = Payment.objects.create(
            commande=order, montant=amount, methode=method, statut=status,
            date_paiement=when if status == "paye" else None,
        )
        return payment

    def test_comptable_accesses_dashboard(self):
        self._login_accountant()
        self.assertEqual(self.client.get(reverse("comptable_dashboard")).status_code, 200)

    def test_client_is_refused(self):
        self.client.login(username="client-v1", password="secret123")
        self.assertRedirects(self.client.get(reverse("comptable_dashboard")), reverse("home"))

    def test_vendor_is_refused(self):
        self.client.login(username="seller-v1", password="secret123")
        self.assertRedirects(self.client.get(reverse("comptable_dashboard")), reverse("home"))

    def test_admin_is_authorized(self):
        self.client.login(username="admin-v1", password="secret123")
        self.assertEqual(self.client.get(reverse("comptable_dashboard")).status_code, 200)

    def test_counter_sale_enters_revenue(self):
        self._sale(1200)
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["total_jour"], 1200)
        self.assertEqual(response.context["rev_ventes_jour"], 1200)

    def test_paid_payment_enters_revenue(self):
        self._payment(2300, when=timezone.now())
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["rev_paiements_jour"], 2300)

    def test_pending_payment_does_not_enter_revenue(self):
        self._payment(2300, status="en_attente")
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["total_jour"], 0)

    def test_failed_payment_does_not_enter_revenue(self):
        self._payment(2300, status="echoue")
        self._login_accountant()
        self.assertEqual(self.client.get(reverse("comptable_dashboard")).context["total_jour"], 0)

    def test_cancelled_payment_does_not_enter_revenue(self):
        self._payment(2300, status="annule")
        self._login_accountant()
        self.assertEqual(self.client.get(reverse("comptable_dashboard")).context["total_jour"], 0)

    def test_order_and_payment_are_not_double_counted(self):
        order = Order.objects.create(utilisateur=self.client_user, statut="confirmee", frais_livraison=200)
        from orders.models import OrderItem
        OrderItem.objects.create(commande=order, produit=self.product, quantite=2, prix=1000)
        self._payment(2200, when=timezone.now(), order=order)
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["total_jour"], 2200)

    def test_paid_payment_period_uses_payment_date(self):
        payment = self._payment(1700, when=timezone.now() - timedelta(days=3))
        Payment.objects.filter(pk=payment.pk).update(date_creation=timezone.now() - timedelta(days=20))
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["total_jour"], 0)
        self.assertEqual(response.context["total_semaine"], 1700)

    def test_counter_sale_period_uses_sale_date(self):
        self._sale(1700, when=timezone.now() - timedelta(days=20))
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["total_jour"], 0)
        self.assertEqual(response.context["total_semaine"], 0)

    def test_cash_distribution_is_combined(self):
        self._sale(1000, method="especes")
        self._payment(500, method="especes", when=timezone.now())
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        cash = next(item for item in response.context["methodes_encaissees"] if item["label"] == "Espèces")
        self.assertEqual(cash["total"], 1500)

    def test_orange_money_distribution_is_correct(self):
        self._sale(1000, method="orange_money")
        self._login_accountant()
        response = self.client.get(reverse("comptable_dashboard"))
        item = next(item for item in response.context["methodes_encaissees"] if item["label"] == "Orange Money")
        self.assertEqual(item["total"], 1000)

    def test_wave_distribution_is_correct(self):
        self._payment(1000, method="wave", when=timezone.now())
        self._login_accountant()
        item = next(item for item in self.client.get(reverse("comptable_dashboard")).context["methodes_encaissees"] if item["label"] == "Wave")
        self.assertEqual(item["total"], 1000)

    def test_moov_money_distribution_is_correct(self):
        self._payment(1000, method="moov_money", when=timezone.now())
        self._login_accountant()
        item = next(item for item in self.client.get(reverse("comptable_dashboard")).context["methodes_encaissees"] if item["label"] == "Moov Money")
        self.assertEqual(item["total"], 1000)

    def test_card_distribution_is_correct(self):
        self._sale(1000, method="carte")
        self._login_accountant()
        item = next(item for item in self.client.get(reverse("comptable_dashboard")).context["methodes_encaissees"] if item["label"] == "Carte bancaire")
        self.assertEqual(item["total"], 1000)

    def test_period_filter_is_applied(self):
        self._sale(1000)
        self._sale(2000, when=timezone.now() - timedelta(days=10))
        self._login_accountant()
        response = self.client.get(reverse("comptable_transactions"), {"date_debut": timezone.localdate().isoformat()})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_method_filter_is_applied(self):
        self._sale(1000, method="especes")
        self._sale(2000, method="carte")
        self._login_accountant()
        response = self.client.get(reverse("comptable_transactions"), {"methode": "carte"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["total_encaisse"], 2000)

    def test_status_filter_is_applied(self):
        self._payment(1000, status="en_attente")
        self._payment(2000, status="paye", when=timezone.now())
        self._login_accountant()
        response = self.client.get(reverse("comptable_transactions"), {"statut": "en_attente"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["total_encaisse"], 0)

    def test_vendor_filter_is_applied(self):
        self._sale(1000, seller=self.seller)
        self._sale(2000, seller=self.other_seller)
        self._login_accountant()
        response = self.client.get(reverse("comptable_transactions"), {"vendeur": self.seller.id})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(response.context["total_encaisse"], 1000)

    def test_counter_sale_detail_is_enriched(self):
        sale = self._sale(1250, reference="Client détail")
        self._login_accountant()
        response = self.client.get(reverse("comptable_transaction_detail", args=[f"V-{sale.id}"]))
        self.assertEqual(response.status_code, 200)
        for value in ("Produit comptable", "Comptabilité", "Client détail", "Encaissé", "1250"):
            self.assertContains(response, value)

    def test_web_payment_detail_is_enriched(self):
        from orders.models import OrderItem
        order = Order.objects.create(utilisateur=self.client_user, statut="confirmee", frais_livraison=100)
        OrderItem.objects.create(commande=order, produit=self.product, quantite=2, prix=900)
        payment = self._payment(1900, method="moov_money", when=timezone.now(), order=order, confirmer=self.seller)
        self._login_accountant()
        response = self.client.get(reverse("comptable_transaction_detail", args=[payment.reference or f"P-{payment.id}"]))
        self.assertEqual(response.status_code, 200)
        for value in ("Commande en ligne", "client-v1", "Moov Money", "Produit comptable", "2", "1900"):
            self.assertContains(response, value)

    def test_export_respects_filters(self):
        self._sale(1000, method="especes")
        self._sale(2000, method="carte")
        self._login_accountant()
        response = self.client.get(reverse("comptable_export_csv"), {"methode": "carte"})
        body = response.content.decode("utf-8-sig")
        self.assertEqual(response.status_code, 200)
        self.assertIn("2000", body)
        self.assertNotIn("1000", body)

    def test_pending_payment_is_visible_but_not_in_encashed_total(self):
        self._payment(1500, status="en_attente")
        self._login_accountant()
        response = self.client.get(reverse("comptable_transactions"))
        self.assertContains(response, "En attente")
        self.assertEqual(response.context["total_encaisse"], 0)
        self.assertEqual(response.context["total_perimetre"], 1500)

    def test_export_formula_injection_is_neutralized(self):
        self._sale(1000, reference="=2+2")
        self._login_accountant()
        body = self.client.get(reverse("comptable_export_csv")).content.decode("utf-8-sig")
        self.assertIn("'=2+2", body)

    def test_register_has_stable_secondary_ordering(self):
        self._sale(1000)
        self._sale(2000)
        self._login_accountant()
        response = self.client.get(reverse("comptable_transactions"))
        rows = list(response.context["page_obj"].object_list)
        self.assertEqual(rows, sorted(rows, key=lambda row: (row["date"], row["id"]), reverse=True))
