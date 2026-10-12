from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from .models import Order
from .delivery_services import initialiser_livraison, affecter_livreur, changer_statut_livraison


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DeliveryProofTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("recipient")
        self.driver = User.objects.create_user("courier")
        self.admin = User.objects.create_user("administrator")
        self.other = User.objects.create_user("other")
        for user, role in [(self.driver, "livreur"), (self.admin, "admin")]:
            user.profile.role = role
            user.profile.save()
        self.order = Order.objects.create(utilisateur=self.customer, statut="confirmee",
            adresse_livraison="Quartier", ville_livraison="Bamako")
        self.delivery = initialiser_livraison(self.order, self.admin)
        affecter_livreur(self.delivery.pk, self.driver.pk, self.admin)
        for target, actor in [("acceptee", self.driver), ("prete", self.admin),
                              ("en_route", self.driver), ("arrive", self.driver)]:
            changer_statut_livraison(self.delivery.pk, target, actor)

    def test_old_action_cannot_confirm_without_proof(self):
        with self.assertRaises(ValidationError):
            changer_statut_livraison(self.delivery.pk, "livree", self.driver)
        self.order.refresh_from_db()
        self.assertEqual(self.order.statut, "expediee")

    def ready(self):
        changer_statut_livraison(self.delivery.pk, "attente_signature", self.driver)

    def sign(self):
        from .proof_services import confirmer_signature
        return confirmer_signature(self.delivery.pk, self.driver, "Fatou Test", png_signature(), True)

    def test_valid_signature_confirms_once_and_preserves_order_amount(self):
        from .proof_models import PreuveLivraison
        self.ready()
        proof = self.sign()
        self.assertTrue(bytes(proof.signature).startswith(b"\x89PNG"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.statut, "livree")
        self.assertEqual(self.order.frais_livraison, 0)
        with self.assertRaises(ValidationError):
            self.sign()
        self.assertEqual(PreuveLivraison.objects.count(), 1)
        self.assertEqual(self.delivery.historique.filter(nouveau_statut="livree").count(), 1)

    def test_invalid_images_leave_no_proof_or_status_change(self):
        from .proof_services import confirmer_signature
        from .proof_models import PreuveLivraison
        self.ready()
        for data in ["", "data:image/svg+xml;base64,AAAA", "data:image/png;base64,invalid!", png_signature(blank=True), "data:image/png;base64," + "A"*180001]:
            with self.subTest(data=data[:30]), self.assertRaises(ValidationError):
                confirmer_signature(self.delivery.pk, self.driver, "Fatou", data, True)
        self.assertFalse(PreuveLivraison.objects.exists())
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.statut, "attente_signature")

    def test_notice_and_assigned_courier_required(self):
        from django.core.exceptions import PermissionDenied
        from .proof_services import confirmer_signature
        self.ready()
        with self.assertRaises(ValidationError):
            confirmer_signature(self.delivery.pk, self.driver, "Fatou", png_signature(), False)
        with self.assertRaises(PermissionDenied):
            confirmer_signature(self.delivery.pk, self.other, "Fatou", png_signature(), True)

    def test_proof_route_is_private_and_audited(self):
        from django.urls import reverse
        from .proof_models import AccesPreuve
        self.ready()
        self.sign()
        url = reverse("livraison_preuve", args=[self.delivery.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        for user, expected in [(self.other, 403), (self.driver, 403), (self.customer, 200), (self.admin, 200)]:
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, expected)
            if expected == 200:
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(AccesPreuve.objects.count(), 2)

    def test_exception_requires_admin_decision(self):
        from django.core.exceptions import PermissionDenied
        from .proof_services import demander_derogation, decider_derogation
        from .proof_models import PreuveLivraison
        self.ready()
        item = demander_derogation(self.delivery.pk, self.driver, "Fatou", "Écran du téléphone endommagé")
        self.assertFalse(PreuveLivraison.objects.exists())
        with self.assertRaises(PermissionDenied):
            decider_derogation(item.pk, self.driver, True, "Remise vérifiée par appel")
        decider_derogation(item.pk, self.admin, True, "Remise vérifiée par appel")
        proof = PreuveLivraison.objects.get()
        self.assertTrue(proof.exceptionnelle)
        self.assertEqual(proof.autorisee_par, self.admin)
        with self.assertRaises(ValidationError):
            decider_derogation(item.pk, self.admin, True, "Remise vérifiée par appel")

    def test_customer_confirmation_rating_then_dispute(self):
        from django.core.exceptions import PermissionDenied
        from .proof_services import retour_client
        self.ready()
        self.sign()
        with self.assertRaises(PermissionDenied):
            retour_client(self.delivery.pk, self.other, "confirmation", 5)
        with self.assertRaises(ValidationError):
            retour_client(self.delivery.pk, self.customer, "confirmation", 6)
        item = retour_client(self.delivery.pk, self.customer, "confirmation", 4, "Bien reçu")
        self.assertEqual(item.note, 4)
        with self.assertRaises(ValidationError):
            retour_client(self.delivery.pk, self.customer, "confirmation", 5)
        retour_client(self.delivery.pk, self.customer, "probleme", commentaire="Un article est endommagé")
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.statut, "contestee")

    def test_purge_previews_then_removes_only_expired_private_data(self):
        from datetime import timedelta
        from django.core.management import call_command
        from django.db import models
        from django.utils import timezone
        from .proof_models import PreuveLivraison
        self.ready()
        proof = self.sign()
        models.QuerySet(model=PreuveLivraison).filter(pk=proof.pk).update(expire_at=timezone.now()-timedelta(seconds=1))
        call_command("purge_delivery_proofs")
        proof.refresh_from_db()
        self.assertTrue(proof.signature)
        call_command("purge_delivery_proofs", apply=True)
        proof.refresh_from_db()
        self.assertIsNone(proof.signature)
        self.assertEqual(proof.receptionnaire, "")
        self.assertIsNotNone(proof.purged_at)
        self.assertEqual(self.delivery.historique.filter(nouveau_statut="livree").count(), 1)

    def test_forms_signature_route_csrf_and_supervision(self):
        from django.test import Client
        from django.urls import reverse
        self.ready()
        self.client.force_login(self.driver)
        response = self.client.get(reverse("livraison_detail", args=[self.delivery.pk]))
        self.assertContains(response, 'id="signature-canvas"')
        self.assertEqual(self.client.get(reverse("livraison_supervision")).status_code, 403)
        url = reverse("livraison_signature", args=[self.delivery.pk])
        self.assertEqual(self.client.post(url, {"receptionnaire": "Fatou"}).status_code, 400)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.driver)
        self.assertEqual(csrf_client.post(url, {"signature": png_signature()}).status_code, 403)
        response = self.client.post(url, {"receptionnaire": "Fatou", "signature": png_signature(), "information_acceptee": "on"})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(reverse("livraison_retour", args=[self.delivery.pk]), {"type": "confirmation", "note": "5"}).status_code, 302)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("livraison_supervision")), "5/5")

    def test_order_save_cannot_bypass_required_proof(self):
        self.order.refresh_from_db()
        self.order.statut = "livree"
        with self.assertRaises(ValidationError):
            self.order.save(update_fields=["statut"])

    def test_historical_physical_order_also_requires_proof(self):
        historical = Order.objects.create(utilisateur=self.customer, statut="expediee", adresse_livraison="Rue 2", ville_livraison="Bamako")
        historical.statut = "livree"
        with self.assertRaises(ValidationError):
            historical.save(update_fields=["statut"])

    def test_reassignment_invalidates_old_exception_and_allows_new_request(self):
        from .proof_services import demander_derogation
        self.ready()
        old = demander_derogation(self.delivery.pk, self.driver, "Fatou", "Téléphone en panne sur place")
        self.other.profile.role = "livreur"
        self.other.profile.save()
        affecter_livreur(self.delivery.pk, self.other.pk, self.admin)
        old.refresh_from_db()
        self.assertEqual(old.decision, "refusee")
        self.assertIn("Réaffectation", old.motif_decision)
        for target, actor in [("acceptee", self.other), ("prete", self.admin), ("en_route", self.other), ("arrive", self.other), ("attente_signature", self.other)]:
            changer_statut_livraison(self.delivery.pk, target, actor)
        new = demander_derogation(self.delivery.pk, self.other, "Fatou", "Destinataire ne peut pas signer")
        self.assertEqual(new.decision, "attente")

    def test_purge_also_covers_abandoned_derogations(self):
        from datetime import timedelta
        from django.core.management import call_command
        from django.db import models
        from django.utils import timezone
        from .proof_models import DemandeDerogation
        from .proof_services import demander_derogation
        self.ready()
        item = demander_derogation(self.delivery.pk, self.driver, "Fatou", "Téléphone en panne sur place")
        models.QuerySet(model=DemandeDerogation).filter(pk=item.pk).update(created_at=timezone.now()-timedelta(days=366))
        call_command("purge_delivery_proofs", apply=True)
        item.refresh_from_db()
        self.assertEqual(item.receptionnaire, "")
        self.assertEqual(item.motif, "")
        self.assertEqual(item.decision, "refusee")


