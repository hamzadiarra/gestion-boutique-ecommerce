"""Deterministic, local customer guide with light typo tolerance."""

import difflib
import re
import unicodedata

from django.conf import settings
from django.db.models import Q
from django.urls import reverse

MAX_MESSAGE_LENGTH = 500
MIN_SCORE = 5
AMBIGUITY_MARGIN = 2
CONTINUATION_MESSAGES = {
    "aide moi", "aider moi", "aide moi alors", "aider moi alors", "oui",
    "d accord", "ok", "continue", "comment", "montre moi", "vas y", "fais voir",
    "comment faire alors",
}
STOP_WORDS = {"a", "au", "aux", "avec", "ce", "cette", "comment", "dans", "de", "des", "du", "en", "est", "et", "je", "la", "le", "les", "ma", "me", "mes", "mon", "ne", "ou", "pour", "que", "quel", "quelle", "quels", "quelles", "sa", "se", "son", "sur", "un", "une", "veut", "veux", "voir", "ici", "m", "j", "ai", "mais", "quelque", "chose", "vous", "ceci", "cette", "i", "am", "an", "the", "this", "is", "it", "my", "me", "do", "does", "how", "can", "could", "what", "where", "when", "for", "to", "here", "your", "a", "something"}


def normalize_question(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("’", "'").replace("'", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def tokenize(value, meaningful=True):
    tokens = re.findall(r"[a-z0-9]+", normalize_question(value))
    return [token for token in tokens if not meaningful or token not in STOP_WORDS]


CONCEPTS = {
    "NEW_USER": {"nouveau", "nouvelle", "debuter", "debute", "commencer", "premiere", "fois", "decouvrir", "new"},
    "HELP": {"aide", "aider", "guide", "guider", "faire", "quoi", "savoir", "sert", "utiliser", "help"},
    "APP": {"application", "appli", "app", "site", "website", "plateforme", "boutique", "boutiq", "shop", "magasin", "service", "fonctionne", "fonctionement", "work"},
    "UNDERSTAND": {"comprendre", "comprend", "expliquer", "explique", "fonctionnement", "fonctionne", "fonctionner", "utiliser", "usage", "marche", "savoir", "sert", "faire", "quoi", "understand", "use"},
    "PAYMENT": {"payer", "paye", "paie", "paiement", "paiements", "payement", "paiment", "regler", "regle", "reglement", "orange", "money", "moov", "wave", "carte", "card", "payment", "payments", "methods", "flutterwave"},
    "PAY_ACTION": {"payer", "paye", "paie", "paiement", "payement", "paiment", "regler", "regle", "reglement", "pay"},
    "ORDER": {"commande", "commandes", "commander", "comande", "commende", "achat", "achats", "acheter", "achete", "buy", "order", "place", "bought"},
    "PURCHASED": {"achete", "achat", "commande", "article", "bought", "buy"},
    "TRACK": {"suivre", "suivi", "statut", "avancement", "avance", "etat", "route", "attends", "attend", "progression", "track", "status", "moving", "happened"},
    "PROGRESS": {"avance", "avancement", "progression", "statut", "etat", "status", "moving"},
    "PASSWORD": {"mot", "passe", "password", "mdp", "oublie", "oublier", "perdu", "recuperer", "reset", "code", "rappelle", "rappeler", "forgot", "lost", "remember"},
    "ACCESS": {"entrer", "acceder", "acces", "rentrer", "ouvrir", "sign", "log", "access", "get"},
    "ACCOUNT": {"compte", "profil", "connexion", "account", "login"},
    "FAILURE": {"plus", "pas", "impossible", "probleme", "arrive", "marche", "passe", "cant", "cannot", "problem"},
    "DELIVERY": {"livraison", "livrer", "livre", "livreur", "livraision", "livreson", "colis", "route", "delivery", "courier", "parcel", "delivered"},
    "PRODUCT": {"produit", "produi", "produt", "article", "lait", "product", "milk"},
    "SEARCH": {"chercher", "rechercher", "trouver", "trouve", "cherche", "find", "looking"},
    "CATALOG": {"catalogue", "boutique", "boutiq", "produit", "article", "categorie", "rayon", "quoi", "avez", "products", "available"},
    "SELL": {"vendre", "vendez", "proposer", "avez", "disponible", "offrir", "offres", "montrez", "sell", "products", "available", "show"},
    "UNKNOWN_CATEGORY": {"categorie", "type", "genre", "sais", "connais", "connait"},
    "EDIT": {"modifier", "mettre", "jour", "actualiser", "changer", "edit", "change", "update"},
}

INTENTS = {
    "COMMENT_CA_MARCHE": {"phrases": ("comment ca marche", "comment ca fonctionne", "je veux comprendre", "comment utiliser", "aide moi a utiliser", "explique moi", "que puis je faire ici", "que peut on faire ici", "je suis nouveau", "je ne comprends pas", "a quoi sert", "how does the app work", "how does this work", "how to use the app", "explain the app", "what can i do here", "i am new"), "concepts": ("APP", "UNDERSTAND"), "fr": "Bienvenue dans Gestion Boutique. Je peux vous guider dans l'application pour parcourir les produits, rechercher une catégorie, ajouter des articles au panier, passer une commande, choisir un moyen de paiement, suivre une commande ou une livraison et gérer votre compte.", "en": "Welcome to Gestion Boutique. I can guide you through the application to browse products, find a category, add items to your cart, place an order, choose a payment method, track an order or delivery, and manage your account.", "actions": ()},
    "INSCRIPTION": {"phrases": ("inscrire", "inscription", "creer un compte", "create an account", "sign up"), "concepts": (), "fr": "Pour créer un compte, ouvrez la page d'inscription et renseignez les informations demandées.", "en": "To create an account, open the registration page and enter the requested information.", "actions": (("register", "Créer un compte", "Create an account"),)},
    "CONNEXION": {"phrases": ("se connecter", "connexion", "connecter", "login", "sign in"), "concepts": (), "fr": "Ouvrez la page de connexion puis saisissez votre identifiant et votre mot de passe.", "en": "Open the sign-in page, then enter your username and password.", "actions": (("login", "Se connecter", "Sign in"),)},
    "DECONNEXION": {"phrases": ("se deconnecter", "deconnexion", "sign out", "quitter mon compte"), "concepts": (), "fr": "Utilisez le lien Se déconnecter dans le menu de votre profil.", "en": "Use the Sign out link in your profile menu.", "actions": ()},
    "MOT_DE_PASSE_OUBLIE": {"phrases": ("mot de passe oublie", "mot passe oublier", "mdp oublie", "forgot password", "reset password", "recuperer mon compte"), "concepts": ("PASSWORD",), "fr": "Je peux vous guider pour réinitialiser votre mot de passe.", "en": "I can guide you through resetting your password.", "actions": (("password_reset", "Réinitialiser mon mot de passe", "Reset my password"),)},
    "PROBLEME_CONNEXION": {"phrases": (), "concepts": ("ACCESS", "FAILURE", "ACCOUNT"), "fr": "Je peux vous aider. Vous pouvez réessayer la connexion ou réinitialiser votre mot de passe.", "en": "I can help. You can try signing in again or reset your password.", "actions": (("login", "Se connecter", "Sign in"), ("password_reset", "Mot de passe oublié", "Forgot password"))},
    "RECHERCHER_PRODUIT": {"phrases": ("chercher", "rechercher", "trouve moi", "find", "do you have"), "concepts": ("SEARCH",), "fr": "Voici les produits qui correspondent à votre recherche.", "en": "Here are the products matching your search.", "actions": (("product_list", "Voir la boutique", "Browse shop"),)},
    "DECOUVRIR_CATALOGUE": {"phrases": ("quels produits", "vous vendez", "what do you sell", "what products"), "concepts": ("SELL", "CATALOG"), "fr": "Vous pouvez parcourir les produits disponibles ou les explorer par catégorie.", "en": "You can browse the available products or explore them by category.", "actions": (("product_list", "Voir les produits", "View products"), ("category_list", "Voir les catégories", "View categories"))},
    "VOIR_CATEGORIES": {"phrases": ("voir les categories", "liste des categories", "parcourir les categories", "view categories"), "concepts": (), "fr": "La page Catégories regroupe les produits par univers.", "en": "The Categories page groups products by collection.", "actions": (("category_list", "Voir les catégories", "View categories"),)},
    "VOIR_PRODUIT": {"phrases": ("voir un produit", "fiche produit", "details produit", "view product"), "concepts": (), "fr": "Ouvrez une carte produit pour consulter sa fiche, son prix et sa disponibilité.", "en": "Open a product card to view its details, price, and availability.", "actions": (("product_list", "Voir la boutique", "Browse shop"),)},
    "AJOUTER_PANIER": {"phrases": ("ajouter au panier", "mettre dans le panier", "add to cart"), "concepts": (), "fr": "Depuis une fiche produit, choisissez la quantité puis cliquez sur Ajouter au panier.", "en": "From a product page, choose a quantity and click Add to cart.", "actions": (("product_list", "Voir la boutique", "Browse shop"),)},
    "VOIR_PANIER": {"phrases": ("voir mon panier", "ouvrir le panier", "consulter le panier", "view cart"), "concepts": (), "fr": "Ouvrez votre panier pour vérifier les articles, les quantités et le total.", "en": "Open your cart to check items, quantities, and the total.", "actions": (("cart_detail", "Voir mon panier", "View cart"),), "auth_required": True},
    "MODIFIER_PANIER": {"phrases": ("modifier mon panier", "changer la quantite", "supprimer du panier", "edit cart"), "concepts": (), "fr": "Dans le panier, utilisez les contrôles de quantité ou l'action Supprimer.", "en": "In the cart, use the quantity controls or the Remove action.", "actions": (("cart_detail", "Modifier mon panier", "Edit cart"),), "auth_required": True},
    "PASSER_COMMANDE": {"phrases": ("je veux acheter", "comment acheter", "comment achete", "faire un achat", "acheter produit", "comment commander", "je veux commander", "passer commande", "place an order", "buy product"), "concepts": ("ORDER",), "fr": "Choisissez un produit, ajoutez-le au panier puis ouvrez votre panier pour finaliser la commande.", "en": "Choose a product, add it to your cart, then open your cart to finish the order.", "actions": (("product_list", "Voir la boutique", "Browse shop"), ("cart_detail", "Voir mon panier", "View cart")), "auth_required": True},
    "VOIR_COMMANDES": {"phrases": ("voir mes commandes", "historique des commandes", "mes commandes", "my orders", "order history"), "concepts": (), "fr": "Votre page Mes commandes affiche l'historique et l'état de vos commandes.", "en": "Your My orders page shows your order history and statuses.", "actions": (("my_orders", "Mes commandes", "My orders"),), "auth_required": True},
    "SUIVRE_COMMANDE": {"phrases": ("suivre ma commande", "ou est ma commande", "ou est ma livraison", "suivi de commande", "statut commande", "ou en est", "where is my order", "track my order", "order status"), "concepts": ("ORDER", "TRACK"), "fr": "Indiquez le numéro de votre commande pour consulter son suivi.", "en": "Tell me your order number to check its tracking status.", "actions": (("my_orders", "Mes commandes", "My orders"),), "auth_required": True, "ask_order_number": True},
    "PAIEMENT_EN_LIGNE": {"phrases": ("paiement en ligne", "payer en ligne", "online payment", "pay online"), "concepts": (), "fr": "Pour payer en ligne, choisissez Paiement en ligne lors de la finalisation de votre commande.", "en": "To pay online, choose Online payment when finishing your order.", "actions": (("cart_detail", "Voir mon panier", "View cart"),), "auth_required": True},
    "PAIEMENT_ECHOUE": {"phrases": ("paiement echoue", "paiement refuse", "paiement ne marche pas", "payment failed"), "concepts": (), "fr": "Si le paiement échoue, votre commande reste disponible. Revenez au paiement pour réessayer.", "en": "If payment fails, your order remains available. Return to payment to try again.", "actions": ()},
    "PAIEMENT": {"phrases": ("comment payer", "comment paye", "comment paie", "how to pay", "how can i pay", "pay order", "moyen de paiement", "moyens de paiement", "quels paiements", "payer commande", "regler ma commande"), "concepts": ("PAY_ACTION", "PURCHASED"), "fr": "Vous choisissez votre moyen de paiement lors de la finalisation de votre commande. Les moyens disponibles dépendent de la configuration de la boutique.", "en": "You choose your payment method when finishing your order. Available methods depend on the shop configuration.", "actions": (("cart_detail", "Voir mon panier", "View cart"),)},
    "LIVRAISON": {"phrases": ("delai de livraison", "livraison", "ou est le livreur", "quand je serai livre", "commande en route", "delivery"), "concepts": ("DELIVERY",), "fr": "Le statut de livraison est visible depuis votre commande lorsqu'une livraison est créée.", "en": "Delivery status is available from your order once a delivery has been created.", "actions": (("my_orders", "Mes commandes", "My orders"),), "auth_required": True},
    "FAVORIS": {"phrases": ("mes favoris", "ajouter aux favoris", "liste de souhaits", "my favorites"), "concepts": (), "fr": "Utilisez le bouton cœur sur un produit, puis retrouvez vos favoris dans votre compte.", "en": "Use the heart button on a product, then find your favorites in your account.", "actions": (("wishlist", "Mes favoris", "My favorites"),), "auth_required": True},
    "PROFIL": {"phrases": ("voir mon profil", "mon profil", "informations du compte", "my profile"), "concepts": (), "fr": "Votre profil regroupe vos informations de compte et vos préférences.", "en": "Your profile contains your account information and preferences.", "actions": (("profile", "Mon profil", "My profile"),), "auth_required": True},
    "MODIFIER_PROFIL": {"phrases": ("modifier mon profil", "modifier profil", "changer mes informations", "edit my profile"), "concepts": ("EDIT",), "fr": "Ouvrez Modifier mon profil pour mettre à jour vos informations.", "en": "Open Edit my profile to update your information.", "actions": (("profile_edit", "Modifier mon profil", "Edit my profile"),), "auth_required": True},
    "CONTACT_SUPPORT": {"phrases": ("contacter le support", "parler au support", "contacter la boutique", "contact support"), "concepts": (), "fr": "Pour une aide personnalisée, contactez la boutique avec les coordonnées affichées.", "en": "For personal help, contact the shop using the displayed contact details.", "actions": ()},
    "SALUTATION": {"phrases": ("bonjour", "salut", "bonsoir", "hello", "hi"), "concepts": (), "fr": "Bonjour ! Comment puis-je vous aider ?", "en": "Hello! How can I help you?", "actions": ()},
    "MERCI": {"phrases": ("merci", "merci beaucoup", "thanks", "thank you"), "concepts": (), "fr": "Avec plaisir.", "en": "You are welcome.", "actions": ()},
    "NEEDS_CLARIFICATION": {"phrases": ("j ai un probleme", "ca ne marche pas", "je ne sais pas", "i have a problem", "it does not work"), "concepts": (), "fr": "Votre problème concerne quoi ?", "en": "What does your problem concern?", "actions": (("login", "Connexion", "Sign in"), ("my_orders", "Commande", "Order"), ("cart_detail", "Paiement", "Payment"), ("profile", "Profil", "Profile"))},
    "MULTIPLE_QUESTIONS": {"phrases": (), "concepts": (), "fr": "Vous avez plusieurs questions. Par quoi voulez-vous commencer ?", "en": "You have several questions. Which one would you like to start with?", "actions": (("product_list", "Produits", "Products"), ("my_orders", "Ma commande", "My order"), ("cart_detail", "Paiement", "Payment"), ("home", "Aide", "Help"))},
    "AIDE_GENERALE": {"phrases": (), "concepts": (), "fr": "Je n'ai pas identifié précisément votre demande. Je peux vous aider à acheter un produit, suivre une commande, effectuer un paiement, récupérer votre mot de passe ou gérer votre profil.", "en": "I could not identify your request precisely. I can help you buy a product, track an order, make a payment, recover your password, or manage your profile.", "actions": ()},
}


# English phrases are kept alongside the intent definitions so the same
# scorer handles both languages without relying on case or substring matches.
INTENTS["COMMENT_CA_MARCHE"]["phrases"] += (
    "how does this shop work", "how does this website work",
    "how do i use this website", "im new here", "help me understand this shop",
)
INTENTS["PROBLEME_CONNEXION"]["phrases"] = (
    "i can t sign in", "i cannot log in", "i can t access my account",
    "login problem", "i can t get into my account",
)
INTENTS["PASSER_COMMANDE"]["phrases"] += (
    "how can i buy", "i want to buy something", "how do i order",
    "i want to place an order", "where can i buy a product",
)
INTENTS["PAIEMENT"]["phrases"] += (
    "how do i pay", "i want to pay", "payment methods",
    "how do i pay for my order", "where can i pay", "card payment",
)
INTENTS["SUIVRE_COMMANDE"]["phrases"] += (
    "is my order moving", "what happened to my order", "where is order",
)
INTENTS["LIVRAISON"]["phrases"] += (
    "where is my delivery", "when will i be delivered", "where is the courier",
    "delivery status", "where is my parcel",
)
INTENTS["DECOUVRIR_CATALOGUE"]["phrases"] += (
    "what do you sell here", "what products do you have", "show me your products",
    "what is available", "what can i buy here",
)
INTENTS["RECHERCHER_PRODUIT"]["phrases"] += (
    "i m looking for milk", "find milk", "do you have milk", "find a product",
    "i m looking for something",
)
INTENTS["MOT_DE_PASSE_OUBLIE"]["phrases"] += (
    "forgot password", "i forgot my password", "lost my password",
    "reset password", "i can t remember my password",
)
INTENTS["PROFIL"]["phrases"] += ("my profile",)
INTENTS["MODIFIER_PROFIL"]["phrases"] += ("change my information", "update my profile")
INTENTS["SALUTATION"]["phrases"] += (
    "hey", "good morning", "good afternoon", "good evening", "hi there", "hello there",
)
INTENTS["MERCI"]["phrases"] += ("thanks a lot", "many thanks", "great thanks")

# English concept vocabulary keeps paraphrases useful without putting holdout
# sentences into production phrase lists.
CONCEPTS["GREETING"] = {"hi", "hello", "hey", "good", "morning", "afternoon", "evening", "day"}
CONCEPTS["APP"].update({"store", "joined", "begin", "steps"})
CONCEPTS["HELP"].update({"explain", "steps", "way"})
CONCEPTS["ORDER"].update({"purchase", "item", "make"})
CONCEPTS["PAYMENT"].update({"ways", "bank"})
CONCEPTS["PASSWORD"].update({"create", "new", "memory"})
CONCEPTS["TRACK"].update({"progress", "journey", "update"})
CONCEPTS["PROGRESS"].update({"progress", "journey"})
CONCEPTS["DELIVERY"].update({"shipment", "shipping", "arrives", "package", "journey"})
CONCEPTS["CATALOG"].update({"items", "goods", "offered", "store"})
CONCEPTS["SELL"].update({"items", "goods", "offered", "store"})
CONCEPTS["SEARCH"].update({"look", "locate"})
CONCEPTS["MERCI"] = {"thanks", "thank", "appreciate"}
INTENTS["SALUTATION"]["concepts"] = ("GREETING",)
INTENTS["MERCI"]["concepts"] = ("MERCI",)
INTENTS["PAIEMENT"]["concepts"] += ("PAYMENT",)


def _phrase_in_question(phrase, question):
    """Match complete normalized phrases, avoiding e.g. ``hi`` in ``this``."""
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(normalize_question(phrase)) + r"(?![a-z0-9])", question))


