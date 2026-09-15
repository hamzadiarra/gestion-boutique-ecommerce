import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from PIL import Image
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connections, models, transaction, IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .cloture_forms import ClotureForm
from .cloture_services import solde_theorique_a_date, transition_cloture, cloture_a_mouvements_posterieurs, indicateurs_clotures
from .finance_services import ajuster, liquidites, regulariser
from .models import ClotureFinanciere, CompteFinancier, MouvementFinancier, JournalActivite


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ClotureTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        temporary = TemporaryDirectory(prefix="boutique-clotures-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name)
        override = override_settings(PRIVATE_EXPENSE_ROOT=cls.root)
        override.enable()
        cls.addClassCleanup(override.disable)

    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("comptable", "admin", "superuser", "vendeur", "client", "staff"):
            user = User.objects.create_user("closure-" + role, is_staff=role == "staff", is_superuser=role == "superuser")
            user.profile.role = role if role in ("comptable", "admin", "vendeur") else "client"
            user.profile.save()
            cls.users[role] = user
        cls.actor = cls.users["comptable"]
        cls.account = CompteFinancier.objects.create(nom="Caisse clôture", type_compte="especes", solde_initial=Decimal("100"), cree_par=cls.actor)
        cls.wave = CompteFinancier.objects.create(nom="Wave clôture", type_compte="wave", cree_par=cls.actor)

    def setUp(self):
        self.client.force_login(self.actor)

    def closure(self, **kwargs):
        data = dict(compte=self.account, date_cloture=timezone.localdate(), solde_constate=Decimal("100"), commentaire="Comptage vérifié", cree_par=self.actor)
        data.update(kwargs)
        return ClotureFinanciere.objects.create(**data)

    def payload(self, **kwargs):
        data = dict(compte=self.account.pk, date_cloture=timezone.localdate().isoformat(), solde_constate="100", commentaire="Constat documenté")
        data.update(kwargs)
        return data

    def movement(self, **kwargs):
        data = dict(compte_id=self.account.pk, sens="entree", montant=Decimal("25"), date_mouvement=timezone.now(), motif="Mouvement test", actor=self.actor)
        data.update(kwargs)
        return ajuster(**data)

    def validate(self, closure):
        return transition_cloture(closure.pk, "validee", self.actor)

    def cancel(self, closure):
        return transition_cloture(closure.pk, "annulee", self.actor)

    def rows(self, **kwargs):
        return list(self.client.get(reverse("comptable_clotures"), kwargs).context["page_obj"])

    @staticmethod
    def pdf():
        return SimpleUploadedFile("preuve.pdf", b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n", content_type="application/pdf")

    @staticmethod
    def image():
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
        return SimpleUploadedFile("comptage.png", buffer.getvalue(), content_type="image/png")

    def test_creation_server_fields(self):
        response = self.client.post(reverse("comptable_cloture_nouvelle"), self.payload(reference="FAUX", statut="validee", solde_theorique="999", ecart="999", cree_par=self.users["admin"].pk, validee_par=self.users["admin"].pk))
        self.assertEqual(response.status_code, 302)
        c = ClotureFinanciere.objects.get()
        self.assertEqual((c.compte, c.statut, c.cree_par, c.solde_theorique, c.ecart), (self.account, "brouillon", self.actor, Decimal("100"), Decimal("0")))
        self.assertRegex(c.reference, r"^CLO-\d{4}-\d{6,}$")
        self.assertIsNone(c.validee_par_id)
        self.assertIsNone(c.date_validation)

    def test_future_form_rejected(self):
        response = self.client.post(reverse("comptable_cloture_nouvelle"), self.payload(date_cloture=(timezone.localdate()+timedelta(days=1)).isoformat()))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ClotureFinanciere.objects.exists())

    def test_future_model_rejected(self):
        with self.assertRaises(ValidationError):
            self.closure(date_cloture=timezone.localdate()+timedelta(days=1))

    def test_initial_only(self):
        self.assertEqual(solde_theorique_a_date(self.account, timezone.localdate()), Decimal("100"))

    def test_entry_until_date(self):
        self.movement()
        self.assertEqual(self.closure().solde_theorique, Decimal("125"))

    def test_exit_until_date(self):
        self.movement(sens="sortie")
        self.assertEqual(self.closure().solde_theorique, Decimal("75"))

    def test_future_movement_excluded(self):
        self.movement(date_mouvement=timezone.now()+timedelta(days=1))
        self.assertEqual(self.closure().solde_theorique, Decimal("100"))

    def test_past_closure_excludes_today(self):
        self.movement()
        self.assertEqual(self.closure(date_cloture=timezone.localdate()-timedelta(days=1)).solde_theorique, Decimal("100"))

    def test_end_of_day_fraction_included(self):
        day = timezone.localdate()-timedelta(days=1)
        self.movement(date_mouvement=timezone.make_aware(datetime.combine(day, time.max)))
        self.assertEqual(self.closure(date_cloture=day).solde_theorique, Decimal("125"))

    def test_next_midnight_excluded(self):
        day = timezone.localdate()-timedelta(days=1)
        self.movement(date_mouvement=timezone.make_aware(datetime.combine(day+timedelta(days=1), time.min)))
        self.assertEqual(self.closure(date_cloture=day).solde_theorique, Decimal("100"))

    def test_decimal_exact(self):
        self.movement(montant=Decimal("0.10"))
        self.movement(montant=Decimal("0.20"))
        c = self.closure(solde_constate=Decimal("100.31"))
        self.assertEqual(c.solde_theorique, Decimal("100.30"))
        self.assertEqual(c.ecart, Decimal("0.01"))

    def test_positive_gap(self):
        c = self.closure(solde_constate=125)
        self.assertEqual((c.ecart, c.ecart_label), (Decimal("25"), "Excédent constaté"))

    def test_negative_gap(self):
        c = self.closure(solde_constate=75)
        self.assertEqual((c.ecart, c.ecart_label), (Decimal("-25"), "Manquant constaté"))

    def test_zero_gap(self):
        self.assertEqual(self.closure().ecart_label, "Conforme")

    def test_negative_observed_allowed(self):
        self.assertEqual(self.closure(solde_constate=-5).ecart, Decimal("-105"))

    def test_aggregate_sql(self):
        with self.assertNumQueries(1):
            self.assertEqual(solde_theorique_a_date(self.account, timezone.localdate()), Decimal("100"))

    def test_draft_edit(self):
        c = self.closure()
        self.assertEqual(self.client.post(reverse("comptable_cloture_modifier", args=[c.pk]), self.payload(solde_constate="75")).status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.ecart, Decimal("-25"))

    def test_draft_date_recalculates(self):
        self.movement()
        c = self.closure()
        c.date_cloture -= timedelta(days=1)
        c.save()
        self.assertEqual(c.solde_theorique, Decimal("100"))

    def test_draft_account_recalculates(self):
        c = self.closure()
        c.compte = self.wave
        c.save()
        self.assertEqual((c.solde_theorique, c.ecart), (Decimal("0"), Decimal("100")))

    def test_validated_edit_refused(self):
        c = self.validate(self.closure())
        self.assertEqual(self.client.post(reverse("comptable_cloture_modifier", args=[c.pk]), self.payload()).status_code, 403)
        with self.assertRaises(ValidationError):
            c.save()

    def test_cancelled_edit_refused(self):
        c = self.cancel(self.validate(self.closure()))
        self.assertEqual(self.client.get(reverse("comptable_cloture_modifier", args=[c.pk])).status_code, 403)

    def test_validation_metadata(self):
        c = self.validate(self.closure())
        self.assertEqual((c.statut, c.validee_par), ("validee", self.actor))
        self.assertIsNotNone(c.date_validation)

    def test_validation_refreshes_snapshot(self):
        c = self.closure()
        self.movement()
        c = self.validate(c)
        self.assertEqual(c.solde_theorique, Decimal("125"))
        self.assertEqual(c.ecart, Decimal("-25"))
        self.assertEqual(c.total_entrees, Decimal("25"))

    def test_double_validation_no_log_or_recalculation(self):
        c = self.validate(self.closure())
        count = JournalActivite.objects.count()
        when = c.date_validation
        self.movement()
        movement_logs = JournalActivite.objects.count()
        c = self.validate(c)
        self.assertEqual(c.date_validation, when)
        self.assertEqual(c.solde_theorique, Decimal("100"))
        self.assertEqual(JournalActivite.objects.count(), movement_logs)

    def test_gap_requires_comment(self):
        c = self.closure(solde_constate=90, commentaire="   ")
        with self.assertRaises(ValidationError):
            self.validate(c)
        c.refresh_from_db()
        self.assertEqual(c.statut, "brouillon")

    def test_zero_gap_without_comment(self):
        self.assertEqual(self.validate(self.closure(commentaire="")).statut, "validee")

    def test_cancel_preserves_snapshot_and_validator(self):
        c = self.validate(self.closure(solde_constate=90))
        when = c.date_validation
        c = self.cancel(c)
        self.assertEqual((c.statut, c.solde_theorique, c.solde_constate, c.ecart, c.validee_par, c.date_validation), ("annulee", Decimal("100"), Decimal("90"), Decimal("-10"), self.actor, when))
        self.assertTrue(ClotureFinanciere.objects.filter(pk=c.pk).exists())

    def test_double_cancel_idempotent(self):
        c = self.cancel(self.validate(self.closure()))
        count = JournalActivite.objects.count()
        self.cancel(c)
        self.assertEqual(JournalActivite.objects.count(), count)

    def test_draft_cannot_cancel(self):
        with self.assertRaises(ValidationError):
            self.cancel(self.closure())

    def test_cancelled_cannot_validate(self):
        c = self.cancel(self.validate(self.closure()))
        with self.assertRaises(ValidationError):
            self.validate(c)

    def test_no_delete(self):
        c = self.closure()
        with self.assertRaises(ValidationError):
            c.delete()
        with self.assertRaises(ValidationError):
            ClotureFinanciere.objects.all().delete()

    def test_validated_unique(self):
        self.validate(self.closure())
        other = self.closure()
        with self.assertRaises(ValidationError):
            self.validate(other)

    def test_database_validated_unique(self):
        self.validate(self.closure())
        other = self.closure()
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet(model=ClotureFinanciere).filter(pk=other.pk).update(statut="validee", validee_par=self.actor, date_validation=timezone.now())

    def test_cancel_allows_replacement(self):
        self.cancel(self.validate(self.closure()))
        self.assertEqual(self.validate(self.closure()).statut, "validee")

    def test_different_accounts_same_day(self):
        self.validate(self.closure())
        self.validate(self.closure(compte=self.wave, solde_constate=0))
        self.assertEqual(ClotureFinanciere.objects.filter(statut="validee").count(), 2)

    def test_snapshot_immutable_after_movement(self):
        c = self.validate(self.closure())
        self.movement()
        c.refresh_from_db()
        self.assertEqual(c.solde_theorique, Decimal("100"))

    def test_retroactive_detected_and_displayed(self):
        c = self.validate(self.closure())
        self.movement()
        self.assertTrue(cloture_a_mouvements_posterieurs(c))
        self.assertContains(self.client.get(reverse("comptable_cloture_detail", args=[c.pk])), "Clôture potentiellement obsolète")

    def test_future_movement_not_retroactive(self):
        c = self.validate(self.closure())
        self.movement(date_mouvement=timezone.now()+timedelta(days=1))
        self.assertFalse(cloture_a_mouvements_posterieurs(c))

    def test_draft_not_obsolete(self):
        c = self.closure()
        self.movement()
        self.assertFalse(cloture_a_mouvements_posterieurs(c))

    def test_late_regularization_detected(self):
        from orders.models import Order
        from payments.models import Payment
        p = Payment.objects.create(commande=Order.objects.create(utilisateur=self.actor), montant=10, methode="wave", statut="paye", date_paiement=timezone.now())
        movement = p.mouvements_financiers.get()
        c = self.validate(self.closure(compte=self.wave, solde_constate=0))
        regulariser(movement.pk, self.wave.pk, self.actor)
        self.assertTrue(cloture_a_mouvements_posterieurs(c))
        c.refresh_from_db()
        self.assertEqual(c.solde_theorique, 0)

    def test_no_automatic_financial_change(self):
        before = liquidites()
        c = self.validate(self.closure(solde_constate=50))
        self.cancel(c)
        self.assertFalse(MouvementFinancier.objects.exists())
        self.assertEqual(before["liquidites_par_devise"], liquidites()["liquidites_par_devise"])

    def test_pdf_accepted_private(self):
        c = self.closure(justificatif=self.pdf())
        self.assertTrue(c.justificatif.name.startswith("clotures/justificatifs/"))
        with self.assertRaises(ValueError):
            _ = c.justificatif.url

    def test_image_accepted(self):
        self.assertTrue(self.closure(justificatif=self.image()).justificatif)

    def test_large_file_rejected(self):
        upload = SimpleUploadedFile("large.pdf", b"%PDF-"+b"x"*(5*1024*1024), content_type="application/pdf")
        with self.assertRaises(ValidationError):
            self.closure(justificatif=upload)

    def test_fake_content_rejected(self):
        with self.assertRaises(ValidationError):
            self.closure(justificatif=SimpleUploadedFile("fake.png", b"not png", content_type="image/png"))

    def test_dangerous_extension_rejected(self):
        with self.assertRaises(ValidationError):
            self.closure(justificatif=SimpleUploadedFile("bad.html", b"<script></script>", content_type="text/html"))

    def test_attachment_download_headers(self):
        c = self.closure(justificatif=self.pdf())
        response = self.client.get(reverse("comptable_cloture_justificatif", args=[c.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])
        response.close()

    def test_attachment_draft_edit_page(self):
        c = self.closure(justificatif=self.pdf())
        self.assertEqual(self.client.get(reverse("comptable_cloture_modifier", args=[c.pk])).status_code, 200)

    def test_missing_attachment_404(self):
        self.assertEqual(self.client.get(reverse("comptable_cloture_justificatif", args=[self.closure().pk])).status_code, 404)

    def test_dashboard_separate_and_unchanged(self):
        before = self.client.get(reverse("comptable_dashboard"))
        self.validate(self.closure(solde_constate=95))
        after = self.client.get(reverse("comptable_dashboard"))
        for key in ("total_jour", "total_mois", "depenses_jour", "depenses_mois", "resultat_jour", "resultat_mois"):
            self.assertEqual(before.context[key], after.context[key])
        self.assertContains(after, "Clôtures et écarts constatés")
        self.assertEqual(self.account.solde_theorique, Decimal("100"))

    def test_accounts_not_closed(self):
        c = self.closure()
        self.assertEqual(indicateurs_clotures()["comptes_non_clotures"].count(), 2)
        self.validate(c)
        self.assertEqual(list(indicateurs_clotures()["comptes_non_clotures"]), [self.wave])

    def test_cancelled_account_not_closed(self):
        self.cancel(self.validate(self.closure()))
        self.assertEqual(indicateurs_clotures()["comptes_non_clotures"].count(), 2)

    def test_inactive_not_in_missing(self):
        self.account.actif = False
        self.account.save()
        self.assertEqual(list(indicateurs_clotures()["comptes_non_clotures"]), [self.wave])

    def test_inactive_closure_allowed(self):
        self.account.actif = False
        self.account.save()
        self.assertEqual(self.validate(self.closure()).statut, "validee")

    def test_kpi_validated_only(self):
        self.validate(self.closure(solde_constate=110))
        self.closure(compte=self.wave, solde_constate=1000)
        data = indicateurs_clotures()
        self.assertEqual(data["clotures_validees"], 1)
        self.assertEqual(data["clotures_avec_ecart"], 1)
        self.assertEqual(list(data["ecarts_par_devise"])[0]["positifs"], Decimal("10"))

    def test_kpi_currencies_separate(self):
        eur = CompteFinancier.objects.create(nom="EUR", type_compte="banque", devise="EUR", cree_par=self.actor)
        self.validate(self.closure(solde_constate=105))
        self.validate(self.closure(compte=eur, solde_constate=10))
        self.assertEqual(len(list(indicateurs_clotures()["ecarts_par_devise"])), 2)

    def test_filter_compte(self):
        c = self.closure()
        self.closure(compte=self.wave)
        self.assertEqual([r.pk for r in self.rows(compte=self.account.pk)], [c.pk])

    def test_filter_type(self):
        self.closure()
        self.assertEqual(self.rows(type_compte="wave"), [])

    def test_filter_period(self):
        old = self.closure(date_cloture=timezone.localdate()-timedelta(days=2))
        c = self.closure()
        self.assertEqual([r.pk for r in self.rows(date_debut=timezone.localdate().isoformat())], [c.pk])

    def test_filter_statut(self):
        self.closure()
        c = self.validate(self.closure())
        self.assertEqual([r.pk for r in self.rows(statut="validee")], [c.pk])

    def test_filter_positive(self):
        c = self.closure(solde_constate=110)
        self.closure(solde_constate=90)
        self.assertEqual([r.pk for r in self.rows(ecart="positif")], [c.pk])

    def test_filter_negative(self):
        c = self.closure(solde_constate=90)
        self.closure()
        self.assertEqual([r.pk for r in self.rows(ecart="negatif")], [c.pk])

    def test_filter_zero(self):
        c = self.closure()
        self.closure(solde_constate=90)
        self.assertEqual([r.pk for r in self.rows(ecart="conforme")], [c.pk])

    def test_invalid_filter(self):
        self.closure()
        self.assertEqual(self.rows(date_debut="not a date"), [])

    def test_pagination_stable(self):
        for _ in range(27):
            self.closure()
        rows = self.rows()
        self.assertEqual(len(rows), 25)
        self.assertEqual([r.pk for r in rows], sorted([r.pk for r in rows], reverse=True))

    def test_export_filters_bom_formula(self):
        self.account.nom = "=HYPERLINK(1)"
        self.account.save()
        self.closure(solde_constate=110)
        self.closure(solde_constate=90)
        response = self.client.get(reverse("comptable_clotures_export"), {"ecart": "positif"})
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]), 12)
        self.assertTrue(rows[1][2].startswith("'="))

    def test_creation_modification_audit(self):
        self.client.post(reverse("comptable_cloture_nouvelle"), self.payload())
        c = ClotureFinanciere.objects.get()
        self.client.post(reverse("comptable_cloture_modifier", args=[c.pk]), self.payload(commentaire="Recomptage"))
        self.assertEqual(JournalActivite.objects.filter(details__startswith=f"Clôture {c.reference} ").count(), 2)

    def test_validation_cancellation_audit(self):
        c = self.closure()
        self.validate(c)
        self.cancel(c)
        self.assertEqual(JournalActivite.objects.filter(details__startswith=f"Clôture {c.reference} ").count(), 2)

    def test_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.actor)
        self.assertEqual(client.post(reverse("comptable_cloture_nouvelle"), self.payload()).status_code, 403)

    def test_actions_post_only(self):
        c = self.closure()
        for route in ("comptable_cloture_valider", "comptable_cloture_annuler"):
            self.assertEqual(self.client.get(reverse(route, args=[c.pk])).status_code, 405)

    def test_adjustment_prefill_no_creation(self):
        c = self.validate(self.closure(solde_constate=90))
        response = self.client.get(reverse("comptable_ajustement_nouveau"), {"cloture": c.pk})
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual((form.initial["compte"], form.initial["sens"], form.initial["montant"]), (self.account.pk, "sortie", Decimal("10")))
        self.assertIn(c.reference, form.initial["motif"])
        self.assertFalse(MouvementFinancier.objects.exists())

    def test_offline_absent(self):
        c = self.closure(commentaire="Secret de clôture unique")
        response = self.client.get("/offline/sync/")
        self.assertNotIn(c.reference.encode(), response.content)
        self.assertNotIn("Secret de clôture unique".encode(), response.content)
        worker = (Path(settings.BASE_DIR)/"static/service-worker.js").read_text(encoding="utf-8")
        self.assertIn('pathname.startsWith("/dashboard/comptable/")', worker)


