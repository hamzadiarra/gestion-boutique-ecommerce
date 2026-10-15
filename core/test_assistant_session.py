import time
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from categories.models import Category
from products.models import Product
from orders.models import Order


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AssistantSessionTests(TestCase):
    def setUp(self):
        cache.clear(); self.addCleanup(cache.clear)
        self.user = User.objects.create_user("assistant-session")
        self.client.force_login(self.user)
        self.category = Category.objects.create(nom="Chaussures")
        self.product = Product.objects.create(nom="Nike test", categorie=self.category, prix=12500, stock=3)

    def ask(self, message="je veux payer", **extra):
        return self.client.post(reverse("assistant_ask"), {"message": message, **extra}, content_type="application/json")

    def test_expired_and_turn_limited_state_no_longer_drives_followup(self):
        for meta in ({"updated_at": time.time()-901, "turns": 1}, {"updated_at": time.time(), "turns": 12}):
            session = self.client.session
            session["assistant_state"] = {"intent": "PAIEMENT", "step": "CONTINUE"}
            session["assistant_meta"] = meta
            session.save()
            self.assertNotEqual(self.ask("oui").json()["intent"], "PAIEMENT")

    def test_current_state_continues_but_different_session_cannot_see_it(self):
        self.ask()
        self.assertEqual(self.ask("oui").json()["intent"], "PAIEMENT")
        other = Client()
        response = other.post(reverse("assistant_ask"), {"message": "oui"}, content_type="application/json")
        self.assertNotEqual(response.json()["intent"], "PAIEMENT")

    def test_request_replay_does_not_advance_turns_and_conflicting_reuse_is_rejected(self):
        response = self.ask(request_id="request-1")
        self.assertEqual(response.status_code, 200)
        before = self.client.session.get("assistant_meta", {}).get("turns")
        self.assertIsNotNone(before)
        self.assertEqual(self.ask(request_id="request-1").status_code, 200)
        self.assertEqual(self.client.session["assistant_meta"]["turns"], before)
        self.assertEqual(self.ask("bonjour", request_id="request-1").status_code, 409)
        self.assertEqual(self.ask(request_id="x"*65).status_code, 400)

    def test_overlapping_requests_in_same_session_are_rejected(self):
        other = Client(); other.cookies = self.client.cookies.copy()
        nested = []; entered = False
        def slow_answer(*args, **kwargs):
            nonlocal entered
            if not entered:
                entered = True
                nested.append(other.post(reverse("assistant_ask"), {"message":"bonjour"}, content_type="application/json").status_code)
            return {"intent":"SALUTATION", "answer":"Bonjour", "actions":[], "state":{}}
        with patch("core.views.answer_question", side_effect=slow_answer):
            self.assertEqual(self.ask("bonjour").status_code, 200)
        self.assertEqual(nested, [409])
        self.assertEqual(self.ask("bonjour").status_code, 200)

    def test_browser_context_resolved_and_private_or_hidden_targets_ignored(self):
        routes = [("/", "home"), ("/products/?q=Nike", "catalogue"),
                  (reverse("product_detail", args=[self.product.slug]), "product"),
                  ("/cart/", "cart"), ("/orders/create/", "checkout"), ("/orders/my-orders/", "orders")]
        for url, kind in routes:
            self.assertEqual(self.ask("bonjour", context=url).json().get("page_context"), kind)
        foreign = Order.objects.create(utilisateur=User.objects.create_user("other-owner"))
        for url in ("https://outside.example/products/", "//outside.example/", "/dashboard/security/", reverse("order_detail", args=[foreign.pk])):
            self.assertEqual(self.ask("bonjour", context=url).json().get("page_context"), "unknown")
        self.category.active=False; self.category.save()
        self.assertEqual(self.ask("bonjour", context=reverse("product_detail", args=[self.product.slug])).json().get("page_context"), "unknown")

    def test_session_state_does_not_persist_arbitrary_or_unbounded_fields(self):
        with patch("core.views.answer_question", return_value={"intent":"RECHERCHER_PRODUIT", "answer":"test", "actions":[], "state":{"intent":"RECHERCHER_PRODUIT", "step":"CONTINUE", "product_ids":list(range(1,100)), "search_query":"a"*500, "secret":"discard"}}):
            self.assertEqual(self.ask().status_code, 200)
        state = self.client.session["assistant_state"]
        self.assertNotIn("secret", state)
        self.assertLessEqual(len(state.get("product_ids", [])), 5)
        self.assertLessEqual(len(state.get("search_query", "")), 100)

    def test_client_supplied_state_cannot_choose_another_users_order(self):
        foreign = Order.objects.create(utilisateur=User.objects.create_user("secret-owner"))
        response = self.ask(str(foreign.pk), state={"intent":"SUIVRE_COMMANDE", "step":"ASK_ORDER_NUMBER"})
        self.assertNotIn(reverse("order_detail",args=[foreign.pk]), str(response.json()))

    def test_anonymous_conversation_sets_session_cookie_and_continues(self):
        anonymous = Client()
        first=anonymous.post(reverse("assistant_ask"), {"message":"je veux payer"}, content_type="application/json")
        self.assertEqual(first.status_code,200)
        continued=anonymous.post(reverse("assistant_ask"), {"message":"oui"}, content_type="application/json")
        self.assertEqual(continued.json()["intent"],"PAIEMENT")

    def test_malformed_page_hint_is_ignored(self):
        self.assertEqual(self.ask("bonjour",context="//[").json().get("page_context"),"unknown")

    def test_retry_preserves_support_escalation_without_advancing_failures(self):
        for number in range(3):
            original = self.ask("zzqqxx", request_id=f"unknown-{number}")
        retried = self.ask("zzqqxx", request_id="unknown-2")
        self.assertEqual(retried.json()["answer"], original.json()["answer"])
        self.assertEqual(retried.json()["actions"], original.json()["actions"])
        self.assertEqual(self.client.session["assistant_failures"], 3)
        self.assertEqual(self.client.session["assistant_meta"]["turns"], 3)