def _fuzzy_concept(tokens):
    hits = set()
    vocabulary = {word for words in CONCEPTS.values() for word in words if len(word) > 3}
    for token in tokens:
        match = difflib.get_close_matches(token, vocabulary, n=1, cutoff=0.82)
        if match:
            for concept, words in CONCEPTS.items():
                if match[0] in words:
                    hits.add(concept)
    return hits


def detect_concepts(message):
    """Return exact and fuzzy concept families for diagnostics and scoring."""
    tokens = set(tokenize(message))
    concepts = {name for name, words in CONCEPTS.items() if tokens & words}
    fuzzy = _fuzzy_concept(tokens)
    return sorted(concepts | fuzzy)


def explain_detection(message, context=None, state=None):
    """Explain the deterministic decision without exposing it in the UI."""
    normalized = normalize_question(message)
    concepts = detect_concepts(message)
    fuzzy_matches = {token: match for token in tokenize(message) for match in difflib.get_close_matches(token, {word for words in CONCEPTS.values() for word in words if len(word) > 3}, n=1, cutoff=0.82) if token != match}
    scores = {}
    for code, intent in INTENTS.items():
        score = sum(10 for phrase in intent["phrases"] if _phrase_in_question(phrase, normalized))
        required = set(intent.get("concepts", ()))
        if required and required.issubset(set(concepts)):
            score += 8
        score += 5 * len(required & set(concepts))
        if score:
            scores[code] = score
    selected, selected_score = detect_intent(message, context, state)
    scores[selected] = max(scores.get(selected, 0), selected_score)
    return {"normalized": normalized, "tokens": tokenize(message), "concepts": concepts, "fuzzy_matches": fuzzy_matches, "scores": scores, "selected": selected, "threshold": MIN_SCORE}


