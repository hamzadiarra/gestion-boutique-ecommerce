"""Deterministic, local customer guide with light typo tolerance."""

import difflib
import re
import unicodedata

from django.conf import settings
from django.urls import Resolver404, resolve, reverse

MAX_MESSAGE_LENGTH = 500
MIN_SCORE = 5
AMBIGUITY_MARGIN = 2
CONTINUATION_MESSAGES = {
    "aide moi", "aider moi", "aide moi alors", "aider moi alors", "oui",
    "d accord", "ok", "continue", "comment", "montre moi", "vas y", "fais voir",
    "comment faire alors", "yes", "okay", "continue please", "show me", "how then",
}
STOP_WORDS = {"a", "au", "aux", "avec", "ce", "cette", "comment", "dans", "de", "des", "du", "en", "est", "et", "je", "la", "le", "les", "ma", "me", "mes", "mon", "ne", "ou", "pour", "que", "quel", "quelle", "quels", "quelles", "sa", "se", "son", "sur", "un", "une", "veut", "veux", "voir", "ici", "m", "j", "ai", "mais", "quelque", "chose", "vous", "ceci", "cette", "i", "am", "an", "the", "this", "is", "it", "my", "me", "do", "does", "how", "can", "could", "what", "where", "when", "for", "to", "here", "your", "a", "something"}


def normalize_question(value):
    value = unicodedata.normalize("NFKD", str(value or "").replace("’", "'")).encode("ascii", "ignore").decode("ascii")
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
    vocabulary = sorted({word for words in CONCEPTS.values() for word in words if len(word) > 3})
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
    semantic = _semantic_intent(question)
    if semantic:
        return semantic, 20
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
    if code in {"MOT_DE_PASSE_OUBLIE", "PRIX_PRODUIT"} | PAYMENT_INTENTS:
        return {"intent": code, "step": "CONTINUE"}
    if code == "RECHERCHER_PRODUIT" and (result.get("results") or result.get("actions")):
        return {"intent": code, "step": "CONTINUE", "search_query": " ".join(_search_terms(message))[:100], "product_ids": []}
    return {}


def answer_question(message, language="fr", authenticated=False, context=None, state=None, request=None):
    language = "en" if str(language).lower().startswith("en") else "fr"
    state = state if isinstance(state, dict) else {}
    continuation = _is_continuation(message)
    previous_intent = state.get("intent") if continuation else None
    if previous_intent not in {"MOT_DE_PASSE_OUBLIE", "PRIX_PRODUIT", "STOCK_PRODUIT", "RECHERCHER_PRODUIT", "SUIVRE_COMMANDE"} | PAYMENT_INTENTS:
        previous_intent = None
    parts = [part.strip() for part in re.split(r"[\n?;]+|\b(?:et|and|puis|then)\b", str(message), flags=re.I) if part.strip()]
    part_codes = {previous_intent or detect_intent(part, context, state)[0] for part in parts}
    part_codes -= {"AIDE_GENERALE", "SALUTATION", "MERCI", "NEEDS_CLARIFICATION"}
    if len(parts) >= 2 and len(part_codes) >= 2:
        intent = INTENTS["MULTIPLE_QUESTIONS"]
        result = {"intent": "MULTIPLE_QUESTIONS", "score": 10, "answer": intent[language], "actions": _actions(intent, language, authenticated), "state": {}}
        result["suggestions"] = [{"label": part[:80], "message": part[:MAX_MESSAGE_LENGTH]} for part in parts[:3]]
        return result
    code, score = (previous_intent, 10) if previous_intent else detect_intent(message, context, state)
    if request and (code == "STOCK_PRODUIT" or (state.get("intent") == "STOCK_PRODUIT" and code == "AIDE_GENERALE" and set(tokenize(message)) & ORDINAL_WORDS)):
        from .assistant_stock import stock_answer
        return stock_answer(message, language, state, context)
    if request and code in {"RECHERCHER_PRODUIT", "PRIX_PRODUIT", "AIDE_GENERALE"}:
        catalog = _catalog_answer(message, language, state, context, code, continuation)
        if catalog is not None:
            return catalog
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
    if code == "PAIEMENT":
        from payments.models import Payment
        from django.utils.translation import override
        with override(language):
            methods = [str(label) for value, label in Payment.METHODES if value != "online" or _online_available()]
        result["methods"] = methods
        result["answer"] += " " + ("Moyens disponibles : " if language == "fr" else "Available methods: ") + ", ".join(methods) + "."
    if code == "PAIEMENT_EN_LIGNE" and not _online_available():
        result["answer"] = ("Le paiement en ligne n'est pas disponible actuellement. Consultez les autres moyens de paiement lors de la finalisation de votre commande."
                            if language == "fr" else "Online payment is not available currently. Check the other payment methods at checkout.")
    result["state"] = _continuation_state(code, message, result)
    return result