def _permission(role, route):
    def test(self):
        c = self.closure(justificatif=self.pdf())
        self.client.force_login(self.users[role])
        args = [c.pk] if route in ("comptable_cloture_detail", "comptable_cloture_modifier", "comptable_cloture_justificatif") else []
        response = self.client.get(reverse(route, args=args))
        self.assertEqual(response.status_code, 200 if role in ("comptable", "admin", "superuser") else 302)
        self.assertIn("no-store", response["Cache-Control"])
        response.close()
    return test


for _role in ("comptable", "admin", "superuser", "vendeur", "client", "staff"):
    for _route in ("comptable_clotures", "comptable_cloture_nouvelle", "comptable_cloture_detail", "comptable_cloture_modifier", "comptable_cloture_justificatif", "comptable_clotures_export"):
        setattr(ClotureTests, f"test_permission_{_role}_{_route}", _permission(_role, _route))


def _action_permission(role):
    def test(self):
        c = self.closure()
        self.client.force_login(self.users[role])
        for route in ("comptable_cloture_valider", "comptable_cloture_annuler", "comptable_cloture_modifier"):
            self.assertEqual(self.client.post(reverse(route, args=[c.pk]), self.payload()).status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.statut, "brouillon")
        self.assertFalse(JournalActivite.objects.exists())
    return test


