"""One-time source authoring aid, NOT a replacement for GNU gettext tools.

Only literal UI text, declared labels/choices and user-facing error/message calls
are marked. Scripts, styles, technical values and migrations are excluded.
PO files are initial editable catalogs; makemessages remains the official updater.
"""
import ast
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = {}
CHANGED = []


def remember(value, path):
    if value:
        CATALOG.setdefault(value, set()).add(path.relative_to(ROOT).as_posix())
    return value


def literal(value):
    return json.dumps(value, ensure_ascii=False)


def python_file(path):
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets, offset = [], 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    def position(line, col):
        return offsets[line-1] + len(lines[line-1].encode("utf-8")[:col].decode("utf-8"))
    def bounds(node):
        return position(node.lineno, node.col_offset), position(node.end_lineno, node.end_col_offset)
    edits = {}
    deferred = path.name.endswith("models.py") or path.name.endswith("forms.py") or path.name.endswith("_files.py")
    function = "gettext_lazy" if deferred else "gettext"
    def mark(node):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str) or not re.search(r"[A-Za-zÀ-ÿ]", node.value):
            return
        start, end = bounds(node)
        edits[(start, end)] = f"{function}({source[start:end]})"
        remember(node.value, path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in {"gettext", "gettext_lazy", "_"}:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    remember(node.args[0].value, path)
            if name in {"ValidationError", "Http404", "HttpResponseForbidden", "PermissionDenied"}:
                if node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Dict):
                        for value in arg.values:
                            mark(value)
                    else:
                        mark(arg)
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "messages" and name in {"success", "warning", "error", "info"} and len(node.args) > 1:
                mark(node.args[1])
            for keyword in node.keywords:
                if keyword.arg in {"label", "help_text", "verbose_name", "verbose_name_plural"}:
                    mark(keyword.value)
                if keyword.arg == "choices":
                    for child in ast.walk(keyword.value):
                        if isinstance(child, ast.Tuple) and len(child.elts) == 2:
                            mark(child.elts[1])
        if isinstance(node, ast.Assign):
            names = [n.id for target in node.targets for n in ast.walk(target) if isinstance(n, ast.Name)]
            if any(n.endswith(("CHOICES", "STATUTS", "MOTIFS", "MOYENS_PAIEMENT", "METHODES", "TYPES_COMPTE", "TYPES_MOUVEMENT", "SENS")) for n in names):
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Tuple) and len(child.elts) == 2:
                        mark(child.elts[1])
            if any(isinstance(target, ast.Attribute) and target.attr in {"label", "help_text"} for target in node.targets):
                mark(node.value)
            if any(n in {"verbose_name", "verbose_name_plural"} for n in names):
                mark(node.value)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in {"label", "help_text", "placeholder"}:
                    mark(value)
    if edits:
        for (start, end), value in sorted(edits.items(), reverse=True):
            source = source[:start] + value + source[end:]
        source = f"from django.utils.translation import {function}\n" + source
        path.write_text(source, encoding="utf-8")
        CHANGED.append(path.relative_to(ROOT).as_posix())


TOKEN = re.compile(r"(<!--.*?-->|<script\b.*?</script\s*>|<style\b.*?</style\s*>|{%\s*(?:blocktrans|blocktranslate)\b.*?{%\s*end(?:blocktrans|blocktranslate)\s*%}|{%.*?%}|{{.*?}}|<(?:\"[^\"]*\"|'[^']*'|[^'\">])*>)", re.S | re.I)
ATTR = re.compile(r'(\b(?:placeholder|title|aria-label|alt)\s*=\s*)([\"\x27])(.*?)(\2)', re.S)


def template_file(path):
    source = path.read_text(encoding="utf-8-sig")
    pieces = TOKEN.split(source)
    changed = False
    for i, part in enumerate(pieces):
        if not part:
            continue
        if i % 2:
            if part.startswith("<") and not re.match(r"<(?:script|style|!--)", part, re.I):
                def attribute(match):
                    nonlocal changed
                    value = match.group(3)
                    if any(x in value for x in ("{{", "{%")) or not re.search(r"[A-Za-zÀ-ÿ]", value):
                        return match.group(0)
                    value = remember(html.unescape(value), path)
                    changed = True
                    return match.group(1) + match.group(2) + "{% trans " + literal(value) + " %}" + match.group(2)
                pieces[i] = ATTR.sub(attribute, part)
            elif re.match(r"{%\s*(?:trans|translate)\b", part):
                match = re.match(r"{%\s*(?:trans|translate)\s+([\"\x27])(.*?)\1", part, re.S)
                if match:
                    remember(match.group(2), path)
            continue
        value = part.strip()
        if not re.search(r"[A-Za-zÀ-ÿ]", value) or value.startswith(("http://", "https://")):
            continue
        value = html.unescape(value)
        # Preserve whitespace around literal nodes, never touch template variables.
        left = part[:len(part)-len(part.lstrip())]
        right = part[len(part.rstrip()):]
        pieces[i] = left + "{% trans " + literal(remember(value, path)) + " %}" + right
        changed = True
    if changed:
        source = "".join(pieces)
        if not re.search(r"{%\s*load\s+[^%]*\bi18n\b", source):
            extends = re.search(r"{%\s*extends\b.*?%}", source)
            index = extends.end() if extends else 0
            source = source[:index] + "{% load i18n %}" + source[index:]
        path.write_text(source, encoding="utf-8")
        CHANGED.append(path.relative_to(ROOT).as_posix())