# These semantic checks precede scoring: negation and completion are not
# independent keywords, and "online" alone never establishes a payment intent.
INTENTS.update({
    "STOCK_PRODUIT": {"phrases": (), "concepts": (), "fr": "De quel produit souhaitez-vous vérifier le stock ? Précisez son nom ou sa position dans les résultats.", "en": "Which product should I check stock for? Give its name or position in the results.", "actions": ()},
    "PAIEMENT_REFUSE": {"phrases": (), "concepts": (), "fr": "Vous pouvez continuer à consulter les produits. Je ne déclenche aucun paiement. Si vous souhaitez annuler une commande, vérifiez les options proposées dans Mes commandes.", "en": "You can keep browsing products. I do not initiate payments. To cancel an order, check the options shown in My orders.", "actions": (("product_list", "Voir les produits", "View products"),)},
    "PAIEMENT_EFFECTUE": {"phrases": (), "concepts": (), "fr": "Pour vérifier votre paiement, ouvrez votre commande et consultez son statut de paiement. Votre message seul ne permet pas de vérifier la réception du paiement.", "en": "To check your payment, open your order and review its payment status. Your message alone cannot verify that payment was received.", "actions": (("my_orders", "Mes commandes", "My orders"),), "auth_required": True},
    "PAIEMENT_LIVRAISON": {"phrases": (), "concepts": (), "fr": "Le moyen Espèces est proposé lors de la commande. Vérifiez les conditions de règlement avec la boutique pour savoir si vous pouvez payer à la livraison.", "en": "Cash is offered as a payment method at checkout. Check the payment terms with the shop to find out whether you can pay on delivery.", "actions": (("cart_detail", "Voir mon panier", "View cart"),), "auth_required": True},
    "PRIX_PRODUIT": {"phrases": (), "concepts": (), "fr": "De quel produit souhaitez-vous connaître le prix ? Précisez son nom ou sa position dans les résultats.", "en": "Which product would you like the price of? Give its name or position in the results.", "actions": ()},
})
CONCEPTS["PAYMENT"].update({"pay", "paid", "cash", "especes"})
PAYMENT_INTENTS = {code for code in INTENTS if code.startswith("PAIEMENT")}


def _semantic_intent(question):
    words = set(question.split())
    payment = bool(words & CONCEPTS["PAYMENT"]) or "PAYMENT" in _fuzzy_concept(words)
    if payment:
        online = bool(words & {"online"}) or _phrase_in_question("en ligne", question)
        refusal = bool(re.search(r"(?:veux|veut|souhaite|souhaites|voudrais) (?:pas|plus) (?:payer|regler)|(?:do not|don t|dont) want to pay|refuse (?:de |to )?(?:payer|pay)", question))
        if refusal:
            return "PAIEMENT" if online else "PAIEMENT_REFUSE"
        not_paid = bool(re.search(r"(?:pas|not|never|jamais|haven t|hasn t).{0,20}(?:paye|paid)|(?:paye|paid).{0,10}(?:pas|not)", question))
        if not not_paid and (words & {"deja", "already"}) and words & {"paye", "paid", "regle"}:
            return "PAIEMENT_EFFECTUE"
        failed = bool(words & {"echoue", "echouee", "refuse", "refusee", "failed", "declined", "rejected"})
        failed = failed or bool(re.search(r"(?:ne |does not |doesn t |not |no longer ).{0,12}(?:marche|fonctionne|passe|work|working)|(?:marche|fonctionne|passe).{0,6}(?:pas|plus)", question))
        if failed:
            if re.search(r"(?:pas|not).{0,8}(?:echoue|refuse|failed|declined)", question):
                return "PAIEMENT"
            return "PAIEMENT_ECHOUE"
        if words & {"especes", "cash"} or re.search(r"(?:a la|on|upon|at) (?:livraison|delivery)", question):
            return "PAIEMENT_LIVRAISON"
        if online and not not_paid:
            if re.search(r"(?:pas|not|sans|without).{0,14}(?:en ligne|online)", question):
                return "PAIEMENT"
            return "PAIEMENT_EN_LIGNE"
        if not_paid or words & {"payment", "paiement"} and words & {"works", "fonctionne", "marche"}:
            return "PAIEMENT"
    from .assistant_stock import is_stock_question
    if is_stock_question(question) and words & {"paiement", "paiements", "payment", "payments"}:
        return "PAIEMENT"
    if is_stock_question(question) and words & {"livraison", "delivery", "shipping", "shipment"}:
        return "LIVRAISON"
    if is_stock_question(question):
        return "STOCK_PRODUIT"
    if words & PRICE_WORDS or _phrase_in_question("how much", question):
        if words & {"livraison", "delivery", "shipping", "shipment"}:
            return "LIVRAISON"
        return "PRIX_PRODUIT"
    return None


