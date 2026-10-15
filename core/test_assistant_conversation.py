from unittest.mock import patch

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from categories.models import Category
from products.models import Product
from .assistant import answer_question, detect_intent


class AssistantConversationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.shoes = Category.objects.create(nom='Chaussures', nom_en='Shoes')
        cls.other = Category.objects.create(nom='Accessoires', nom_en='Accessories')
        cls.hidden = Category.objects.create(nom='Invisible', active=False)
        cls.first = Product.objects.create(categorie=cls.shoes, nom='Basket Alpha', nom_en='Alpha sneaker', marque='Nike', prix=12000, stock=3)
        cls.second = Product.objects.create(categorie=cls.shoes, nom='Basket Beta', nom_en='Beta sneaker', marque='Nike', prix=18000, prix_promotion=15000, stock=0)
        cls.third = Product.objects.create(categorie=cls.shoes, nom='Basket Gamma', marque='Adidas', prix=9000)
        Product.objects.create(categorie=cls.other, nom='Sac Nike', marque='Nike', prix=5000)
        Product.objects.create(categorie=cls.shoes, nom='Basket inactive Nike', marque='Nike', prix=1, actif=False)
        Product.objects.create(categorie=cls.hidden, nom='Basket cachée Nike', marque='Nike', prix=1)

    def ask(self, message, state=None, language='fr', context=None):
        return answer_question(message, language, state=state, context=context, request=RequestFactory().get('/'))

    def test_payment_meanings_and_negation_are_distinct(self):
        cases = {
            'Comment marche le paiement en ligne ?': 'PAIEMENT_EN_LIGNE',
            'Mon paiement en ligne a échoué': 'PAIEMENT_ECHOUE',
            'My online payment failed': 'PAIEMENT_ECHOUE',
            'Je ne veux pas payer en ligne': 'PAIEMENT',
            'I do not want to pay online': 'PAIEMENT',
            'Je ne veux pas payer': 'PAIEMENT_REFUSE',
            'I do not want to pay': 'PAIEMENT_REFUSE',
            "J'ai déjà payé": 'PAIEMENT_EFFECTUE',
            'I already paid': 'PAIEMENT_EFFECTUE',
            "Je n'ai pas encore payé": 'PAIEMENT',
            'Payer à la livraison': 'PAIEMENT_LIVRAISON',
            'Can I pay on delivery?': 'PAIEMENT_LIVRAISON',
            'Je veux payer en espèces': 'PAIEMENT_LIVRAISON',
            'My payment does not work': 'PAIEMENT_ECHOUE',
            'My payment works': 'PAIEMENT',
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(detect_intent(message)[0], expected)
        self.assertNotEqual(detect_intent('voir mes commandes en ligne')[0], 'PAIEMENT_EN_LIGNE')
        self.assertNotEqual(detect_intent('browse products online')[0], 'PAIEMENT_EN_LIGNE')

    @override_settings(PAYMENT_PROVIDER='', PAYMENT_SECRET_KEY='')
    def test_online_payment_unavailable_is_truthful(self):
        result = self.ask('how do I pay online', language='en')
        self.assertEqual(result['intent'], 'PAIEMENT_EN_LIGNE')
        self.assertIn('not available', result['answer'])

    @override_settings(PAYMENT_PROVIDER='cinetpay', PAYMENT_SECRET_KEY='', CINETPAY_API_KEY='test', CINETPAY_SITE_ID='test', CINETPAY_SECRET_KEY='test')
    def test_cinetpay_availability_matches_checkout_configuration(self):
        result = self.ask('how do I pay online', language='en')
        self.assertNotIn('not available', result['answer'])

    def test_conjunction_questions_offer_actual_followups(self):
        for message in ('Comment payer et où est ma commande ?', 'How do I pay and where is my order?'):
            with self.subTest(message=message):
                result = self.ask(message)
                self.assertEqual(result['intent'], 'MULTIPLE_QUESTIONS')
                self.assertEqual(len(result['suggestions']), 2)
                self.assertTrue(all(item['message'] for item in result['suggestions']))
        self.assertEqual(self.ask('Orange Money et Wave')['intent'], 'PAIEMENT')

    def test_category_brand_then_price_of_second_real_product(self):
        first = self.ask('je cherche des chaussures')
        self.assertEqual(first['intent'], 'RECHERCHER_PRODUIT')
        self.assertEqual({item['id'] for item in first['results']}, {self.first.pk, self.second.pk, self.third.pk})
        second = self.ask('Nike', first['state'])
        self.assertEqual([item['id'] for item in second['results']], [self.first.pk, self.second.pk])
        third = self.ask('et le prix du deuxième ?', second['state'])
        self.assertEqual(third['intent'], 'PRIX_PRODUIT')
        self.assertIn('15000.00', third['answer'])
        self.assertIn(self.second.nom, third['answer'])
        self.assertEqual(third['results'][0]['price'], '15000.00')
        self.assertFalse(third['results'][0]['available'])
        self.assertEqual(third['results'][0]['stock'], 0)

    def test_english_catalog_and_ordinal_are_localized_without_global_override(self):
        first = self.ask('I am looking for shoes', language='en')
        second = self.ask('Nike', first['state'], language='en')
        result = self.ask('price of the second one', second['state'], language='en')
        self.assertEqual(result['intent'], 'PRIX_PRODUIT')
        self.assertIn('Beta sneaker', result['answer'])
        self.assertNotIn('Basket Beta', result['answer'])

    def test_catalog_reuses_shared_typo_search(self):
        from products.search import search_products
        with patch('products.search.search_products', wraps=search_products) as shared:
            result = self.ask('chercher Nkie')
        self.assertTrue(shared.called)
        self.assertTrue(result['results'])
        self.assertTrue(all('Nike' == Product.objects.get(pk=item['id']).marque for item in result['results']))

    def test_hidden_products_and_categories_never_return(self):
        result = self.ask('chercher Nike')
        self.assertEqual(len(result['results']), 3)
        self.assertTrue(all(Product.objects.filter(pk=item['id'], actif=True, categorie__active=True).exists() for item in result['results']))

    def test_deleted_or_hidden_second_result_is_not_replaced_by_another(self):
        first = self.ask('chercher chaussures')
        self.second.actif = False
        self.second.save(update_fields=['actif'])
        result = self.ask('prix du deuxième', first['state'])
        self.assertEqual(result['intent'], 'PRIX_PRODUIT')
        self.assertNotIn('results', result)
        self.assertNotIn('9000', result['answer'])
        self.assertIn('disponible', result['answer'])

    def test_price_without_selection_asks_for_product(self):
        result = self.ask('quel est son prix')
        self.assertEqual(result['intent'], 'PRIX_PRODUIT')
        self.assertNotIn('results', result)
        self.assertIn('produit', result['answer'])
        first = self.ask('chercher chaussures')
        ambiguous = self.ask('son prix', first['state'])
        self.assertNotIn('results', ambiguous)
        missing = self.ask('prix du cinquième', first['state'])
        self.assertNotIn('results', missing)

    def test_verified_product_page_can_supply_price(self):
        result = self.ask('son prix ?', context=reverse('product_detail', args=[self.second.slug]))
        self.assertEqual(result['results'][0]['id'], self.second.pk)
        self.assertIn('15000.00', result['answer'])
        forged = self.ask('son prix ?', context='https://evil.example/products/' + self.second.slug + '/')
        self.assertNotIn('results', forged)

    def test_new_topic_clears_catalog_context_and_state_is_bounded(self):
        first = self.ask('chercher chaussures')
        result = self.ask('bonjour', first['state'])
        self.assertEqual(result['intent'], 'SALUTATION')
        self.assertEqual(result['state'], {})
        self.assertLessEqual(len(first['state']['product_ids']), 5)
        self.assertLessEqual(len(first['state']['search_query']), 100)
        self.assertNotIn('search_message', first['state'])

    def test_payment_status_response_does_not_claim_verification(self):
        result = self.ask("J'ai déjà payé")
        self.assertEqual(result['intent'], 'PAIEMENT_EFFECTUE')
        self.assertIn('vérifier', result['answer'])
        self.assertNotIn('confirmé', result['answer'])

    def test_price_paraphrases_names_and_stale_selection(self):
        first = self.ask('chercher chaussures')
        result = self.ask('how much is the second one', first['state'], language='en')
        self.assertEqual(result['intent'], 'PRIX_PRODUIT')
        self.assertEqual(result['results'][0]['id'], self.second.pk)
        named = self.ask('prix de Basket Beta')
        self.assertEqual(named['results'][0]['id'], self.second.pk)
        self.assertEqual(self.ask('combien coûte la livraison')['intent'], 'LIVRAISON')
        self.second.categorie.active = False
        self.second.categorie.save(update_fields=['active'])
        hidden = self.ask('son prix', result['state'])
        self.assertNotIn('results', hidden)

    def test_refining_search_does_not_match_filler_or_unrelated_products(self):
        first = self.ask('chercher chaussures')
        second = self.ask('plutôt Nike', first['state'])
        self.assertEqual([item['id'] for item in second['results']], [self.first.pk, self.second.pk])
        repeated = self.ask('yes', second['state'], language='en')
        self.assertEqual([item['id'] for item in repeated['results']], [self.first.pk, self.second.pk])

    def test_negation_scope_does_not_invent_payment_failure_or_refusal(self):
        cases = {
            'Mon paiement n’a pas échoué': 'PAIEMENT',
            'My payment has not failed': 'PAIEMENT',
            'Je ne veux pas annuler mon paiement': 'PAIEMENT',
            'Je ne veux plus payer': 'PAIEMENT_REFUSE',
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(detect_intent(message)[0], expected)

    def test_followup_keeps_new_payment_intent_and_no_raw_message_state(self):
        first = self.ask('payer à la livraison')
        result = self.ask('oui', first['state'])
        self.assertEqual(result['intent'], 'PAIEMENT_LIVRAISON')
        result = answer_question('chercher chaussures')
        self.assertNotIn('search_message', result['state'])

    def test_price_keeps_category_but_next_brand_replaces_previous_brand(self):
        Product.objects.create(categorie=self.other, nom='Sac Adidas', marque='Adidas', prix=3000)
        first = self.ask('chercher chaussures')
        nike = self.ask('Nike', first['state'])
        price = self.ask('prix du deuxième', nike['state'])
        adidas = self.ask('Adidas', price['state'])
        self.assertEqual([item['id'] for item in adidas['results']], [self.third.pk])
        self.assertEqual(adidas['state']['category_id'], self.shoes.pk)

    def test_english_possessive_price_uses_new_product_page_before_old_selection(self):
        shoes = self.ask('I am looking for shoes', language='en')
        nike = self.ask('Nike', shoes['state'], language='en')
        selected = self.ask('How much is the second?', nike['state'], language='en')
        self.assertEqual(selected['results'][0]['id'], self.second.pk)
        result = self.ask('What is its price?', selected['state'], language='en', context=reverse('product_detail', args=[self.first.slug]))
        self.assertEqual(result['intent'], 'PRIX_PRODUIT')
        self.assertEqual(result['results'][0]['id'], self.first.pk)
        self.assertEqual(result['results'][0]['price'], '12000.00')
        followup = self.ask('What is its price?', result['state'], language='en')
        self.assertEqual(followup['results'][0]['id'], self.first.pk)
