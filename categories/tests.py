from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from .models import Category


class CategoryLocalizationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            nom="Lait", nom_en="Milk",
            description="Description française", description_en="English description",
        )

    def test_localized_name_uses_french_and_english_values(self):
        with translation.override("fr"):
            self.assertEqual(self.category.localized_name, "Lait")
        with translation.override("en"):
            self.assertEqual(self.category.localized_name, "Milk")
            self.category.nom_en = ""
            self.assertEqual(self.category.localized_name, "Lait")

    def test_localized_description_falls_back_to_french(self):
        with translation.override("fr"):
            self.assertEqual(self.category.localized_description, "Description française")
        with translation.override("en"):
            self.assertEqual(self.category.localized_description, "English description")
            self.category.description_en = ""
            self.assertEqual(self.category.localized_description, "Description française")
    def test_category_list_and_detail_render_english_name_and_description(self):
        self.client.cookies["django_language"] = "en"
        listing = self.client.get(reverse("category_list"))
        self.assertContains(listing, "Milk")
        detail = self.client.get(reverse("category_detail", args=[self.category.slug]))
        self.assertContains(detail, "Milk")
        self.assertContains(detail, "English description")
        self.assertNotContains(detail, "Description française")

    def test_category_detail_falls_back_to_french_content(self):
        self.category.nom_en = ""
        self.category.description_en = ""
        self.category.save(update_fields=["nom_en", "description_en", "date_modification"])
        self.client.cookies["django_language"] = "en"
        response = self.client.get(reverse("category_detail", args=[self.category.slug]))
        self.assertContains(response, "Lait")
        self.assertContains(response, "Description française")