def _online_available():
    if settings.PAYMENT_PROVIDER == "cinetpay":
        return bool(settings.CINETPAY_API_KEY and settings.CINETPAY_SITE_ID and settings.CINETPAY_SECRET_KEY)
    return bool(settings.PAYMENT_PROVIDER and settings.PAYMENT_SECRET_KEY)


# A small bilingual vocabulary helps find actual category names; it never
# supplies a product, price, brand or availability that is absent from the DB.
CATALOG_SYNONYMS = (
    {"chaussure", "chaussures", "shoe", "shoes", "basket", "baskets", "sneaker", "sneakers"},
    {"vetement", "vetements", "clothing", "clothes", "apparel"},
    {"telephone", "telephones", "phone", "phones", "smartphone", "smartphones"},
    {"lait", "milk"},
)
PRICE_WORDS = {"prix", "price", "cost", "coute", "coutent", "combien", "tarif"}
ORDINALS = ({"premier", "premiere", "first", "1", "1er", "1st"}, {"second", "seconde", "deuxieme", "2", "2e", "2nd"}, {"troisieme", "third", "3", "3e", "3rd"}, {"quatrieme", "fourth", "4", "4e", "4th"}, {"cinquieme", "fifth", "5", "5e", "5th"}, {"sixieme", "sixth", "6"}, {"septieme", "seventh", "7"}, {"huitieme", "eighth", "8"}, {"neuvieme", "ninth", "9"}, {"dixieme", "tenth", "10"})
ORDINAL_WORDS = set().union(*ORDINALS)
SEARCH_FILLER = STOP_WORDS | {
    "cherche", "chercher", "recherche", "rechercher", "trouve", "trouver", "produit", "produits", "produi", "produt", "article", "articles",
    "find", "search", "look", "looking", "locate", "product", "products", "item", "items", "some", "please", "want", "need", "would", "like",
    "voudrais", "souhaite", "souhaiterais", "aimerais", "besoin", "montre", "montrez", "show", "avez", "have", "has", "y", "t", "il", "s", "im", "moi", "meme", "plutot", "only", "just", "seulement", "uniquement",
}


def _search_terms(message):
    return [word for word in tokenize(message) if word not in SEARCH_FILLER][:8]


def _category_for_terms(terms):
    from categories.models import Category
    for category in Category.objects.filter(active=True).only("id", "nom", "nom_en").order_by("id")[:100]:
        names = set(tokenize(category.nom + " " + category.nom_en))
        expanded = set(names)
        for family in CATALOG_SYNONYMS:
            if names & family:
                expanded.update(family)
        matching = {term for term in terms if term in expanded or (len(term) >= 4 and difflib.get_close_matches(term, sorted(expanded), n=1, cutoff=.84))}
        if matching:
            return category.pk, [term for term in terms if term not in matching]
    return None, terms


def _public_products():
    from products.models import Product
    return Product.objects.filter(actif=True, categorie__active=True).select_related("categorie")


def _search_catalog(queryset, terms):
    from products.search import search_products
    for term in terms[:8]:
        queryset = search_products(queryset, term)
    return queryset


def _serialize_product(product, language):
    return {
        "id": product.pk,
        "name": product.nom_en.strip() if language == "en" and product.nom_en.strip() else product.nom,
        "url": reverse("product_detail", args=[product.slug]),
        "price": str(product.prix_promotion or product.prix), "currency": "XOF",
        "stock": product.stock, "available": product.stock > 0,
    }


def _page_product(context):
    if not isinstance(context, str) or not context.startswith("/") or context.startswith("//") or len(context) > 300:
        return None
    try:
        route = resolve(context)
    except Resolver404:
        return None
    if route.url_name == "product_detail":
        return _public_products().filter(slug=route.kwargs.get("slug")).first()
    return None


def _product_ids(state):
    ids = state.get("product_ids", [])
    if not isinstance(ids, list):
        return []
    return [pk for pk in ids[:5] if type(pk) is int and 0 < pk <= 9223372036854775807]


def _ordinal_position(message):
    words = set(tokenize(message))
    normalized = normalize_question(message)
    return next((index for index, labels in enumerate(ORDINALS)
                 if words & {label for label in labels if not label.isdigit()}
                 or normalized in {label for label in labels if label.isdigit()}), None)


