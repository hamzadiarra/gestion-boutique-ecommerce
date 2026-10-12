from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.utils import translation
from .templatetags.navigation import back_navigation


class BackNavigationTests(SimpleTestCase):
    def test_server_error_template_renders_without_request(self):
        with translation.override("fr"):
            self.assertIn("Un problème est survenu", render_to_string("500.html"))

    def test_external_referrer_uses_local_fallback(self):
        request = RequestFactory().get("/products/example/", HTTP_REFERER="https://evil.example/login")
        self.assertEqual(back_navigation({"request": request})["back_url"], "/products/")

    def test_local_referrer_preserves_filters_and_pagination(self):
        request = RequestFactory().get("/products/example/", HTTP_REFERER="http://testserver/products/?categorie=2&q=lait&page=3")
        self.assertEqual(back_navigation({"request": request})["back_url"], "/products/?categorie=2&q=lait&page=3")

    def test_checkout_keeps_its_existing_cart_return(self):
        request = RequestFactory().get("/orders/create/")
        self.assertFalse(back_navigation({"request": request})["show_back"])