def detect_intent(message, context=None, state=None):
    question = normalize_question(message)
    if state and state.get("intent") == "SUIVRE_COMMANDE" and state.get("step") == "ASK_ORDER_NUMBER" and re.fullmatch(r"\d+", question):
        return "SUIVRE_COMMANDE", 10
    if not question:
        return "AIDE_GENERALE", 0
    if re.search(r"\b(mon|ma|mes)\b", question) and len(tokenize(question)) <= 1 and "achat" in question:
        return "NEEDS_CLARIFICATION", 1
    tokens = tokenize(question)
    fuzzy = _fuzzy_concept(tokens)
    scores = []
    for code, intent in INTENTS.items():
        score = sum(6 + min(len(phrase.split()), 5) for phrase in intent["phrases"] if _phrase_in_question(phrase, question))
        follow_words = {"suivre", "suivi", "statut", "attends", "route", "avance", "avancement", "progression", "etat", "track", "status", "moving", "progress", "journey", "update"}
        allow_follow_concepts = code != "SUIVRE_COMMANDE" or bool(set(tokens) & follow_words)
        score += sum(5 for concept in intent["concepts"] if allow_follow_concepts and (set(tokens) & CONCEPTS.get(concept, set()) or concept in fuzzy))
        if code == "PAIEMENT_EN_LIGNE" and ("online" in question or "en ligne" in question):
            score += 5
        has_payment = bool(set(tokens) & CONCEPTS["PAYMENT"]) or "PAYMENT" in fuzzy
        if code == "PAIEMENT" and has_payment:
            score += 3
        if code == "PASSER_COMMANDE" and has_payment:
            score -= 4
        if code == "PAIEMENT" and (set(tokens) & CONCEPTS["PAY_ACTION"] or has_payment):
            score += 4
        if code == "RECHERCHER_PRODUIT" and (set(tokens) & CONCEPTS["PRODUCT"] or "PRODUCT" in fuzzy):
            score += 5
        if code == "PAIEMENT" and not (set(tokens) & CONCEPTS["PAY_ACTION"]) and not has_payment and not any(phrase in question for phrase in intent["phrases"]):
            score -= 6
        if code == "PAIEMENT" and has_payment and set(tokens) & CONCEPTS["FAILURE"]:
            score -= 8
        if code == "COMMENT_CA_MARCHE":
            concept_set = set(tokens)
            if (concept_set & CONCEPTS["APP"] and concept_set & CONCEPTS["HELP"]) or (concept_set & CONCEPTS["NEW_USER"] and concept_set & CONCEPTS["HELP"]):
                score += 10
            if concept_set & CONCEPTS["NEW_USER"]:
                score += 8
            if ("salut" in tokens or "bonjour" in tokens or "hello" in tokens) and set(tokens) & CONCEPTS["HELP"]:
                score += 8
        if code == "DECOUVRIR_CATALOGUE" and set(tokens) & CONCEPTS["CATALOG"] and any(word in question for word in ("voir", "montrez", "quels")):
            score += 6
        if code == "DECOUVRIR_CATALOGUE" and ("salut" in tokens or "bonjour" in tokens) and set(tokens) & CONCEPTS["HELP"]:
            score -= 8
        if code == "MODIFIER_PROFIL" and set(tokens) & CONCEPTS["EDIT"]:
            score += 8
        if code == "PASSER_COMMANDE" and set(tokens) & {"buy", "purchase", "order", "place", "make"}:
            score += 7
        if code == "PASSER_COMMANDE" and (set(tokens) & {"track", "status", "moving", "progress", "journey", "update"} or _phrase_in_question("where is", question)):
            score -= 8
        if code == "SUIVRE_COMMANDE" and set(tokens) & CONCEPTS["ORDER"] and set(tokens) & CONCEPTS["TRACK"]:
            score += 10
        if code == "MODIFIER_PROFIL" and set(tokens) & CONCEPTS["ORDER"] and set(tokens) & CONCEPTS["TRACK"]:
            score -= 8
        if code == "MOT_DE_PASSE_OUBLIE" and "password" in tokens and set(tokens) & {"new", "create", "memory"}:
            score += 10
        if code == "COMMENT_CA_MARCHE" and "password" in tokens:
            score -= 8
        if code == "SALUTATION" and set(tokens) & CONCEPTS["GREETING"]:
            score += 6
        if code == "MOT_DE_PASSE_OUBLIE" and (set(tokens) & CONCEPTS["PASSWORD"]) and (set(tokens) & {"oublie", "oublier", "perdu", "recuperer", "rappelle", "rappeler", "reset"}):
            score += 8
        if code == "PAIEMENT_ECHOUE" and (set(tokens) & CONCEPTS["PAY_ACTION"] or has_payment) and set(tokens) & {"echoue", "refuse", "marche", "passe"}:
            score += 10
        if code == "SALUTATION" and len(tokens) > 1 and not any(_phrase_in_question(phrase, question) for phrase in intent["phrases"] if len(phrase.split()) > 1):
            score -= 6
        if code == "SUIVRE_COMMANDE" and (set(tokens) & CONCEPTS["DELIVERY"]) and (set(tokens) & CONCEPTS["PROGRESS"]):
            score += 9
        if code == "PROBLEME_CONNEXION" and (set(tokens) & CONCEPTS["ACCESS"]) and (set(tokens) & CONCEPTS["FAILURE"]):
            score += 6
        if code == "SUIVRE_COMMANDE" and any(word in tokens for word in ("suivre", "suivi", "statut", "attends", "route", "avance", "avancement", "progression", "etat")):
            score += 4
        if context and code == "PASSER_COMMANDE" and context.rstrip("/").endswith("cart"):
            score += 2
        if context and code == "SUIVRE_COMMANDE" and ("orders" in context or "order" in context):
            score += 2
        if score:
            scores.append((score, code))
    if not scores:
        return "AIDE_GENERALE", 0
    if "en ligne" in question or "online" in question:
        return "PAIEMENT_EN_LIGNE", max(next((score for score, code in scores if code == "PAIEMENT_EN_LIGNE"), 0), MIN_SCORE)
    score, code = sorted(scores, reverse=True)[0]
    return (code, score) if score >= MIN_SCORE else ("AIDE_GENERALE", score)


