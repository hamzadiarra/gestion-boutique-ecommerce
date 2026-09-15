import csv
import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections, IntegrityError, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from categories.models import Category
from orders.models import Order
from payments.models import Payment
from products.models import Product
from .finance_forms import CompteForm, AjustementForm, TransfertForm
from .finance_services import ajuster, transferer, regulariser, enregistrer_vente, enregistrer_paiement, enregistrer_depense, liquidites
from .models import CompteFinancier, MouvementFinancier, TransfertFinancier, Vente, Depense, CategorieDepense, JournalActivite


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {}
        for role in ("comptable", "admin", "vendeur", "client", "staff", "superuser"):
            user = User.objects.create_user("finance-" + role, is_staff=role == "staff", is_superuser=role == "superuser")
            user.profile.role = role if role in ("comptable", "admin", "vendeur") else "client"
            user.profile.save()
            cls.users[role] = user
        cls.actor = cls.users["comptable"]
        cls.cash = CompteFinancier.objects.create(nom="Caisse", type_compte="especes", solde_initial=Decimal("100.25"), est_par_defaut=True, cree_par=cls.actor)
        cls.wave = CompteFinancier.objects.create(nom="Wave", type_compte="wave", est_par_defaut=True, cree_par=cls.actor)
        cls.category = CategorieDepense.objects.create(nom="Transport")
        cls.product = Product.objects.create(nom="Produit finance", prix=25, stock=100, categorie=Category.objects.create(nom="Finance"))

    def setUp(self):
        self.client.force_login(self.actor)

    def account(self, **kwargs):
        data = dict(nom="Autre", type_compte="especes", cree_par=self.actor)
        data.update(kwargs)
        return CompteFinancier.objects.create(**data)

    def sale(self, **kwargs):
        data = dict(vendeur=self.users["vendeur"], produit=self.product, quantite=2, prix_unitaire=25, montant_total=50, methode_paiement="especes")
        data.update(kwargs)
        return Vente.objects.create(**data)

    def payment(self, **kwargs):
        data = dict(commande=Order.objects.create(utilisateur=self.users["client"]), montant=Decimal("20.25"), methode="wave", statut="en_attente")
        data.update(kwargs)
        return Payment.objects.create(**data)

    def expense(self):
        return Depense.objects.create(categorie=self.category, libelle="Transport", montant=Decimal("15.50"), moyen_paiement="wave", cree_par=self.actor)

    def validate(self, expense):
        self.assertEqual(self.client.post(reverse("comptable_depense_valider", args=[expense.pk])).status_code, 302)
        expense.refresh_from_db()

    def cancel(self, expense):
        self.assertEqual(self.client.post(reverse("comptable_depense_annuler", args=[expense.pk])).status_code, 302)
        expense.refresh_from_db()

    def adjust(self, **kwargs):
        data = dict(compte_id=self.cash.pk, sens="entree", montant=Decimal("20.25"), date_mouvement=timezone.now(), motif="Comptage documenté", actor=self.actor)
        data.update(kwargs)
        return ajuster(**data)

    def transfer(self, **kwargs):
        data = dict(source_id=self.cash.pk, destination_id=self.wave.pk, montant=Decimal("25.50"), date_transfert=timezone.now(), motif="Dépôt", actor=self.actor)
        data.update(kwargs)
        return transferer(**data)

    def rows(self, **kwargs):
        return list(self.client.get(reverse("comptable_mouvements"), kwargs).context["page_obj"])

    def test_account_creation_view(self):
        response = self.client.post(reverse("comptable_compte_nouveau"), dict(nom="Banque", type_compte="banque", devise="FCFA", solde_initial="123.45", actif="on"))
        self.assertEqual(response.status_code, 302)
        account = CompteFinancier.objects.get(nom="Banque")
        self.assertEqual(account.cree_par, self.actor)
        self.assertEqual(account.solde_initial, Decimal("123.45"))
        self.assertEqual(JournalActivite.objects.count(), 1)

    def test_default_model_constraint(self):
        with self.assertRaises(ValidationError):
            self.account(est_par_defaut=True)

    def test_default_database_constraint(self):
        other = self.account()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompteFinancier.objects.filter(pk=other.pk).update(est_par_defaut=True)

    def test_inactive_default_allowed(self):
        self.assertFalse(self.account(actif=False, est_par_defaut=True).actif)

    def test_used_account_delete_protected(self):
        self.adjust()
        with self.assertRaises(ProtectedError):
            CompteFinancier.objects.filter(pk=self.cash.pk).delete()

    def test_account_instance_delete_forbidden(self):
        with self.assertRaises(ValidationError):
            self.cash.delete()

    def test_unused_initial_edit(self):
        self.cash.solde_initial = Decimal("150.75")
        self.cash.save()
        self.assertEqual(self.cash.solde_theorique, Decimal("150.75"))

    def test_used_initial_edit_refused(self):
        self.adjust()
        self.cash.solde_initial = 0
        with self.assertRaises(ValidationError):
            self.cash.save()

    def test_used_type_edit_refused(self):
        self.adjust()
        self.cash.type_compte = "banque"
        with self.assertRaises(ValidationError):
            self.cash.save()

    def test_used_currency_edit_refused(self):
        self.adjust()
        self.cash.devise = "EUR"
        with self.assertRaises(ValidationError):
            self.cash.save()

    def test_used_name_edit_allowed(self):
        self.adjust()
        self.cash.nom = "Caisse renommée"
        self.cash.save()
        self.assertEqual(self.cash.solde_initial, Decimal("100.25"))

    def test_initial_balance(self):
        self.assertEqual(self.cash.solde_theorique, Decimal("100.25"))

    def test_entry_balance(self):
        self.adjust()
        self.assertEqual(self.cash.solde_theorique, Decimal("120.50"))

    def test_exit_balance(self):
        self.adjust(sens="sortie")
        self.assertEqual(self.cash.solde_theorique, Decimal("80.00"))

    def test_negative_balance_allowed(self):
        self.adjust(sens="sortie", montant=Decimal("200"))
        self.assertEqual(self.cash.solde_theorique, Decimal("-99.75"))

    def test_sql_balance_annotation(self):
        self.adjust()
        self.adjust(sens="sortie", montant=Decimal("5"))
        with self.assertNumQueries(1):
            account = CompteFinancier.avec_soldes().get(pk=self.cash.pk)
            self.assertEqual(account.solde, Decimal("115.50"))
            self.assertIsNotNone(account.derniere_operation)

    def test_initial_not_multiplied_by_joins(self):
        self.adjust()
        self.adjust()
        self.assertEqual(liquidites()["liquidites_par_devise"]["FCFA"], Decimal("140.75"))

    def test_currencies_separate(self):
        self.account(devise="EUR", solde_initial=50)
        self.assertEqual(liquidites()["liquidites_par_devise"], {"FCFA": Decimal("100.25"), "EUR": Decimal("50")})

    def test_sale_creates_correct_entry(self):
        sale = self.sale()
        movement = MouvementFinancier.objects.get(vente=sale)
        self.assertEqual((movement.compte, movement.montant, movement.sens, movement.date_mouvement, movement.cree_par), (self.cash, Decimal("50"), "entree", sale.date_vente, self.users["vendeur"]))
        self.assertRegex(movement.reference, r"^MVT-\d{4}-\d{6,}$")

    def test_sale_double_processing(self):
        sale = self.sale()
        enregistrer_vente(sale)
        sale.save()
        self.assertEqual(MouvementFinancier.objects.count(), 1)

    def test_sale_atomic_failure(self):
        with patch("dashboard.finance_services.MouvementFinancier.objects.create", side_effect=RuntimeError("ledger")):
            with self.assertRaises(RuntimeError):
                self.sale()
        self.assertFalse(Vente.objects.exists())

    def test_paid_entry_date(self):
        when = timezone.now() - timedelta(days=3)
        payment = self.payment(statut="paye", date_paiement=when)
        movement = MouvementFinancier.objects.get(paiement=payment)
        self.assertEqual((movement.compte, movement.montant, movement.date_mouvement), (self.wave, payment.montant, when))

    def test_paid_double_save_notifications_and_ledger(self):
        payment = self.payment()
        payment.statut, payment.date_paiement = "paye", timezone.now()
        payment.save()
        count = payment.commande.utilisateur.notifications.count()
        payment.save()
        enregistrer_paiement(payment)
        self.assertEqual(MouvementFinancier.objects.count(), 1)
        self.assertEqual(payment.commande.utilisateur.notifications.count(), count)

    def test_payment_atomic_failure(self):
        payment = self.payment()
        payment.statut, payment.date_paiement = "paye", timezone.now()
        with patch("dashboard.finance_services.MouvementFinancier.objects.create", side_effect=RuntimeError("ledger")):
            with self.assertRaises(RuntimeError):
                payment.save()
        payment.refresh_from_db()
        self.assertEqual(payment.statut, "en_attente")

    def test_paid_order_cancel_no_refund(self):
        payment = self.payment(statut="paye", date_paiement=timezone.now())
        order = payment.commande
        order.statut = "annulee"
        order.save()
        self.assertEqual(MouvementFinancier.objects.get().sens, "entree")
        self.assertEqual(MouvementFinancier.objects.count(), 1)

    def test_old_paid_save_no_backfill(self):
        payment = self.payment()
        Payment.objects.filter(pk=payment.pk).update(statut="paye", date_paiement=timezone.now())
        payment.refresh_from_db()
        payment.save()
        self.assertFalse(MouvementFinancier.objects.exists())

    def test_zero_payment_no_invented_money(self):
        self.payment(montant=0, statut="paye", date_paiement=timezone.now())
        self.assertFalse(MouvementFinancier.objects.exists())

    def test_missing_payment_date_unassigned(self):
        self.payment(statut="paye")
        movement = MouvementFinancier.objects.get()
        self.assertIsNone(movement.compte_id)
        with self.assertRaises(ValidationError):
            regulariser(movement.pk, self.wave.pk, self.actor)

    def test_expense_draft_no_movement(self):
        self.expense()
        self.assertFalse(MouvementFinancier.objects.exists())

    def test_expense_validation_exit(self):
        expense = self.expense()
        self.validate(expense)
        movement = MouvementFinancier.objects.get(depense=expense)
        self.assertEqual((movement.sens, movement.montant, movement.compte), ("sortie", expense.montant, self.wave))
        self.assertEqual(timezone.localdate(movement.date_mouvement), expense.date_depense)

    def test_double_expense_validation(self):
        expense = self.expense()
        self.validate(expense)
        count = JournalActivite.objects.count()
        self.validate(expense)
        self.assertEqual(MouvementFinancier.objects.count(), 1)
        self.assertEqual(JournalActivite.objects.count(), count)

    def test_expense_cancellation_inverse(self):
        expense = self.expense()
        self.validate(expense)
        self.cancel(expense)
        self.assertEqual(MouvementFinancier.objects.filter(depense=expense).count(), 2)
        self.assertEqual(self.wave.solde_theorique, 0)
        self.assertTrue(Depense.objects.filter(pk=expense.pk).exists())

    def test_double_expense_cancellation(self):
        expense = self.expense()
        self.validate(expense)
        self.cancel(expense)
        count = JournalActivite.objects.count()
        self.cancel(expense)
        self.assertEqual(MouvementFinancier.objects.count(), 2)
        self.assertEqual(JournalActivite.objects.count(), count)

    def test_cancellation_retains_original_account(self):
        expense = self.expense()
        self.validate(expense)
        self.wave.est_par_defaut = False
        self.wave.save()
        self.account(type_compte="wave", est_par_defaut=True)
        self.cancel(expense)
        self.assertEqual(MouvementFinancier.objects.get(type_mouvement="annulation").compte, self.wave)

    def test_historical_cancellation_not_invented_balance(self):
        expense = self.expense()
        Depense.objects.filter(pk=expense.pk).update(statut="validee", date_validation=timezone.now(), validee_par=self.actor)
        self.cancel(expense)
        movement = MouvementFinancier.objects.get()
        self.assertIsNone(movement.compte_id)
        with self.assertRaises(ValidationError):
            regulariser(movement.pk, self.wave.pk, self.actor)

    def test_missing_default_preserves_sale(self):
        sale = self.sale(methode_paiement="moov_money")
        movement = MouvementFinancier.objects.get(vente=sale)
        self.assertIsNone(movement.compte_id)
        self.assertEqual(movement.type_compte_attendu, "moov_money")
        self.assertContains(self.client.get(reverse("comptable_regularisations")), movement.reference)

    def test_inactive_account_not_auto_used(self):
        self.wave.actif = False
        self.wave.save()
        self.payment(statut="paye", date_paiement=timezone.now())
        self.assertIsNone(MouvementFinancier.objects.get().compte_id)

    def test_regularization_incompatible(self):
        movement = self.sale(methode_paiement="moov_money").mouvements_financiers.get()
        with self.assertRaises(ValidationError):
            regulariser(movement.pk, self.cash.pk, self.actor)

    def test_regularization_currency_refused(self):
        movement = self.sale(methode_paiement="moov_money").mouvements_financiers.get()
        other = self.account(type_compte="moov_money", devise="EUR")
        with self.assertRaises(ValidationError):
            regulariser(movement.pk, other.pk, self.actor)

    def test_regularization_and_double_audit(self):
        movement = self.sale(methode_paiement="moov_money").mouvements_financiers.get()
        account = self.account(type_compte="moov_money")
        regulariser(movement.pk, account.pk, self.actor)
        regulariser(movement.pk, account.pk, self.actor)
        movement.refresh_from_db()
        self.assertEqual(movement.compte, account)
        self.assertEqual(JournalActivite.objects.count(), 1)

    def test_regularization_pair_net_zero(self):
        self.wave.est_par_defaut = False
        self.wave.save()
        expense = self.expense()
        self.validate(expense)
        self.cancel(expense)
        movement = MouvementFinancier.objects.get(type_mouvement="depense")
        regulariser(movement.pk, self.wave.pk, self.actor)
        self.assertFalse(MouvementFinancier.objects.filter(compte__isnull=True).exists())
        self.assertEqual(self.wave.solde_theorique, 0)

    def test_inactive_reversal_regularization(self):
        expense = self.expense()
        self.validate(expense)
        self.wave.actif = False
        self.wave.save()
        self.cancel(expense)
        inverse = MouvementFinancier.objects.get(type_mouvement="annulation")
        self.assertIsNone(inverse.compte_id)
        self.wave.actif = True
        self.wave.save()
        regulariser(inverse.pk, self.wave.pk, self.actor)
        self.assertEqual(self.wave.solde_theorique, 0)

    def test_transfer_pair(self):
        transfer = self.transfer()
        self.assertRegex(transfer.reference, r"^TRF-\d{4}-\d{6,}$")
        self.assertEqual(transfer.mouvements.count(), 2)
        self.assertEqual(transfer.mouvements.get(sens="sortie").compte, self.cash)
        self.assertEqual(transfer.mouvements.get(sens="entree").compte, self.wave)
        self.assertEqual(self.cash.solde_theorique, Decimal("74.75"))
        self.assertEqual(self.wave.solde_theorique, Decimal("25.50"))

    def test_transfer_atomic_pair_failure(self):
        create = MouvementFinancier.objects.create
        calls = []
        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise RuntimeError("second leg")
            return create(**kwargs)
        with patch("dashboard.finance_services.MouvementFinancier.objects.create", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                self.transfer()
        self.assertFalse(TransfertFinancier.objects.exists())
        self.assertFalse(MouvementFinancier.objects.exists())
        self.assertFalse(JournalActivite.objects.exists())

    def test_transfer_duplicate_token(self):
        key = uuid.uuid4()
        first = self.transfer(cle_operation=key)
        self.assertEqual(self.transfer(cle_operation=key).pk, first.pk)
        self.assertEqual(MouvementFinancier.objects.count(), 2)
        self.assertEqual(JournalActivite.objects.count(), 1)

    def test_transfer_same_account_refused(self):
        with self.assertRaises(ValidationError):
            self.transfer(destination_id=self.cash.pk)

    def test_transfer_currency_refused(self):
        account = self.account(devise="EUR")
        with self.assertRaises(ValidationError):
            self.transfer(destination_id=account.pk)

    def test_transfer_inactive_refused(self):
        self.wave.actif = False
        self.wave.save()
        with self.assertRaises(ValidationError):
            self.transfer()

    def test_transfer_negative_balance_allowed(self):
        self.transfer(montant=200)
        self.assertLess(self.cash.solde_theorique, 0)

    def test_adjustment_reason_required(self):
        with self.assertRaises(ValidationError):
            self.adjust(motif="   ")

    def test_adjustment_inactive_refused(self):
        self.cash.actif = False
        self.cash.save()
        with self.assertRaises(ValidationError):
            self.adjust()

    def test_adjustment_duplicate_token(self):
        key = uuid.uuid4()
        self.adjust(cle_operation=key)
        self.adjust(cle_operation=key)
        self.assertEqual(MouvementFinancier.objects.count(), 1)
        self.assertEqual(JournalActivite.objects.count(), 1)

    def test_movement_instance_immutable(self):
        movement = self.adjust()
        movement.montant = 10
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()

    def test_movement_queryset_immutable(self):
        self.adjust()
        with self.assertRaises(ValidationError):
            MouvementFinancier.objects.update(montant=1)
        with self.assertRaises(ValidationError):
            MouvementFinancier.objects.all().delete()

    def test_no_edit_delete_ui(self):
        movement = self.adjust()
        for action in ("modifier", "supprimer"):
            self.assertEqual(self.client.post(f"/dashboard/comptable/mouvements/{movement.pk}/{action}/").status_code, 404)

    def test_dashboard_preserves_ca_expenses_result(self):
        self.sale()
        self.payment(statut="paye", date_paiement=timezone.now())
        expense = self.expense()
        self.validate(expense)
        self.adjust(montant=999)
        response = self.client.get(reverse("comptable_dashboard"))
        self.assertEqual(response.context["total_jour"], Decimal("70.25"))
        self.assertEqual(response.context["depenses_jour"], Decimal("15.50"))
        self.assertEqual(response.context["resultat_jour"], Decimal("54.75"))
        self.assertContains(response, "Liquidités théoriques")

    def test_filter_period(self):
        old = self.adjust(date_mouvement=timezone.now()-timedelta(days=4))
        new = self.adjust()
        self.assertEqual([r.pk for r in self.rows(date_debut=timezone.localdate().isoformat())], [new.pk])

    def test_filter_account(self):
        cash = self.adjust()
        self.adjust(compte_id=self.wave.pk)
        self.assertEqual([m.pk for m in self.rows(compte=self.cash.pk)], [cash.pk])

    def test_filter_type_compte(self):
        self.adjust()
        self.assertEqual(self.rows(type_compte="wave"), [])

    def test_filter_type_movement(self):
        self.adjust()
        sale = self.sale()
        self.assertEqual(self.rows(type_mouvement="vente")[0].vente, sale)

    def test_filter_sens(self):
        self.adjust()
        self.assertEqual(self.rows(sens="sortie"), [])

    def test_filter_search(self):
        self.adjust(motif="Comptage exceptionnel")
        self.assertEqual(len(self.rows(q="exceptionnel")), 1)
        self.assertEqual(self.rows(q="introuvable"), [])

    def test_invalid_filters_empty(self):
        self.adjust()
        self.assertEqual(self.rows(date_debut="incorrect"), [])

    def test_pagination_stable(self):
        when = timezone.now()
        for i in range(27):
            self.adjust(date_mouvement=when)
        response = self.client.get(reverse("comptable_mouvements"))
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertEqual([m.pk for m in response.context["page_obj"]], list(MouvementFinancier.objects.order_by("-pk").values_list("pk", flat=True)[:25]))

    def test_export_bom_filters_formula(self):
        self.adjust(motif="  =HYPERLINK(1)")
        self.adjust(sens="sortie", motif="Exclu")
        response = self.client.get(reverse("comptable_mouvements_export"), {"sens": "entree"})
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1][7].startswith("'"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_csrf_required(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.actor)
        self.assertEqual(client.post(reverse("comptable_compte_toggle", args=[self.cash.pk])).status_code, 403)

    def test_toggle_post_only(self):
        self.assertEqual(self.client.get(reverse("comptable_compte_toggle", args=[self.cash.pk])).status_code, 405)

    def test_toggle_retains_balance(self):
        self.adjust()
        response = self.client.post(reverse("comptable_compte_toggle", args=[self.cash.pk]))
        self.assertEqual(response.status_code, 302)
        self.cash.refresh_from_db()
        self.assertFalse(self.cash.actif)
        self.assertEqual(self.cash.solde_theorique, Decimal("120.50"))

    def test_signed_adjustment_form_repeat(self):
        url = reverse("comptable_ajustement_nouveau")
        response = self.client.get(url)
        data = dict(compte=self.cash.pk, sens="entree", montant="10", motif="Correction autorisée", date=timezone.now().isoformat(), jeton=response.context["form"].initial["jeton"])
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(MouvementFinancier.objects.count(), 1)

    def test_forged_token_refused(self):
        response = self.client.post(reverse("comptable_ajustement_nouveau"), dict(compte=self.cash.pk, sens="entree", montant="10", motif="Motif", date=timezone.now().isoformat(), jeton="forged"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MouvementFinancier.objects.exists())

    def test_offline_financial_data_absent(self):
        self.adjust(motif="Secret financier unique")
        response = self.client.get("/offline/sync/")
        self.assertNotIn(b"Secret financier unique", response.content)
        worker = (Path(settings.BASE_DIR) / "static/service-worker.js").read_text(encoding="utf-8")
        self.assertIn('pathname.startsWith("/dashboard/comptable/")', worker)
        self.assertIn('cache: "no-store"', worker)


def _access_test(role, route, detail=False):
    def test(self):
        self.client.force_login(self.users[role])
        response = self.client.get(reverse(route, args=[self.cash.pk] if detail else []))
        self.assertEqual(response.status_code, 200 if role in ("comptable", "admin", "superuser") else 302)
        self.assertIn("no-store", response["Cache-Control"])
    return test


for _role in ("comptable", "admin", "superuser", "vendeur", "client", "staff"):
    for _route in ("comptable_comptes", "comptable_mouvements", "comptable_regularisations", "comptable_compte_nouveau", "comptable_transfert_nouveau", "comptable_ajustement_nouveau", "comptable_mouvements_export", "comptable_compte_detail"):
        setattr(FinanceTests, f"test_permission_{_role}_{_route}", _access_test(_role, _route, _route == "comptable_compte_detail"))


def _method_test(method):
    def test(self):
        expected = "banque" if method == "carte" else method
        account = CompteFinancier.objects.filter(type_compte=expected).first() or self.account(type_compte=expected, est_par_defaut=True)
        payment = self.payment(methode=method, statut="paye", date_paiement=timezone.now())
        self.assertEqual(payment.mouvements_financiers.get().compte, account)
    return test


for _method in ("especes", "wave", "orange_money", "moov_money", "carte"):
    setattr(FinanceTests, "test_payment_routing_" + _method, _method_test(_method))


def _unpaid_test(status):
    def test(self):
        self.payment(statut=status)
        self.assertFalse(MouvementFinancier.objects.exists())
    return test


for _status in ("en_attente", "echoue", "annule"):
    setattr(FinanceTests, "test_payment_no_entry_" + _status, _unpaid_test(_status))


def _invalid_amount_test(value):
    def test(self):
        with self.assertRaises(ValidationError):
            self.adjust(montant=value)
        with self.assertRaises(ValidationError):
            self.transfer(montant=value)
        self.assertFalse(MouvementFinancier.objects.exists())
    return test


for _index, _amount in enumerate((Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), "invalid")):
    setattr(FinanceTests, f"test_invalid_amount_{_index}", _invalid_amount_test(_amount))


def _action_permission_test(role):
    def test(self):
        sale = self.sale(methode_paiement="moov_money")
        movement = sale.mouvements_financiers.get()
        self.client.force_login(self.users[role])
        for route, args, payload in (
            ("comptable_compte_toggle", [self.cash.pk], {}),
            ("comptable_compte_modifier", [self.cash.pk], {"nom": "Hacked"}),
            ("comptable_regularisation_affecter", [movement.pk], {"compte": self.cash.pk}),
            ("comptable_transfert_nouveau", [], {}),
            ("comptable_ajustement_nouveau", [], {}),
        ):
            self.assertEqual(self.client.post(reverse(route, args=args), payload).status_code, 302)
        self.cash.refresh_from_db()
        self.assertTrue(self.cash.actif)
        movement.refresh_from_db()
        self.assertIsNone(movement.compte_id)
        self.assertFalse(TransfertFinancier.objects.exists())
    return test


for _role in ("vendeur", "client", "staff"):
    setattr(FinanceTests, "test_action_permissions_" + _role, _action_permission_test(_role))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinanceConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.actor = User.objects.create_user("finance-concurrent")
        self.source = CompteFinancier.objects.create(nom="Source", type_compte="wave", cree_par=self.actor)
        self.destination = CompteFinancier.objects.create(nom="Destination", type_compte="banque", cree_par=self.actor)

    def race(self, function):
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker) for _ in range(2)]
            return [f.result(timeout=30) for f in futures]

    def test_concurrent_transfer_same_token(self):
        key = uuid.uuid4()
        self.race(lambda: transferer(self.source.pk, self.destination.pk, Decimal("10"), timezone.now(), "Transfert concurrent", self.actor, key).pk)
        self.assertEqual(TransfertFinancier.objects.count(), 1)
        self.assertEqual(MouvementFinancier.objects.count(), 2)
        self.assertEqual(JournalActivite.objects.count(), 1)

    def test_concurrent_regularization(self):
        payment = Payment.objects.create(commande=Order.objects.create(utilisateur=self.actor), montant=10, methode="wave", statut="paye", date_paiement=timezone.now())
        movement = payment.mouvements_financiers.get()
        self.race(lambda: regulariser(movement.pk, self.source.pk, self.actor).pk)
        movement.refresh_from_db()
        self.assertEqual(movement.compte, self.source)
        self.assertEqual(JournalActivite.objects.count(), 1)

    def test_concurrent_payment_processing(self):
        payment = Payment.objects.create(commande=Order.objects.create(utilisateur=self.actor), montant=10, methode="wave")
        Payment.objects.filter(pk=payment.pk).update(statut="paye", date_paiement=timezone.now())
        payment.refresh_from_db()
        self.race(lambda: enregistrer_paiement(payment).pk)
        self.assertEqual(MouvementFinancier.objects.count(), 1)