EN = dict(line.split("|", 1) for line in """
Langue|Language
Appliquer|Apply
Accueil|Home
Boutique|Shop
Catégories|Categories
Catégorie|Category
Panier|Cart
Commandes|Orders
Mes commandes|My orders
Mes livraisons|My deliveries
Livraisons|Deliveries
Notifications|Notifications
Mon profil|My profile
Profil|Profile
Se connecter|Sign in
Connexion|Sign in
Déconnexion|Sign out
Se déconnecter|Sign out
Créer un compte|Create an account
Inscription|Sign up
Mot de passe|Password
Mot de passe oublié ?|Forgot your password?
Mot de passe oublié|Forgotten password
Changer le mot de passe|Change password
Nouveau mot de passe|New password
Confirmer le mot de passe|Confirm password
Nom d'utilisateur|Username
Identifiant|Username
Adresse e-mail|Email address
Prénom|First name
Nom|Name
Téléphone|Phone
Adresse|Address
Ville|City
Pays|Country
Date de naissance|Date of birth
Lieu de naissance|Place of birth
Genre|Gender
Homme|Man
Femme|Woman
Préfère ne pas préciser|Prefer not to say
Photo de profil|Profile photo
Enregistrer|Save
Annuler|Cancel
Modifier|Edit
Supprimer|Delete
Valider|Confirm
Confirmer|Confirm
Continuer|Continue
Retour|Back
Fermer|Close
Rechercher|Search
Recherche|Search
Filtrer|Filter
Réinitialiser|Reset
Voir le détail|View details
Voir les détails|View details
Détail|Details
Tous|All
Toutes|All
Oui|Yes
Non|No
Aucun|None
Aucune|None
Actions|Actions
Action|Action
Date|Date
Statut|Status
Référence|Reference
Montant|Amount
Total|Total
Sous-total|Subtotal
Prix|Price
Quantité|Quantity
Produit|Product
Produits|Products
Description|Description
Marque|Brand
En stock|In stock
Rupture de stock|Out of stock
Ajouter au panier|Add to cart
Votre panier|Your cart
Votre panier est vide|Your cart is empty
Continuer mes achats|Continue shopping
Passer commande|Place order
Finaliser votre commande|Complete your order
Commande sécurisée|Secure checkout
Livraison|Delivery
Paiement|Payment
Paiements|Payments
En attente|Pending
Payé|Paid
Échoué|Failed
Annulé|Cancelled
Annulée|Cancelled
Confirmée|Confirmed
Expédiée|Shipped
Livrée|Delivered
Espèces|Cash
Carte bancaire|Bank card
Carte / Banque|Card / Bank
Banque|Bank
Livraison standard|Standard delivery
Livraison express|Express delivery
Gratuite|Free
Rue|Street number
Porte|Door number
Repère|Landmark
Repère :|Landmark:
Quartier / Rue / Avenue|District / Street / Avenue
N° de porte / Repère|Door number / Landmark
Téléphone utile à la livraison|Delivery contact phone
Mode de livraison|Delivery method
Adresse de livraison|Delivery address
Frais de livraison|Delivery fee
Récapitulatif|Summary
Confirmation|Confirmation
Commande|Order
Reçu|Receipt
Télécharger|Download
Imprimer|Print
Imprimer le reçu|Print receipt
Retour à la commande|Back to order
Votre reçu officiel de commande|Your official order receipt
Commande confirmée|Order confirmed
Articles de la commande|Order items
Adresse non renseignée|No address provided
Adresse client|Customer address
Client|Customer
Clients|Customers
Vendeur|Sales assistant
Vendeurs|Sales assistants
Livreur|Delivery driver
Comptable|Accountant
Administrateur|Administrator
Administration|Administration
Pilotage|Overview
Vue d'ensemble|Overview
Tableau de bord|Dashboard
Finance|Finance
Comptabilité|Accounting
Encaissements|Receipts
Transactions|Transactions
Dépenses|Expenses
Dépense|Expense
Dépenses & charges|Expenses & costs
Catégories de dépenses|Expense categories
Catégorie de dépense|Expense category
Brouillon|Draft
Validée|Validated
Brouillons|Drafts
Bénéficiaire|Payee
Libellé|Description
Moyen de paiement|Payment method
Justificatif|Supporting document
Commentaire|Comment
Créateur|Created by
Validateur|Validated by
Créé par|Created by
Validé par|Validated by
Date validation|Validation date
Date création|Creation date
Comptes financiers|Financial accounts
Compte|Account
Comptes|Accounts
Nouveau compte|New account
Modifier le compte|Edit account
Actif|Active
Défaut|Default
Devise|Currency
Initial|Opening balance
Entrées|Inflows
Sorties|Outflows
Entrée|Inflow
Sortie|Outflow
Solde théorique|Theoretical balance
Liquidités théoriques|Theoretical liquidity
Journal financier|Financial ledger
Transfert|Transfer
Nouveau transfert|New transfer
Ajustement|Adjustment
Nouvel ajustement|New adjustment
À régulariser|To allocate
Mouvements à régulariser|Movements awaiting allocation
Affecter au compte|Assign to account
Choisir un compte|Choose an account
Clôtures financières|Financial closings
Nouvelle clôture|New closing
Clôtures et écarts constatés|Closings and observed discrepancies
Historique des clôtures|Closing history
Solde constaté|Observed balance
Écart constaté|Observed discrepancy
Conforme|Balanced
Excédent constaté|Observed surplus
Manquant constaté|Observed shortfall
Enregistrer le brouillon|Save draft
Valider et figer|Validate and freeze
Annuler la clôture|Cancel closing
Commentaire / justification|Comment / explanation
Historique d'activité|Activity history
Aucun justificatif.|No supporting document.
Aucun commentaire.|No comment.
Aucune activité.|No activity.
Non validée|Not validated
Personne|Nobody
Système|System
Source|Source
Type|Type
Export CSV|Export CSV
Export CSV filtré|Export filtered CSV
Exporter|Export
Toutes les transactions|All transactions
Tous les statuts|All statuses
Tous les types|All types
Tous les types de compte|All account types
Tous les mouvements|All movements
Entrées et sorties|Inflows and outflows
Activités|Activity
Alertes|Alerts
Paramètres boutique|Shop settings
Utilisateurs|Users
Rôle|Role
Contact|Contact
Performance vendeurs|Sales assistant performance
Outils financiers|Financial tools
Stock|Stock
Historique|History
Vente comptoir|Counter sale
Enregistrer une vente|Record a sale
Ventes comptoir|Counter sales
Vente|Sale
Liste produits|Product list
Ajouter un produit|Add product
Activer|Activate
Désactiver|Deactivate
Suivi de livraison|Delivery tracking
Suivi & discussion|Tracking & discussion
À affecter|Unassigned
Affectée|Assigned
Acceptée|Accepted
En préparation|Being prepared
Prête|Ready
En route|On the way
Arrivé|Arrived
Échec de livraison|Delivery failed
Échecs|Failures
À accepter|Awaiting acceptance
En cours|In progress
Terminées|Completed
Livrées aujourd'hui|Delivered today
Non affecté|Unassigned
Affecter / réaffecter|Assign / reassign
Enregistrer l'affectation|Save assignment
Actions opérationnelles|Operational actions
Chronologie|Timeline
Par|By
Sans livreur|No driver
Appeler le client|Call customer
Envoyer|Send
Messages précédents|Earlier messages
Messages suivants|Later messages
Client absent|Customer absent
Adresse introuvable|Address not found
Client injoignable|Customer unreachable
Refus client|Customer refused delivery
Autre|Other
Choisir un motif|Choose a reason
Motif de l'échec|Reason for failure
Initialiser la livraison|Initialize delivery
Discussion conservée en lecture seule.|Discussion retained as read-only.
Un message ne change jamais le statut de la livraison.|A message never changes the delivery status.
1000 caractères maximum. Texte uniquement.|Up to 1,000 characters. Text only.
Aucun message pour le moment.|No messages yet.
Veuillez vous connecter.|Please sign in.
Veuillez vous connecter pour accéder à cette page.|Please sign in to access this page.
Compte introuvable.|Account not found.
Compte obligatoire.|An account is required.
Cette livraison ne vous est pas accessible.|You do not have access to this delivery.
Écrivez un message non vide.|Please enter a message.
Transition non autorisée dans cet état.|This transition is not allowed in the current state.
Seul un brouillon est modifiable.|Only a draft can be edited.
Une clôture ne peut pas être datée dans le futur.|A closing cannot be dated in the future.
La date de clôture ne peut pas être dans le futur.|The closing date cannot be in the future.
Période invalide.|Invalid date range.
La date de fin doit suivre la date de début.|The end date must not precede the start date.
Formats acceptés : PDF, JPG/JPEG, PNG et WebP.|Accepted formats: PDF, JPG/JPEG, PNG and WebP.
Le justificatif doit peser entre 1 octet et 5 Mo.|The supporting document must be between 1 byte and 5 MB.
Le type du fichier ne correspond pas à son extension.|The file type does not match its extension.
Le fichier envoyé n'est pas un PDF.|The uploaded file is not a PDF.
Le fichier PDF est incomplet.|The PDF file is incomplete.
L'image ne correspond pas à son extension.|The image does not match its extension.
Le justificatif est illisible ou invalide.|The supporting document is unreadable or invalid.
Justificatif introuvable.|Supporting document not found.
La photo doit peser 5 Mo maximum.|The photo must not exceed 5 MB.
Format non accepté. Utilisez une image JPG, JPEG, PNG ou WebP.|Unsupported format. Use a JPG, JPEG, PNG or WebP image.
Le fichier envoyé n'est pas une image valide.|The uploaded file is not a valid image.
Renseignez votre adresse et votre ville de livraison.|Enter your delivery address and city.
Choisissez un mode de livraison valide.|Choose a valid delivery method.
Choisissez un moyen de paiement valide.|Choose a valid payment method.
Votre panier est vide. Ajoutez un produit avant de poursuivre.|Your cart is empty. Add a product to continue.
Votre panier est déjà vide.|Your cart is already empty.
Un produit de votre panier n'est plus disponible.|A product in your cart is no longer available.
Toutes les notifications ont été marquées comme lues.|All notifications have been marked as read.
Connecté en tant que|Signed in as
Rechercher un produit, une marque...|Search for a product or brand...
Rechercher dans la boutique|Search the shop
Lancer la recherche|Search
Ouvrir le menu|Open menu
Se souvenir de moi|Remember me
Retour à la connexion|Back to sign in
Retour à l'accueil|Back to home
Mettre à jour|Update
Enregistrer les modifications|Save changes
Modifier mon profil|Edit my profile
Favoris|Favourites
Mes favoris|My favourites
Explorer la boutique|Browse the shop
Dernière opération|Last operation
Solde négatif|Negative balance
Aucun compte configuré.|No accounts configured.
Actif :|Active:
Défaut :|Default:
Réinitialiser le mot de passe|Reset password
Cette information n'est pas disponible hors connexion.|This information is not available offline.
Cette action nécessite une connexion Internet.|This action requires an Internet connection.
Synchronisation terminée.|Sync complete.
Dernière synchronisation|Last sync
En ligne|Online
Hors connexion|Offline
Erreur|Error
Attention|Warning
Information|Information
Informations|Information
Gestion Boutique|Shop Management
Gestion Boutique Admin|Shop Management Admin
""".strip().splitlines())