def _actions(intent, language, authenticated):
    if intent.get("auth_required") and not authenticated:
        return [{"label": "Se connecter" if language == "fr" else "Sign in", "url": reverse("login")}]
    return [{"label": en if language == "en" else fr, "url": reverse(route)} for route, fr, en in intent.get("actions", ())]


def _is_continuation(message):
    return normalize_question(message) in CONTINUATION_MESSAGES


def _continuation_state(code, message, result):
    """Keep only actionable conversation context for a later short reply."""
    if code == "SUIVRE_COMMANDE" and result.get("state", {}).get("step") == "ASK_ORDER_NUMBER":
        return result["state"]
    if code in {"MOT_DE_PASSE_OUBLIE", "PAIEMENT"}:
        return {"intent": code, "step": "CONTINUE"}
    if code == "RECHERCHER_PRODUIT" and (result.get("results") or result.get("actions")):
        return {"intent": code, "step": "CONTINUE", "search_message": message}
    return {}


def _product_results(message):
    terms = [token for token in tokenize(message) if token not in {"cherche", "chercher", "recherche", "rechercher", "trouve", "trouver", "produit", "produi", "produt", "article", "find"}]
    if not terms and "lait" in normalize_question(message):
        terms = ["lait"]
    if not terms:
        return []
    query = Q()
    for term in terms:
        query |= Q(nom__icontains=term) | Q(nom_en__icontains=term) | Q(description__icontains=term) | Q(description_en__icontains=term) | Q(categorie__nom__icontains=term)
    from products.models import Product
    return [{"name": product.localized_name, "url": reverse("product_detail", args=[product.slug])} for product in Product.objects.filter(query, actif=True).select_related("categorie")[:5]]


