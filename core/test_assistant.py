from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from categories.models import Category
from products.models import Product
from orders.models import Order

from .assistant import answer_question, detect_intent, explain_detection


class AssistantGuideTests(TestCase):
    EN_HOLDOUT_CASES = (
        ("Good day, I am here", "SALUTATION"),
        ("Hey there", "SALUTATION"),
        ("I really appreciate it", "MERCI"),
        ("Thanks for your help", "MERCI"),
        ("Can you explain this store", "COMMENT_CA_MARCHE"),
        ("I just joined this site", "COMMENT_CA_MARCHE"),
        ("Where do I begin as a new customer", "COMMENT_CA_MARCHE"),
        ("What are the steps to shop", "COMMENT_CA_MARCHE"),
        ("I need to purchase an item", "PASSER_COMMANDE"),
        ("What is the way to place my purchase", "PASSER_COMMANDE"),
        ("I would like to make an order", "PASSER_COMMANDE"),
        ("Which ways are available for payment", "PAIEMENT"),
        ("Can I use a bank card to pay", "PAIEMENT"),
        ("I need to pay for my purchase", "PAIEMENT"),
        ("Signing in to my account is not working", "PROBLEME_CONNEXION"),
        ("I am unable to enter my account", "PROBLEME_CONNEXION"),
        ("My account access has failed", "PROBLEME_CONNEXION"),
        ("I need to recover my forgotten password", "MOT_DE_PASSE_OUBLIE"),
        ("My password is no longer in my memory", "MOT_DE_PASSE_OUBLIE"),
        ("Can I create a new password", "MOT_DE_PASSE_OUBLIE"),
        ("Can you tell me the progress of my purchase", "SUIVRE_COMMANDE"),
        ("I need an update on my order", "SUIVRE_COMMANDE"),
        ("Has my package started its journey", "SUIVRE_COMMANDE"),
        ("How long until my shipment arrives", "LIVRAISON"),
        ("I need information about shipping", "LIVRAISON"),
        ("Can I see the items in your store", "DECOUVRIR_CATALOGUE"),
        ("Which goods are currently offered", "DECOUVRIR_CATALOGUE"),
        ("I need to locate some milk", "RECHERCHER_PRODUIT"),
        ("Please look for an item for me", "RECHERCHER_PRODUIT"),
        ("I want to update my account details", "MODIFIER_PROFIL"),
    )

    HOLDOUT_CASES = (
        ("je débarque sur ce site je fais quoi", "COMMENT_CA_MARCHE"),
        ("c'est ma première visite", "COMMENT_CA_MARCHE"),
        ("je débute ici", "COMMENT_CA_MARCHE"),
        ("par où commencer", "COMMENT_CA_MARCHE"),
        ("je veux découvrir cette boutique", "COMMENT_CA_MARCHE"),
        ("mon accès ne passe plus", "PROBLEME_CONNEXION"),
        ("impossible d'ouvrir mon compte", "PROBLEME_CONNEXION"),
        ("je suis bloqué pour entrer", "PROBLEME_CONNEXION"),
        ("je veux régler ma facture", "PAIEMENT"),
        ("où choisir mon moyen de règlement", "PAIEMENT"),
        ("je n'arrive pas à payer", "PAIEMENT"),
        ("mon paiement ne passe plus", "PAIEMENT_ECHOUE"),
        ("où en est mon colis", "SUIVRE_COMMANDE"),
        ("ma livraison avance comment", "SUIVRE_COMMANDE"),
        ("je voudrais connaître l'état de mon colis", "SUIVRE_COMMANDE"),
        ("mon achat est-il en route", "SUIVRE_COMMANDE"),
        ("qu'est-ce que vous avez", "DECOUVRIR_CATALOGUE"),
        ("montrez-moi vos articles", "DECOUVRIR_CATALOGUE"),
        ("je veux voir vos rayons", "DECOUVRIR_CATALOGUE"),
        ("quelles sont vos offres", "DECOUVRIR_CATALOGUE"),
        ("je veux trouver un produit", "RECHERCHER_PRODUIT"),
        ("aidez-moi à trouver un article", "RECHERCHER_PRODUIT"),
        ("je ne sais pas dans quel rayon chercher", "RECHERCHER_PRODUIT"),
        ("où voir les produits", "DECOUVRIR_CATALOGUE"),
        ("mon colis est en route", "SUIVRE_COMMANDE"),
        ("quand vais-je être livré", "LIVRAISON"),
        ("je voudrais changer mes informations", "MODIFIER_PROFIL"),
        ("où mettre à jour mon profil", "MODIFIER_PROFIL"),
        ("je ne me rappelle plus de mon code", "MOT_DE_PASSE_OUBLIE"),
        ("comment récupérer l'accès à mon compte", "MOT_DE_PASSE_OUBLIE"),
        ("salut, je peux faire quoi", "COMMENT_CA_MARCHE"),
        ("merci beaucoup", "MERCI"),
    )
    def test_required_intents_and_fallback(self):
        cases = {
            "je veux acheter": "PASSER_COMMANDE",
            "j'ai oublié mon mot de passe": "MOT_DE_PASSE_OUBLIE",
            "chercher un produit": "RECHERCHER_PRODUIT",
            "voir mon panier": "VOIR_PANIER",
            "comment payer en ligne": "PAIEMENT_EN_LIGNE",
            "suivre ma commande": "SUIVRE_COMMANDE",
            "modifier mon profil": "MODIFIER_PROFIL",
        }
        for question, expected in cases.items():
            self.assertEqual(detect_intent(question)[0], expected)
        self.assertEqual(detect_intent("une question incompréhensible")[0], "AIDE_GENERALE")

    def test_common_typos_and_short_questions(self):
        cases = {
            "comment payer": "PAIEMENT", "comment paye": "PAIEMENT", "coment payer": "PAIEMENT",
            "je veux payé": "PAIEMENT", "paiment": "PAIEMENT", "orange money": "PAIEMENT",
            "mot passe oublier": "MOT_DE_PASSE_OUBLIE", "mdp oublié": "MOT_DE_PASSE_OUBLIE",
            "comment achete": "PASSER_COMMANDE", "comande": "PASSER_COMMANDE",
            "ou est ma commande": "SUIVRE_COMMANDE", "suivi comande": "SUIVRE_COMMANDE",
            "livraision": "LIVRAISON", "produi lait": "RECHERCHER_PRODUIT",
            "modifier profil": "MODIFIER_PROFIL", "mes favoris": "FAVORIS",
        }
        for question, expected in cases.items():
            self.assertEqual(detect_intent(question)[0], expected, question)

    def test_application_guide_questions(self):
        for question in (
            "je veux comprendre le fonctionne de l'application",
            "comment ca marche",
            "comment utiliser l'application",
            "explique moi l'application",
            "how does the app work",
        ):
            self.assertEqual(detect_intent(question)[0], "COMMENT_CA_MARCHE", question)
        visitor_answer = answer_question("comment ca marche", "fr", authenticated=False)
        self.assertIn("application", visitor_answer["answer"])
        self.assertEqual([item["url"] for item in visitor_answer["actions"]], ["/products/", "/categories/", "/accounts/register/", "/accounts/login/"])
        client_answer = answer_question("how to use the app", "en", authenticated=True)
        self.assertIn("application", client_answer["answer"])
        self.assertIn("/orders/my-orders/", [item["url"] for item in client_answer["actions"]])

    def test_concept_generalization_and_social_or_ambiguous_inputs(self):
        cases = {
            "je veux comprendre votre boutique": "COMMENT_CA_MARCHE",
            "j'aimerais savoir à quoi sert cette boutique": "COMMENT_CA_MARCHE",
            "je comprends pas trop comment votre site marche": "COMMENT_CA_MARCHE",
            "on fait quoi sur cette plateforme": "COMMENT_CA_MARCHE",
            "cette boutiq fonctionne coment": "COMMENT_CA_MARCHE",
            "comment je règle mes achats": "PAIEMENT",
            "je voudrais savoir où en est mon achat": "SUIVRE_COMMANDE",
            "j'ai un problème": "NEEDS_CLARIFICATION",
            "ça ne marche pas": "NEEDS_CLARIFICATION",
            "bonjour": "SALUTATION",
            "merci": "MERCI",
        }
        for question, expected in cases.items():
            self.assertEqual(detect_intent(question)[0], expected, question)
        diagnostic = explain_detection("je veux comprendre votre boutique")
        self.assertEqual(diagnostic["selected"], "COMMENT_CA_MARCHE")
        self.assertIn("APP", diagnostic["concepts"])
        self.assertIn("UNDERSTAND", diagnostic["concepts"])

    def test_holdout_accuracy_is_at_least_ninety_percent(self):
        results = [(question, expected, detect_intent(question)[0]) for question, expected in self.HOLDOUT_CASES]
        correct = sum(expected == actual for _, expected, actual in results)
        self.assertGreaterEqual(correct / len(results), 0.90, results)

    def test_english_holdout_accuracy_is_at_least_ninety_percent(self):
        results = [(question, expected, detect_intent(question)[0]) for question, expected in self.EN_HOLDOUT_CASES]
        correct = sum(expected == actual for _, expected, actual in results)
        self.assertGreaterEqual(correct / len(results), 0.90, results)

    @override_settings(LANGUAGE_CODE="en")
    def test_real_english_endpoint_cases(self):
        cases = (
            ("HI", "SALUTATION"),
            ("I'm new here, what should I do?", "COMMENT_CA_MARCHE"),
            ("I can't get into my account", "PROBLEME_CONNEXION"),
            ("How do I pay for what I bought?", "PAIEMENT"),
            ("Where is my order?", "SUIVRE_COMMANDE"),
            ("What do you sell here?", "DECOUVRIR_CATALOGUE"),
        )
        with override("en"):
            for question, expected in cases:
                response = self.client.post(
                    reverse("assistant_ask"),
                    data={"message": question, "language": "en"},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 200, question)
                self.assertEqual(response.json()["intent"], expected, question)

    def test_endpoint_handles_holdout_and_multiple_questions(self):
        for question, expected in self.HOLDOUT_CASES[:7]:
            response = self.client.post(reverse("assistant_ask"), data={"message": question}, content_type="application/json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["intent"], expected, question)
        response = self.client.post(reverse("assistant_ask"), data={"message": "vous vendez quoi ici\nma commande avance ou pas"}, content_type="application/json")
        self.assertEqual(response.json()["intent"], "MULTIPLE_QUESTIONS")

    def test_real_holdout_endpoint_cases(self):
        cases = (
            ("je suis nouveau ici je fais quoi", "COMMENT_CA_MARCHE"),
            ("je trouve pas comment régler ce que j'ai acheté", "PAIEMENT"),
            ("j'arrive plus à rentrer dans mon compte", "PROBLEME_CONNEXION"),
            ("vous vendez quoi ici", "DECOUVRIR_CATALOGUE"),
            ("je cherche quelque chose mais je connais pas la catégorie", "RECHERCHER_PRODUIT"),
            ("ma commande avance ou pas", "SUIVRE_COMMANDE"),
            ("comment ce site peut m'aider", "COMMENT_CA_MARCHE"),
        )
        for question, expected in cases:
            response = self.client.post(reverse("assistant_ask"), data={"message": question}, content_type="application/json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["intent"], expected, question)

    def test_french_and_english_answers(self):
        self.assertIn("inscription", answer_question("comment créer un compte", "fr")["answer"])
        self.assertIn("registration", answer_question("how do I create an account", "en")["answer"])

    def test_password_short_continuation_keeps_previous_intent(self):
        first = answer_question("je souhait recuperer le mot de passe", "fr", authenticated=True)
        continued = answer_question("aider moi alors", "fr", authenticated=True, state=first["state"])
        self.assertEqual(continued["intent"], "MOT_DE_PASSE_OUBLIE")
        self.assertIn("adresse e-mail associée", continued["answer"])
        self.assertEqual(continued["actions"][0]["label"], "Réinitialiser mon mot de passe")

    def test_payment_short_continuation_keeps_previous_intent(self):
        first = answer_question("je veux payer", "fr", authenticated=True)
        continued = answer_question("comment faire alors", "fr", authenticated=True, state=first["state"])
        self.assertEqual(continued["intent"], "PAIEMENT")

    def test_short_continuation_without_context_does_not_invent_intent(self):
        result = answer_question("aide moi alors", "fr", authenticated=True)
        self.assertIn(result["intent"], {"AIDE_GENERALE", "NEEDS_CLARIFICATION"})

    def test_explicit_new_intent_replaces_previous_context(self):
        first = answer_question("je souhait recuperer le mot de passe", "fr", authenticated=True)
        replacement = answer_question("je veux payer", "fr", authenticated=True, state=first["state"])
        self.assertEqual(replacement["intent"], "PAIEMENT")
        self.assertEqual(replacement["state"]["intent"], "PAIEMENT")

    def test_order_number_continuation_keeps_existing_workflow(self):
        first = answer_question("je veux suivre ma commande", "fr", authenticated=True, state={})
        continued = answer_question("24", "fr", authenticated=True, state=first["state"])
        self.assertEqual(continued["intent"], "SUIVRE_COMMANDE")

    def test_endpoint_is_read_only_and_respects_auth_for_private_actions(self):
        response = self.client.post(reverse("assistant_ask"), data='{"message":"voir mon panier"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["actions"][0]["url"], "/accounts/login/")
        user = User.objects.create_user("guide-client", password="secret123")
        self.client.force_login(user)
        response = self.client.post(reverse("assistant_ask"), data='{"message":"voir mon panier"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "VOIR_PANIER")
        self.assertTrue(response.json()["actions"])
        self.assertEqual(User.objects.count(), 1)

    def test_endpoint_rejects_oversized_input(self):
        response = self.client.post(reverse("assistant_ask"), data={"message": "x" * 501}, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_follow_up_order_number_is_scoped_to_authenticated_owner(self):
        user = User.objects.create_user("owner", password="secret123")
        other = User.objects.create_user("other", password="secret123")
        owned = Order.objects.create(utilisateur=user)
        foreign = Order.objects.create(utilisateur=other)
        self.client.force_login(user)
        first = self.client.post(reverse("assistant_ask"), data='{"message":"suivre ma commande"}', content_type="application/json")
        self.assertEqual(first.json()["state"]["step"], "ASK_ORDER_NUMBER")
        found = self.client.post(reverse("assistant_ask"), data='{"message":"%s"}' % owned.id, content_type="application/json")
        self.assertIn("Commande #%s" % owned.id, found.json()["answer"])
        self.client.post(reverse("assistant_ask"), data='{"message":"suivre ma commande"}', content_type="application/json")
        denied = self.client.post(reverse("assistant_ask"), data='{"message":"%s"}' % foreign.id, content_type="application/json")
        self.assertIn("ne trouve", denied.json()["answer"])

    def test_product_search_returns_at_most_five_results(self):
        category = Category.objects.create(nom="Épicerie")
        for index in range(6):
            Product.objects.create(categorie=category, nom="Lait %s" % index, prix=100, actif=True)
        user = User.objects.create_user("searcher", password="secret123")
        self.client.force_login(user)
        response = self.client.post(reverse("assistant_ask"), data='{"message":"je cherche du lait"}', content_type="application/json")
        self.assertEqual(response.json()["intent"], "RECHERCHER_PRODUIT")
        self.assertLessEqual(len(response.json()["results"]), 5)

    def test_public_route_and_pages_resolve(self):
        self.assertEqual(reverse("assistant_ask"), "/assistant/ask/")
        for url in ("/", "/products/", "/categories/", "/cart/", "/accounts/login/"):
            response = self.client.get(url, HTTP_HOST="localhost")
            self.assertNotEqual(response.status_code, 500, url)

    @override_settings(LANGUAGE_CODE="en")
    def test_endpoint_uses_active_language(self):
        with override("en"):
            response = self.client.post(reverse("assistant_ask"), data='{"message":"how do I pay online"}', content_type="application/json")
        self.assertEqual(response.json()["intent"], "PAIEMENT_EN_LIGNE")
        self.assertIn("Online payment", response.json()["answer"])

    def test_csrf_rejects_bad_token_and_accepts_current_token_after_login_rotation(self):
        user = User.objects.create_user("csrf-guide", password="secret123")
        csrf_client = Client(enforce_csrf_checks=True)

        csrf_client.get(reverse("home"))
        token_before_login = csrf_client.cookies["csrftoken"].value
        bad = csrf_client.post(
            reverse("assistant_ask"),
            data='{"message":"comment payer"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN="invalid-token",
        )
        self.assertEqual(bad.status_code, 403)

        valid_before_login = csrf_client.post(
            reverse("assistant_ask"),
            data='{"message":"comment payer"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token_before_login,
        )
        self.assertEqual(valid_before_login.status_code, 200)

        login_response = csrf_client.post(
            reverse("login"),
            {
                "username": user.username,
                "password": "secret123",
                "csrfmiddlewaretoken": token_before_login,
            },
        )
        self.assertEqual(login_response.status_code, 302)
        csrf_client.get(reverse("home"))
        token_after_login = csrf_client.cookies["csrftoken"].value
        self.assertNotEqual(token_before_login, token_after_login)

        after_login = csrf_client.post(
            reverse("assistant_ask"),
            data='{"message":"comment paye"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token_after_login,
        )
        self.assertEqual(after_login.status_code, 200)
        self.assertEqual(after_login.json()["intent"], "PAIEMENT")
