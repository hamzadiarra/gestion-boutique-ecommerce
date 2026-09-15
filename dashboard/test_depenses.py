import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from PIL import Image
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from orders.models import Order
from payments.models import Payment
from products.models import Product
from .depense_forms import DepenseForm
from .depense_views import _transition_depense
from .models import BoutiqueSettings, CategorieDepense, Depense, JournalActivite, Vente


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DepensesV1Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        temporary = TemporaryDirectory(prefix="boutique-depenses-tests-")
        cls.addClassCleanup(temporary.cleanup)
        cls.private_root = Path(temporary.name)
        storage_settings = override_settings(PRIVATE_EXPENSE_ROOT=cls.private_root)
        storage_settings.enable()
        cls.addClassCleanup(storage_settings.disable)

    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("comptable", "admin", "vendeur", "client"):
            user = User.objects.create_user(f"expense-{role}", password="ExpenseTest!42")
            user.profile.role = role
            user.profile.save()
            cls.users[role] = user
        cls.staff = User.objects.create_user("expense-staff", is_staff=True)
        cls.category = CategorieDepense.objects.create(nom="Transport")
        cls.other_category = CategorieDepense.objects.create(nom="Internet")
        cls.shop = BoutiqueSettings.objects.create(nom="Expense shop", devise="FCFA")

    def setUp(self):
        self.client.force_login(self.users["comptable"])

    def _payload(self, **changes):
        data = {"date_depense": timezone.localdate().isoformat(), "categorie": self.category.pk,
                "libelle": "Carburant", "montant": "20000.50", "moyen_paiement": "wave",
                "beneficiaire": "Station", "description": "Livraison client"}
        data.update(changes)
        return data

    def _create(self, **changes):
        data = {"date_depense": timezone.localdate(), "categorie": self.category, "libelle": "Carburant",
                "montant": Decimal("100.25"), "moyen_paiement": "wave", "cree_par": self.users["comptable"]}
        data.update(changes)
        return Depense.objects.create(**data)

    def _validate(self, expense):
        response = self.client.post(reverse("comptable_depense_valider", args=[expense.pk]))
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        return expense

    def _cancel(self, expense):
        self._validate(expense)
        response = self.client.post(reverse("comptable_depense_annuler", args=[expense.pk]))
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        return expense

    def _rows(self, **filters):
        return list(self.client.get(reverse("comptable_depenses"), filters).context["page_obj"])

    def _assert_refused(self, user):
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("comptable_depenses")), reverse("home"), fetch_redirect_response=False)

    @staticmethod
    def _pdf():
        return SimpleUploadedFile("facture.pdf", b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n", content_type="application/pdf")

    @staticmethod
    def _image(extension="png", fmt="PNG", mime="image/png"):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(buffer, format=fmt)
        return SimpleUploadedFile(f"facture.{extension}", buffer.getvalue(), content_type=mime)

    def test_comptable_accesses_empty_list(self):
        response = self.client.get(reverse("comptable_depenses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune dépense")
        self.assertEqual(response.context["total_selection"], Decimal("0"))

    def test_admin_accesses_expenses(self):
        self.client.force_login(self.users["admin"])
        self.assertEqual(self.client.get(reverse("comptable_depenses")).status_code, 200)

    def test_seller_refused(self):
        self._assert_refused(self.users["vendeur"])

    def test_client_refused(self):
        self._assert_refused(self.users["client"])

    def test_staff_client_refused(self):
        self._assert_refused(self.staff)

    def test_anonymous_refused(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse("comptable_depenses")), reverse("login"))

    def test_superuser_supervises_without_accountant_role(self):
        user = User.objects.create_superuser("expense-super", password="ExpenseTest!42")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("comptable_depenses")).status_code, 200)

    def test_creation_is_draft(self):
        response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload())
        expense = Depense.objects.get()
        self.assertRedirects(response, reverse("comptable_depense_detail", args=[expense.pk]))
        self.assertEqual(expense.statut, "brouillon")
        self.assertIsNone(expense.date_validation)
        self.assertIsNone(expense.validee_par)
        self.assertEqual(expense.montant, Decimal("20000.50"))

    def test_reference_generated_unique_and_readable(self):
        first, second = self._create(), self._create()
        self.assertRegex(first.reference, rf"^DEP-{timezone.localdate().year}-\d{{6,}}$")
        self.assertNotEqual(first.reference, second.reference)
        self.assertTrue(first.reference.endswith(f"{first.pk:06d}"))

    def test_creator_correct_and_protected_fields_ignored(self):
        response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(
            reference="FORGED", cree_par=self.users["client"].pk, statut="validee",
            validee_par=self.users["admin"].pk, date_validation="2020-01-01",
        ))
        self.assertEqual(response.status_code, 302)
        expense = Depense.objects.get()
        self.assertEqual(expense.cree_par, self.users["comptable"])
        self.assertNotEqual(expense.reference, "FORGED")
        self.assertEqual(expense.statut, "brouillon")
        self.assertIsNone(expense.date_validation)
        self.assertIsNone(expense.validee_par)

    def test_positive_decimal_amount_accepted(self):
        self.assertEqual(self.client.post(reverse("comptable_depense_nouvelle"), self._payload(montant="0.01")).status_code, 302)
        self.assertEqual(Depense.objects.get().montant, Decimal("0.01"))

    def test_negative_amount_refused(self):
        self.assertEqual(self.client.post(reverse("comptable_depense_nouvelle"), self._payload(montant="-1")).status_code, 200)
        self.assertFalse(Depense.objects.exists())

    def test_zero_amount_refused(self):
        response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(montant="0"))
        self.assertIn("montant", response.context["form"].errors)
        self.assertFalse(Depense.objects.exists())

    def test_nonfinite_invalid_or_excessive_amounts_refused(self):
        for value in ("NaN", "Infinity", "-Infinity", "abc", "", "0.001", "1000000000000"):
            with self.subTest(value=value):
                response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(montant=value))
                self.assertIn("montant", response.context["form"].errors)
        self.assertFalse(Depense.objects.exists())

    def test_model_validation_and_database_positive_constraint(self):
        for value in (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self._create(montant=value)
        expense = self._create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Depense.objects.filter(pk=expense.pk).update(montant=0)

    def test_draft_can_be_modified(self):
        expense = self._create()
        reference = expense.reference
        response = self.client.post(reverse("comptable_depense_modifier", args=[expense.pk]), self._payload(montant="222.22", reference="FORGED", cree_par=self.users["client"].pk))
        self.assertRedirects(response, reverse("comptable_depense_detail", args=[expense.pk]))
        expense.refresh_from_db()
        self.assertEqual(expense.montant, Decimal("222.22"))
        self.assertEqual(expense.reference, reference)
        self.assertEqual(expense.cree_par, self.users["comptable"])

    def test_validated_expense_cannot_be_modified(self):
        expense = self._validate(self._create())
        url = reverse("comptable_depense_modifier", args=[expense.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self._payload(montant="1")).status_code, 403)
        expense.refresh_from_db()
        self.assertEqual(expense.montant, Decimal("100.25"))
        expense.montant = Decimal("1")
        with self.assertRaises(ValidationError):
            expense.save()

    def test_cancelled_expense_cannot_be_modified(self):
        expense = self._cancel(self._create())
        self.assertEqual(self.client.post(reverse("comptable_depense_modifier", args=[expense.pk]), self._payload()).status_code, 403)

    def test_validation_changes_status(self):
        self.assertEqual(self._validate(self._create()).statut, "validee")

    def test_validation_sets_date(self):
        before = timezone.now()
        expense = self._validate(self._create())
        self.assertGreaterEqual(expense.date_validation, before)

    def test_validator_is_current_user_not_browser_value(self):
        expense = self._create()
        self.client.force_login(self.users["admin"])
        self.client.post(reverse("comptable_depense_valider", args=[expense.pk]), {"validee_par": self.users["client"].pk})
        expense.refresh_from_db()
        self.assertEqual(expense.validee_par, self.users["admin"])

    def test_double_validation_is_idempotent(self):
        expense = self._validate(self._create())
        validated_at, validator = expense.date_validation, expense.validee_par
        count = JournalActivite.objects.count()
        self.client.force_login(self.users["admin"])
        self._validate(expense)
        self.assertEqual((expense.date_validation, expense.validee_par), (validated_at, validator))
        self.assertEqual(JournalActivite.objects.count(), count)
        self.assertEqual(Depense.objects.count(), 1)

    def test_validated_expense_can_be_cancelled(self):
        self.assertEqual(self._cancel(self._create()).statut, "annulee")

    def test_double_cancellation_is_idempotent(self):
        expense = self._cancel(self._create())
        count = JournalActivite.objects.count()
        response = self.client.post(reverse("comptable_depense_annuler", args=[expense.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(JournalActivite.objects.count(), count)

    def test_cancellation_preserves_row_and_validation_history(self):
        expense = self._validate(self._create())
        previous = (expense.reference, expense.montant, expense.categorie_id, expense.cree_par_id, expense.validee_par_id, expense.date_validation)
        self.client.post(reverse("comptable_depense_annuler", args=[expense.pk]))
        expense.refresh_from_db()
        self.assertEqual((expense.reference, expense.montant, expense.categorie_id, expense.cree_par_id, expense.validee_par_id, expense.date_validation), previous)

    def test_invalid_transitions_refused(self):
        expense = self._create()
        self.assertEqual(self.client.post(reverse("comptable_depense_annuler", args=[expense.pk])).status_code, 409)
        self._cancel(expense)
        self.assertEqual(self.client.post(reverse("comptable_depense_valider", args=[expense.pk])).status_code, 409)
        expense.refresh_from_db()
        self.assertEqual(expense.statut, "annulee")

    def test_draft_excluded_from_charges(self):
        self._create()
        self.assertEqual(Depense.indicateurs()["depenses_jour"], Decimal("0"))

    def test_validated_expense_included_in_charges(self):
        self._validate(self._create())
        self.assertEqual(Depense.indicateurs()["depenses_jour"], Decimal("100.25"))

    def test_cancelled_expense_excluded_from_charges_and_chart(self):
        self._cancel(self._create())
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["depenses_jour"], Decimal("0"))
        self.assertEqual(list(response.context["depenses_par_categorie"]), [])
        self.assertEqual(self.client.get(reverse("comptable_depenses")).context["nb_annulees"], 1)

    def test_operational_result_subtracts_expenses_without_changing_ca(self):
        category = Category.objects.create(nom="Finance test")
        product = Product.objects.create(categorie=category, nom="Finance product", prix=1000, stock=10)
        Vente.objects.create(vendeur=self.users["vendeur"], produit=product, quantite=1, prix_unitaire=1000, montant_total=1000)
        order = Order.objects.create(utilisateur=self.users["client"])
        Payment.objects.create(commande=order, montant=2000, methode="wave", statut="paye", date_paiement=timezone.now())
        unpaid = Order.objects.create(utilisateur=self.users["client"])
        Payment.objects.create(commande=unpaid, montant=9000, methode="wave")
        before = self.client.get(reverse("comptable_dashboard"))
        self._validate(self._create(montant=Decimal("700.50")))
        after = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(after.context["total_jour"], Decimal("3000"))
        for key in ("total_jour", "total_mois", "total_annee", "total_global"):
            self.assertEqual(after.context[key], before.context[key])
        self.assertEqual(after.context["resultat_jour"], Decimal("2299.50"))
        self.assertEqual(after.context["resultat_mois"], Decimal("2299.50"))
        self.assertEqual(self.client.get(reverse("comptable_transactions")).context["total_encaisse"], Decimal("3000"))

    def test_negative_operational_result_is_displayed(self):
        self._validate(self._create())
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["total_jour"], 0)
        self.assertEqual(response.context["resultat_jour"], Decimal("-100.25"))
        self.assertContains(response, "Résultat opérationnel")

    def test_period_kpis_use_expense_date_not_validation_date(self):
        for when, amount in ((date(2026, 6, 15), "1"), (date(2026, 6, 1), "2"), (date(2026, 1, 1), "4"), (date(2025, 12, 31), "8"), (date(2026, 6, 16), "16")):
            self._validate(self._create(date_depense=when, montant=Decimal(amount)))
        values = Depense.indicateurs(date(2026, 6, 15))
        self.assertEqual((values["depenses_jour"], values["depenses_mois"], values["depenses_annee"]), (Decimal("1"), Decimal("3"), Decimal("7")))

    def test_filter_period(self):
        current = self._create()
        self._create(date_depense=timezone.localdate() - timedelta(days=20))
        self.assertEqual(self._rows(date_debut=timezone.localdate().isoformat(), date_fin=timezone.localdate().isoformat()), [current])

    def test_filter_category(self):
        expense = self._create()
        self._create(categorie=self.other_category)
        self.assertEqual(self._rows(categorie=self.category.pk), [expense])

    def test_filter_payment_method(self):
        expense = self._create(moyen_paiement="moov_money")
        self._create(moyen_paiement="especes")
        self.assertEqual(self._rows(moyen_paiement="moov_money"), [expense])

    def test_filter_status(self):
        expense = self._validate(self._create())
        self._create()
        self.assertEqual(self._rows(statut="validee"), [expense])

    def test_filter_creator(self):
        expense = self._create(cree_par=self.users["admin"])
        self._create()
        self.assertEqual(self._rows(cree_par=self.users["admin"].pk), [expense])

    def test_search_all_requested_fields(self):
        expense = self._create(libelle="Carburant camion", beneficiaire="Station Alpha", description="Livraison urgente")
        self._create(categorie=self.other_category, libelle="Abonnement")
        for term in (expense.reference, "camion", "Alpha", "urgente", "Transport"):
            with self.subTest(term=term):
                self.assertEqual(self._rows(q=term), [expense])

    def test_invalid_filters_report_errors_and_export_refuses(self):
        for data in ({"date_debut": "2026-99-99"}, {"date_debut": "2026-06-02", "date_fin": "2026-06-01"}, {"categorie": "bad"}, {"cree_par": "bad"}, {"statut": "bad"}, {"moyen_paiement": "bad"}):
            with self.subTest(data=data):
                response = self.client.get(reverse("comptable_depenses"), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["filtre_form"].errors)
                self.assertEqual(self.client.get(reverse("comptable_depenses_export_csv"), data).status_code, 400)

    def test_stable_sort_and_pagination_keep_filters(self):
        expenses = [self._create() for _ in range(22)]
        response = self.client.get(reverse("comptable_depenses"), {"q": "Carburant", "statut": "brouillon", "moyen_paiement": "wave"})
        self.assertEqual([row.pk for row in response.context["page_obj"]], [item.pk for item in reversed(expenses)][0:20])
        self.assertContains(response, "page=2")
        self.assertContains(response, "moyen_paiement=wave")
        second = self.client.get(reverse("comptable_depenses"), {"page": 2, "statut": "brouillon"})
        self.assertEqual(len(second.context["page_obj"]), 2)

    def test_inactive_category_not_available_for_new_expense(self):
        self.category.actif = False
        self.category.save()
        form = DepenseForm()
        self.assertNotIn(self.category, form.fields["categorie"].queryset)
        response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload())
        self.assertIn("categorie", response.context["form"].errors)
        self.assertFalse(Depense.objects.exists())

    def test_historical_expense_keeps_inactive_category(self):
        expense = self._create()
        self.category.actif = False
        self.category.save()
        self.assertContains(self.client.get(reverse("comptable_depense_detail", args=[expense.pk])), "Transport")
        form = DepenseForm(instance=expense)
        self.assertIn(self.category, form.fields["categorie"].queryset)
        self._validate(expense)
        self.assertEqual(expense.categorie, self.category)

    def test_categories_create_and_toggle_are_audited(self):
        response = self.client.post(reverse("comptable_depense_categories"), {"nom": "Loyer", "description": "Local", "actif": "on"})
        self.assertRedirects(response, reverse("comptable_depense_categories"))
        category = CategorieDepense.objects.get(nom="Loyer")
        self.client.post(reverse("comptable_depense_categorie_toggle", args=[category.pk]))
        category.refresh_from_db()
        self.assertFalse(category.actif)
        self.client.post(reverse("comptable_depense_categorie_toggle", args=[category.pk]))
        category.refresh_from_db()
        self.assertTrue(category.actif)
        self.assertEqual(JournalActivite.objects.filter(details__contains=f"#{category.pk}").count(), 3)

    def test_category_name_required_unique_and_used_category_protected(self):
        for name in ("", "   ", self.category.nom):
            response = self.client.post(reverse("comptable_depense_categories"), {"nom": name})
            self.assertIn("nom", response.context["form"].errors)
        self._create()
        with self.assertRaises(ProtectedError):
            self.category.delete()

    def test_empty_category_setup_is_usable(self):
        CategorieDepense.objects.all().delete()
        self.assertContains(self.client.get(reverse("comptable_depense_categories")), "Aucune catégorie")
        self.assertContains(self.client.get(reverse("comptable_depense_nouvelle")), "Créez d'abord")

    def test_pdf_attachment_accepted_and_stored_privately(self):
        response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(justificatif=self._pdf()))
        self.assertEqual(response.status_code, 302)
        expense = Depense.objects.get()
        self.assertTrue(Path(expense.justificatif.path).is_relative_to(self.private_root))
        self.assertRegex(expense.justificatif.name, r"^depenses/justificatifs/\d{4}/\d{2}/[a-f0-9]+\.pdf$")
        with self.assertRaises(ValueError):
            _ = expense.justificatif.url
        self.assertEqual(self.client.get("/media/" + expense.justificatif.name).status_code, 404)

    def test_supported_image_attachments_accepted(self):
        for ext, fmt, mime in (("png", "PNG", "image/png"), ("jpg", "JPEG", "image/jpeg"), ("jpeg", "JPEG", "image/jpeg"), ("webp", "WEBP", "image/webp")):
            with self.subTest(extension=ext):
                response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(justificatif=self._image(ext, fmt, mime)))
                self.assertEqual(response.status_code, 302)

    def test_attachment_over_five_mb_refused(self):
        file = SimpleUploadedFile("large.pdf", b"x" * (5 * 1024 * 1024 + 1), content_type="application/pdf")
        response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(justificatif=file))
        self.assertIn("justificatif", response.context["form"].errors)
        self.assertFalse(Depense.objects.exists())

    def test_dangerous_or_disguised_attachment_refused(self):
        for filename, data, mime in (("run.html", b"<script>alert(1)</script>", "text/html"), ("run.pdf", b"<script>alert(1)</script>", "application/pdf"), ("run.png", b"not-image", "image/png"), ("run.pdf", b"%PDF-1.4\n%%EOF", "text/html")):
            with self.subTest(filename=filename, mime=mime):
                response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(justificatif=SimpleUploadedFile(filename, data, content_type=mime)))
                self.assertIn("justificatif", response.context["form"].errors)
        self.assertFalse(Depense.objects.exists())

    def test_missing_attachment_does_not_block_validation(self):
        expense = self._validate(self._create())
        self.assertFalse(expense.justificatif)
        self.assertEqual(expense.statut, "validee")

    def test_attachment_download_authorized_and_not_cached(self):
        self.client.post(reverse("comptable_depense_nouvelle"), self._payload(justificatif=self._pdf()))
        expense = Depense.objects.get()
        url = reverse("comptable_depense_justificatif", args=[expense.pk])
        for user in (self.users["comptable"], self.users["admin"]):
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
            response.close()
        for user in (self.users["client"], self.users["vendeur"], self.staff):
            self.client.force_login(user)
            self.assertRedirects(self.client.get(url), reverse("home"), fetch_redirect_response=False)

    def test_attachment_missing_file_returns_404(self):
        expense = self._create()
        url = reverse("comptable_depense_justificatif", args=[expense.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        Depense.objects.filter(pk=expense.pk).update(justificatif="depenses/justificatifs/missing.pdf")
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_csv_export_respects_filters_and_has_bom(self):
        included = self._validate(self._create(moyen_paiement="moov_money"))
        excluded = self._create(moyen_paiement="especes")
        response = self.client.get(reverse("comptable_depenses_export_csv"), {"moyen_paiement": "moov_money", "statut": "validee", "categorie": self.category.pk, "date_debut": timezone.localdate().isoformat(), "cree_par": self.users["comptable"].pk})
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        body = response.content.decode("utf-8-sig")
        self.assertIn(included.reference, body)
        self.assertNotIn(excluded.reference, body)
        rows = list(csv.reader(io.StringIO(body)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]), 11)
        self.assertEqual(rows[1][7], "100.25")

    def test_csv_formula_injection_protected(self):
        for value in ("=2+2", "+2+2", "-2+2", "@SUM(A1)", "\t=2+2", "  =2+2"):
            self._create(libelle=value, beneficiaire=value)
        body = self.client.get(reverse("comptable_depenses_export_csv")).content.decode("utf-8-sig")
        for row in list(csv.reader(io.StringIO(body)))[1:]:
            self.assertTrue(row[3].startswith("'"))
            self.assertTrue(row[4].startswith("'"))

    def test_creation_journal(self):
        self.client.post(reverse("comptable_depense_nouvelle"), self._payload())
        expense = Depense.objects.get()
        log = JournalActivite.objects.get()
        self.assertIn(expense.reference, log.details)
        self.assertIn("créée", log.details)
        self.assertEqual(log.utilisateur, self.users["comptable"])

    def test_modification_journal(self):
        expense = self._create()
        self.client.post(reverse("comptable_depense_modifier", args=[expense.pk]), self._payload())
        self.assertIn("modifiée", JournalActivite.objects.get().details)

    def test_validation_journal(self):
        expense = self._validate(self._create())
        log = JournalActivite.objects.get()
        self.assertIn(expense.reference, log.details)
        self.assertIn("validée", log.details)
        self.assertIn("100.25", log.details)

    def test_cancellation_journal(self):
        expense = self._cancel(self._create())
        log = JournalActivite.objects.filter(niveau="warning").get()
        self.assertIn(expense.reference, log.details)
        self.assertIn("annulée", log.details)

    def test_detail_permissions_and_no_data_leak(self):
        expense = self._create(libelle="Private expense label")
        for user in (self.users["vendeur"], self.users["client"], self.staff):
            self.client.force_login(user)
            response = self.client.get(reverse("comptable_depense_detail", args=[expense.pk]))
            self.assertEqual(response.status_code, 302)
            self.assertNotIn(b"Private expense label", response.content)

    def test_validation_permissions(self):
        expense = self._create()
        for user in (self.users["vendeur"], self.users["client"], self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse("comptable_depense_valider", args=[expense.pk])).status_code, 302)
        expense.refresh_from_db()
        self.assertEqual(expense.statut, "brouillon")
        self.assertFalse(JournalActivite.objects.exists())

    def test_cancellation_permissions(self):
        expense = self._validate(self._create())
        for user in (self.users["vendeur"], self.users["client"], self.staff):
            self.client.force_login(user)
            self.client.post(reverse("comptable_depense_annuler", args=[expense.pk]))
        expense.refresh_from_db()
        self.assertEqual(expense.statut, "validee")
        self.assertEqual(JournalActivite.objects.count(), 1)

    def test_create_edit_categories_export_permissions(self):
        expense = self._create()
        for user in (self.users["vendeur"], self.users["client"], self.staff):
            self.client.force_login(user)
            for route, args in (("comptable_depense_nouvelle", []), ("comptable_depense_modifier", [expense.pk]), ("comptable_depense_categories", []), ("comptable_depense_categorie_toggle", [self.category.pk])):
                self.assertEqual(self.client.post(reverse(route, args=args), self._payload()).status_code, 302)
            self.assertEqual(self.client.get(reverse("comptable_depenses_export_csv")).status_code, 302)
        self.assertEqual(Depense.objects.count(), 1)
        self.assertFalse(JournalActivite.objects.exists())

    def test_financial_actions_require_post_and_csrf(self):
        expense = self._create()
        for route in ("comptable_depense_valider", "comptable_depense_annuler"):
            self.assertEqual(self.client.get(reverse(route, args=[expense.pk])).status_code, 405)
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.users["comptable"])
        self.assertEqual(secured.post(reverse("comptable_depense_valider", args=[expense.pk])).status_code, 403)
        self.assertEqual(self.client.delete(reverse("comptable_depense_detail", args=[expense.pk])).status_code, 405)

    def test_detail_actions_follow_workflow_and_history_visible(self):
        expense = self._create()
        url = reverse("comptable_depense_detail", args=[expense.pk])
        self.assertContains(self.client.get(url), "Valider la dépense")
        self._validate(expense)
        response = self.client.get(url)
        self.assertContains(response, "Annuler la dépense")
        self.assertNotContains(response, "Valider la dépense")
        self.client.post(reverse("comptable_depense_annuler", args=[expense.pk]))
        response = self.client.get(url)
        self.assertNotContains(response, "Annuler la dépense")
        self.assertContains(response, "Historique des actions")
        self.assertContains(response, "annulée")

    def test_expense_navigation_only_for_financial_roles(self):
        for role, user in self.users.items():
            self.client.force_login(user)
            response = self.client.get(reverse("home"))
            if role in ("admin", "comptable"):
                self.assertContains(response, reverse("comptable_depenses"))
            else:
                self.assertNotContains(response, reverse("comptable_depenses"))

    def test_all_five_payment_methods_are_descriptive_only(self):
        for method, _ in Depense.MOYENS_PAIEMENT:
            response = self.client.post(reverse("comptable_depense_nouvelle"), self._payload(moyen_paiement=method))
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Depense.objects.count(), 5)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(Vente.objects.exists())

    def test_financial_pages_not_cached(self):
        for route in ("comptable_depenses", "comptable_dashboard", "comptable_depenses_export_csv"):
            self.assertIn("no-store", self.client.get(reverse(route))["Cache-Control"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DepenseConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user("concurrent-accountant")
        self.user.profile.role = "comptable"
        self.user.profile.save()
        category = CategorieDepense.objects.create(nom="Concurrent category")
        BoutiqueSettings.objects.create()
        self.expense = Depense.objects.create(categorie=category, libelle="Concurrent expense", montant=Decimal("10"), moyen_paiement="especes", cree_par=self.user)

    def _simultaneous(self, expected, target):
        barrier = Barrier(2)
        def execute():
            close_old_connections()
            try:
                request = RequestFactory().post("/dashboard/comptable/depenses/")
                request.user = self.user
                request.session = {}
                request._messages = FallbackStorage(request)
                barrier.wait(timeout=10)
                return _transition_depense(request, self.expense.pk, expected, target).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute) for _ in range(2)]
            statuses = [future.result(timeout=15) for future in futures]
        self.assertEqual(statuses, [302, 302])
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.statut, target)

    def test_simultaneous_validation_has_one_audit_entry(self):
        self._simultaneous("brouillon", "validee")
        self.assertEqual(JournalActivite.objects.count(), 1)
        self.assertEqual(Depense.objects.count(), 1)
        self.assertEqual(Depense.indicateurs()["depenses_jour"], Decimal("10"))

    def test_simultaneous_cancellation_has_one_audit_entry(self):
        Depense.objects.filter(pk=self.expense.pk).update(statut="validee", date_validation=timezone.now(), validee_par=self.user)
        self._simultaneous("validee", "annulee")
        self.assertEqual(JournalActivite.objects.count(), 1)
        self.assertIsNotNone(self.expense.date_validation)
        self.assertEqual(Depense.indicateurs()["depenses_jour"], Decimal("0"))