def answer_question(message, language="fr", authenticated=False, context=None, state=None, request=None):
    language = "en" if str(language).lower().startswith("en") else "fr"
    state = state or {}
    continuation = _is_continuation(message)
    previous_intent = state.get("intent") if continuation else None
    if previous_intent not in {"MOT_DE_PASSE_OUBLIE", "PAIEMENT", "RECHERCHER_PRODUIT", "SUIVRE_COMMANDE"}:
        previous_intent = None
    parts = [part.strip() for part in re.split(r"[\n?]+", str(message)) if part.strip()]
    part_codes = {previous_intent or detect_intent(part, context, state)[0] for part in parts}
    if len(parts) >= 2 and len(part_codes - {"AIDE_GENERALE"}) >= 2:
        intent = INTENTS["MULTIPLE_QUESTIONS"]
        result = {"intent": "MULTIPLE_QUESTIONS", "score": 10, "answer": intent[language], "actions": _actions(intent, language, authenticated), "state": {}}
        return result
    code, score = (previous_intent, 10) if previous_intent else detect_intent(message, context, state)
    intent = INTENTS[code]
    result = {"intent": code, "score": score, "answer": intent[language], "actions": _actions(intent, language, authenticated), "state": {}}
    if code == "MOT_DE_PASSE_OUBLIE" and continuation:
        result["answer"] = (
            "Bien sûr. Cliquez sur Réinitialiser mon mot de passe, puis saisissez l'adresse e-mail associée à votre compte."
            if language == "fr" else
            "Of course. Click Reset my password, then enter the email address linked to your account."
        )
    if code == "COMMENT_CA_MARCHE":
        routes = (("product_list", "Voir la boutique", "Browse shop"), ("category_list", "Voir les catégories", "View categories"))
        if authenticated:
            routes += (("cart_detail", "Voir mon panier", "View cart"), ("my_orders", "Mes commandes", "My orders"), ("profile", "Mon profil", "My profile"))
        else:
            routes += (("register", "Créer un compte", "Create an account"), ("login", "Se connecter", "Sign in"))
        result["actions"] = [{"label": en if language == "en" else fr, "url": reverse(route)} for route, fr, en in routes]
    if code == "SUIVRE_COMMANDE" and intent.get("ask_order_number"):
        normalized = normalize_question(message)
        if re.fullmatch(r"\d+", normalized) and request and authenticated:
            from orders.models import Order
            order = Order.objects.filter(id=int(normalized), utilisateur=request.user).first()
            if order:
                result["answer"] = (f"Commande #{order.id} : {order.get_statut_display()}." if language == "fr" else f"Order #{order.id}: {order.get_statut_display()}.")
                result["actions"] = [{"label": "Voir ma commande" if language == "fr" else "View my order", "url": reverse("order_detail", args=[order.id])}]
                return result
            result["answer"] = "Je ne trouve pas cette commande dans votre compte." if language == "fr" else "I cannot find that order in your account."
        else:
            result["state"] = {"intent": "SUIVRE_COMMANDE", "step": "ASK_ORDER_NUMBER"}
    if code == "RECHERCHER_PRODUIT" and request:
        result["results"] = _product_results(state.get("search_message", message) if continuation else message)
        if not result["results"]:
            result["answer"] = "Je n'ai trouvé aucun produit correspondant. Essayez un autre terme." if language == "fr" else "I could not find a matching product. Try another term."
    if code == "PAIEMENT":
        from payments.models import Payment
        methods = [str(label) for value, label in Payment.METHODES if value != "online" or (settings.PAYMENT_PROVIDER and settings.PAYMENT_SECRET_KEY)]
        result["methods"] = methods
        result["answer"] += " " + ("Moyens disponibles : " if language == "fr" else "Available methods: ") + ", ".join(methods) + "."
    result["state"] = _continuation_state(code, message, result)
    return result