def png_signature(blank=False):
    import base64, io
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (600, 240), "white")
    if not blank:
        ImageDraw.Draw(image).line([(40, 120), (120, 50), (170, 140), (300, 60), (440, 110)], fill="black", width=4)
    out = io.BytesIO()
    image.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


from django.test import TransactionTestCase


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DeliveryConcurrencyTests(TransactionTestCase):
    setUp = DeliveryProofTests.setUp

    def test_concurrent_signatures_create_exactly_one_confirmation(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connection, close_old_connections
        from .proof_services import confirmer_signature
        from .proof_models import PreuveLivraison
        changer_statut_livraison(self.delivery.pk, "attente_signature", self.driver)
        barrier = Barrier(2)
        driver_id, delivery_id = self.driver.pk, self.delivery.pk
        def submit():
            close_old_connections()
            actor = User.objects.select_related("profile").get(pk=driver_id)
            barrier.wait(timeout=10)
            try:
                confirmer_signature(delivery_id, actor, "Fatou Test", png_signature(), True)
                return "confirmed"
            except ValidationError:
                return "conflict"
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: submit(), range(2)))
        self.assertCountEqual(results, ["confirmed", "conflict"])
        self.assertEqual(PreuveLivraison.objects.filter(livraison_id=delivery_id).count(), 1)
        self.assertEqual(self.delivery.historique.filter(nouveau_statut="livree").count(), 1)