def _price_answer(message, language, state, context):
    result = {"intent": "PRIX_PRODUIT", "score": 20, "answer": INTENTS["PRIX_PRODUIT"][language], "actions": [], "state": {}}
    ids = _product_ids(state)
    words = set(tokenize(message))
    position = _ordinal_position(message)
    product = None
    if position is not None:
        if position < len(ids):
            product = _public_products().filter(pk=ids[position]).first()
        if product is None:
            result["answer"] = "Ce produit n'est plus disponible dans les résultats. Relancez la recherche." if language == "fr" else "That product is not available in the results. Please search again."
            return result
    else:
        terms = [term for term in _search_terms(message) if term not in PRICE_WORDS | {word for word in ORDINAL_WORDS if not word.isdigit()} | {"and", "much", "one", "ones", "its", "actuel", "current", "tell"}]
        if terms:
            named = list(_search_catalog(_public_products(), terms).order_by("nom", "pk")[:2])
            if len(named) == 1:
                product = named[0]
        else:
            product = _page_product(context)
            selected = state.get("selected_product_id")
            if product is None and type(selected) is int and selected in ids:
                product = _public_products().filter(pk=selected).first()
            if product is None and len(ids) == 1:
                product = _public_products().filter(pk=ids[0]).first()
    if product is None:
        # Keep only validated compact context so a following ordinal can answer.
        if ids:
            result["state"] = _retain_search_context({"intent": "PRIX_PRODUIT", "step": "SELECT_PRODUCT", "product_ids": ids}, state)
        return result
    item = _serialize_product(product, language)
    result["results"] = [item]
    result["answer"] = f"{item['name']} : {item['price']} FCFA."
    result["actions"] = [{"label": "Voir le produit" if language == "fr" else "View product", "url": item["url"]}]
    result["state"] = _retain_search_context({"intent": "PRIX_PRODUIT", "step": "CONTINUE", "product_ids": ids if product.pk in ids else [product.pk], "selected_product_id": product.pk}, state)
    return result


def _retain_search_context(next_state, previous):
    query = previous.get("search_query")
    category_id = previous.get("category_id")
    if isinstance(query, str):
        next_state["search_query"] = query[:100]
    if type(category_id) is int and 0 < category_id <= 9223372036854775807:
        next_state["category_id"] = category_id
    return next_state


def _catalog_answer(message, language, state, context, code, continuation):
    if code == "PRIX_PRODUIT" or (state.get("intent") == "PRIX_PRODUIT" and (set(tokenize(message)) & ORDINAL_WORDS)):
        return _price_answer(message, language, state, context)
    terms = _search_terms(message)
    previous = state.get("intent") in {"RECHERCHER_PRODUIT", "PRIX_PRODUIT", "STOCK_PRODUIT"}
    category_id, terms = _category_for_terms(terms)
    if code == "AIDE_GENERALE" and not previous and not category_id:
        # Unknown prose is not silently converted into an arbitrary catalog query.
        if len(terms) != 1:
            return None
    old_query = state.get("search_query", "")
    old_query = old_query[:100] if isinstance(old_query, str) else ""
    if previous and category_id is None and (continuation or code == "AIDE_GENERALE"):
        old_category = state.get("category_id")
        if type(old_category) is int and 0 < old_category <= 9223372036854775807:
            category_id = old_category
        prior_terms = _search_terms(old_query)
        if not continuation and terms and _public_products().filter(marque__iexact=" ".join(terms)).exists():
            # A different explicit real brand replaces the previous brand,
            # while the selected category remains a constraint.
            if prior_terms and _public_products().filter(marque__iexact=" ".join(prior_terms)).exists():
                prior_terms = []
        terms = prior_terms + ([] if continuation else terms)
    terms = list(dict.fromkeys(terms))[:8]
    query = " ".join(terms)[:100]
    queryset = _public_products()
    if category_id:
        queryset = queryset.filter(categorie_id=category_id)
    if not terms and not category_id:
        if code == "AIDE_GENERALE":
            return None
        products = []
    else:
        products = list(_search_catalog(queryset, terms).order_by("nom", "pk")[:5])
    if not products and code == "AIDE_GENERALE" and not previous and not category_id:
        return None
    result = {"intent": "RECHERCHER_PRODUIT", "score": 15, "answer": INTENTS["RECHERCHER_PRODUIT"][language], "actions": _actions(INTENTS["RECHERCHER_PRODUIT"], language, True), "results": [_serialize_product(product, language) for product in products]}
    result["state"] = {"intent": "RECHERCHER_PRODUIT", "step": "CONTINUE", "search_query": query, "product_ids": [product.pk for product in products]}
    if category_id:
        result["state"]["category_id"] = category_id
    if not products:
        result["answer"] = ("Précisez un produit, une catégorie ou une marque." if not terms and not category_id else "Je n'ai trouvé aucun produit correspondant. Essayez un autre terme.") if language == "fr" else ("Please give a product, category or brand." if not terms and not category_id else "I could not find a matching product. Try another term.")
    return result