for _role in ("vendeur", "client", "staff"):
    setattr(ClotureTests, "test_actions_refused_"+_role, _action_permission(_role))


def _invalid_amount(value):
    def test(self):
        form = ClotureForm(self.payload(solde_constate=value))
        self.assertFalse(form.is_valid())
        self.assertIn("solde_constate", form.errors)
    return test


for _index, _value in enumerate(("NaN", "Infinity", "-Infinity", "invalid")):
    setattr(ClotureTests, f"test_invalid_decimal_{_index}", _invalid_amount(_value))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ClotureConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.actor = User.objects.create_user("cloture-concurrente")
        self.account = CompteFinancier.objects.create(nom="Concurrent", type_compte="especes", cree_par=self.actor)

    def closure(self):
        return ClotureFinanciere.objects.create(compte=self.account, solde_constate=0, cree_par=self.actor)

    def race(self, ids):
        barrier = Barrier(2)
        def worker(pk):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    transition_cloture(pk, "validee", self.actor)
                    return "ok"
                except (ValidationError, IntegrityError):
                    return "conflict"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, pk) for pk in ids]
            return [f.result(timeout=30) for f in futures]

    def test_same_closure_two_validations(self):
        c = self.closure()
        self.assertEqual(self.race([c.pk, c.pk]), ["ok", "ok"])
        self.assertEqual(JournalActivite.objects.count(), 1)
        self.assertEqual(ClotureFinanciere.objects.filter(statut="validee").count(), 1)

    def test_two_closures_one_validation(self):
        results = self.race([self.closure().pk, self.closure().pk])
        self.assertCountEqual(results, ["ok", "conflict"])
        self.assertEqual(JournalActivite.objects.count(), 1)
        self.assertEqual(ClotureFinanciere.objects.filter(statut="validee").count(), 1)
