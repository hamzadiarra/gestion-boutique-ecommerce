from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from categories.models import Category
from products.models import Product
from .assistant import answer_question, detect_intent


class AssistantStockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(nom='Chaussures', nom_en='Shoes')
        cls.first = Product.objects.create(categorie=cls.category, nom='Alpha', nom_en='Alpha shoe', prix=10, stock=3)
        cls.second = Product.objects.create(categorie=cls.category, nom='Beta', nom_en='Beta shoe', prix=20, stock=0)
        cls.hidden = Product.objects.create(categorie=cls.category, nom='Secret', prix=30, stock=10, actif=False)

    def ask(self, message, state=None, language='fr', context=None):
        return answer_question(message, language, state=state, context=context, request=RequestFactory().get('/'))

    def test_named_product_stock_in_both_languages(self):
        for message, lang, status, pk in [('Alpha est disponible ?', 'fr', 'available', self.first.pk), ('Is Beta in stock?', 'en', 'out_of_stock', self.second.pk)]:
            with self.subTest(message=message):
                result = self.ask(message, language=lang)
                self.assertEqual(result['intent'], 'STOCK_PRODUIT')
                self.assertEqual(result['availability'], status)
                self.assertEqual(result['results'][0]['id'], pk)

    def test_stock_quantity_precedes_price(self):
        for message in ('combien en reste', 'how many left', 'combien reste-t-il de Alpha'):
            self.assertEqual(detect_intent(message)[0], 'STOCK_PRODUIT')

    def test_unknown_and_nonexistent_hidden_are_distinct(self):
        self.assertEqual(self.ask('en stock ?')['availability'], 'unknown')
        missing = self.ask('Neverexist est disponible ?')
        hidden = self.ask('Secret est disponible ?')
        self.assertEqual(missing['availability'], 'not_found')
        self.assertEqual(missing['answer'], hidden['answer'])
        self.assertNotIn('results', hidden)

    def test_category_counts_full_public_in_stock_set(self):
        for n in range(7):
            Product.objects.create(categorie=self.category, nom=f'Shoe {n}', prix=1, stock=1)
        result = self.ask('chaussures disponibles ?')
        self.assertEqual(result['available_count'], 8)
        self.assertLessEqual(len(result['results']), 5)
        self.assertTrue(all(item['available'] for item in result['results']))
        result = self.ask('what is in stock in this category?', language='en', context=reverse('category_detail', args=[self.category.slug]))
        self.assertEqual(result['available_count'], 8)

    def test_search_stock_second_price_preserves_order_and_selection(self):
        search = self.ask('chercher chaussures')
        stock = self.ask('et le deuxième en stock ?', search['state'])
        self.assertEqual(stock['availability'], 'out_of_stock')
        self.assertEqual(stock['state']['product_ids'], search['state']['product_ids'])
        price = self.ask('son prix ?', stock['state'])
        self.assertEqual(price['results'][0]['id'], self.second.pk)

    def test_ambiguous_then_ordinal_and_fresh_stock(self):
        search = self.ask('chercher chaussures')
        ambiguous = self.ask('est-il disponible ?', search['state'])
        self.assertEqual(ambiguous['availability'], 'ambiguous')
        selected = self.ask('le premier', ambiguous['state'])
        self.assertEqual(selected['results'][0]['id'], self.first.pk)
        Product.objects.filter(pk=self.first.pk).update(stock=0)
        fresh = self.ask('encore disponible ?', selected['state'])
        self.assertEqual(fresh['availability'], 'out_of_stock')

    def test_hidden_selection_never_falls_back(self):
        search = self.ask('chercher chaussures')
        Product.objects.filter(pk=self.second.pk).update(actif=False)
        result = self.ask('le deuxième en stock ?', search['state'])
        self.assertEqual(result['availability'], 'not_found')
        self.assertNotIn('results', result)

    def test_variants_cannot_be_verified(self):
        for message in ('Alpha disponible en taille 42 ?', 'Is Alpha in stock in red?', 'Alpha disponible en bleu ?'):
            self.assertEqual(self.ask(message)['availability'], 'unknown')

    def test_reads_only_and_bounded_query_budget(self):
        with CaptureQueriesContext(connection) as queries:
            result = self.ask('Alpha en stock ?')
        self.assertEqual(result['availability'], 'available')
        self.assertLessEqual(len(queries), 12)
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in queries))
        self.first.refresh_from_db()
        self.assertEqual(self.first.stock, 3)

    def test_empty_and_hidden_category(self):
        Product.objects.filter(categorie=self.category).update(stock=0)
        self.assertEqual(self.ask('chaussures en stock ?')['available_count'], 0)
        self.category.active = False
        self.category.save(update_fields=['active'])
        self.assertEqual(self.ask('Alpha en stock ?')['availability'], 'not_found')

    def test_generic_category_page_and_stock_continuation(self):
        result = self.ask('encore disponible ?', context=reverse('category_detail', args=[self.category.slug]))
        self.assertEqual(result['available_count'], 1)
        selected = self.ask('Alpha en stock ?')
        self.assertEqual(self.ask('oui', selected['state'])['availability'], 'available')
        self.assertEqual(self.ask('how many Alpha left?', language='en')['availability'], 'available')

    def test_have_model_phrases_and_current_page_precedence(self):
        context = reverse('product_detail', args=[self.first.slug])
        selected = self.ask('Beta en stock ?')['state']
        for message in ('Avez-vous encore ce modèle ?', 'Ce produit est disponible ?'):
            result = self.ask(message, selected, context=context)
            self.assertEqual(result['results'][0]['id'], self.first.pk)
        self.assertEqual(self.ask('Avez-vous ce modèle en taille 42 ?', context=context)['availability'], 'unknown')
        self.assertEqual(detect_intent('Est-ce que vous avez des chaussures Nike ?')[0], 'STOCK_PRODUIT')

    def test_full_category_questions(self):
        for message in ('Combien de produits sont en stock dans la catégorie chaussures ?', 'How many products are in stock in the shoes category?'):
            self.assertEqual(self.ask(message)['available_count'], 1)

    def test_stock_data_error_is_unknown(self):
        from unittest.mock import patch
        from django.db import DatabaseError
        with patch('core.assistant._public_products', side_effect=DatabaseError('private database details')):
            result = self.ask('Alpha en stock ?')
        self.assertEqual(result['availability'], 'unknown')
        self.assertNotIn('private', result['answer'])

    def test_english_price_followup_after_stock(self):
        search = self.ask('find shoes', language='en')
        stock = self.ask('second in stock?', search['state'], language='en')
        price = self.ask('And how much does it cost?', stock['state'], language='en')
        self.assertEqual(price['results'][0]['id'], self.second.pk)

    def test_numeric_model_is_not_an_ordinal(self):
        phone = Product.objects.create(categorie=self.category, nom='iPhone 7', prix=70, stock=4)
        state = self.ask('chercher chaussures')['state']
        for message in ('iPhone 7 en stock ?', 'prix de iPhone 7'):
            self.assertEqual(self.ask(message, state)['results'][0]['id'], phone.pk)
        stock = self.ask('Alpha en stock ?')
        self.assertEqual(self.ask('1', stock['state'])['results'][0]['id'], self.first.pk)

    def test_requested_quantity_is_not_ordinal_or_stock_confirmation(self):
        state = self.ask('chercher chaussures')['state']
        for message in ('Avez-vous 2 Alpha en stock ?', 'Do you have 20 Alpha in stock?'):
            result = self.ask(message, state)
            self.assertEqual(result['availability'], 'unknown')
            self.assertNotIn('results', result)

    def test_service_availability_keeps_service_intent(self):
        for message, expected in [('Quels moyens de paiement sont disponibles ?', 'PAIEMENT'), ('What payment methods are available?', 'PAIEMENT'), ('La livraison express est disponible ?', 'LIVRAISON')]:
            self.assertEqual(detect_intent(message)[0], expected)