def catalog(language):
    path = ROOT / 'locale' / language / 'LC_MESSAGES' / 'django.po'
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"Project-Id-Version: Gestion Boutique\nReport-Msgid-Bugs-To: \nPOT-Creation-Date: 2026-09-12 00:00+0000\nPO-Revision-Date: 2026-09-12 00:00+0000\nLast-Translator: Project team\nLanguage-Team: {language}\nLanguage: {language}\nMIME-Version: 1.0\nContent-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: 8bit\nPlural-Forms: nplurals=2; plural=(n != 1);\n"
    output = ['# Initial editable catalog. Update using GNU gettext / Django makemessages.', 'msgid ""', 'msgstr ""']
    output.extend(literal(line+'\n') for line in header.splitlines())
    for msgid, refs in sorted(CATALOG.items()):
        output.extend(['', '#: '+' '.join(sorted(refs)), 'msgid '+literal(msgid), 'msgstr '+literal(EN.get(msgid, '') if language == 'en' else '')])
    path.write_text('\n'.join(output)+'\n', encoding='utf-8')


if __name__ == '__main__':
    for app in ('accounts', 'orders', 'payments', 'products', 'dashboard', 'notifications', 'core', 'cart', 'categories', 'reviews'):
        for path in sorted((ROOT/app).glob('*.py')):
            if path.name.startswith('test') or path.name in {'apps.py', 'admin.py', 'urls.py'}:
                continue
            python_file(path)
    for path in sorted((ROOT/'templates').rglob('*.html')):
        template_file(path)
    catalog('en')
    catalog('bm')
    print(json.dumps({'files': len(CHANGED), 'messages': len(CATALOG), 'english_translated': sum(bool(EN.get(m)) for m in CATALOG)}, ensure_ascii=False))
    (ROOT/'docs'/'i18n-files.txt').write_text('\n'.join(CHANGED)+'\n', encoding='utf-8')
