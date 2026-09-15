# Gestion Boutique

Application Django de gestion d'une boutique : catalogue, panier, commandes, livraison, paiements, notifications et suivi financier.

## Installation locale

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

Le projet utilise Django 5.2+ et Python 3.12+. Créez un compte avec `createsuperuser` pour accéder à l'administration. Les rôles applicatifs sont client, vendeur, livreur, comptable et administrateur.

## Configuration

Les secrets restent dans l'environnement et ne sont jamais inclus dans les templates, JavaScript, logs ou le dépôt. Les variables principales sont : `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `PAYMENT_PROVIDER`, `PAYMENT_PUBLIC_KEY`, `PAYMENT_SECRET_KEY` et `PAYMENT_WEBHOOK_SECRET`. Voir [.env.example](.env.example).

## Paiements en ligne

Le moyen `online` utilise une abstraction `PaymentProvider` avec `FlutterwaveProvider` et `CinetPayProvider`. Le checkout hébergé est créé côté serveur à partir du total de la commande. Le navigateur ne peut pas confirmer un paiement : le retour et le webhook appellent la vérification serveur du provider actif avant de confirmer la commande.

Provider CinetPay :

```text
PAYMENT_PROVIDER=cinetpay
CINETPAY_API_KEY=
CINETPAY_SITE_ID=
CINETPAY_SECRET_KEY=
```

Le callback CinetPay est `/payments/webhooks/cinetpay/`. CinetPay documente un environnement de test lié au compte marchand ; aucun identifiant réel n'est inclus dans le projet.

Pour un test, renseignez les clés TEST Flutterwave dans l'environnement :

```text
PAYMENT_PROVIDER=flutterwave
PAYMENT_PUBLIC_KEY=...
PAYMENT_SECRET_KEY=...
PAYMENT_WEBHOOK_SECRET=...
```

`PAYMENT_WEBHOOK_SECRET` doit contenir le secret hash configuré dans Flutterwave. Le webhook accepte le format actuel `flutterwave-signature` (HMAC-SHA256 Base64) et le format v3 historique `verif-hash` (comparaison directe), selon le flux configuré. Configurez l'URL publique `/payments/webhooks/flutterwave/`. Les notifications répétées sont idempotentes et le paiement en ligne ne décrémente jamais le stock : le stock suit la règle de création de commande existante.

Sans clés, l'application reste utilisable et affiche `Configuration sandbox requise.`. Ne fournissez jamais de vraies clés dans une capture, un commit ou un README.

## Assistant-guide client

Le bouton d'aide ouvre un guide local déterministe. `core/assistant.py` normalise la question, score des mots-clés et synonymes, puis renvoie une réponse FR/EN et des liens sûrs. L'endpoint `POST /assistant/ask/` ne modifie aucune donnée et n'exécute aucune opération métier. Les actions sensibles restent dans les pages Django protégées.

## Fonctionnalités métier

Les commandes passent par le panier et le checkout. Les paiements existants (espèces, Orange Money, Moov Money, Wave et carte) sont conservés. Après confirmation, les transactions payées alimentent la comptabilité sans double comptage. Les reçus peuvent afficher le provider et la référence externe. La livraison possède ses vues client, vendeur et livreur, avec discussion et statuts.

## Langues, thème et responsive

Le français et l'anglais sont gérés par Django. Le thème clair/sombre est conservé. La feuille `static/css/style.css` adopte une composition mobile-first, avec formulaires empilés, tables contenues, images fluides et assistant limité à la largeur de la fenêtre. Les largeurs cibles vont de 320 px aux écrans desktop.

## Vérification

```powershell
python manage.py check
python manage.py test core.test_i18n
python manage.py test core.test_assistant
python manage.py test payments orders accounts dashboard
python manage.py test core products categories orders payments dashboard accounts
python manage.py makemigrations --check --dry-run
```

Les tests de paiement remplacent le provider par un faux provider local. Un test sandbox réel nécessite des identifiants TEST disponibles dans l'environnement et une URL de retour/webhook accessible.

## Accès depuis un téléphone du réseau local

Lancez `python manage.py runserver 0.0.0.0:8000`, ajoutez l'adresse IP locale du PC dans `DJANGO_ALLOWED_HOSTS` et ouvrez `http://IP_DU_PC:8000` depuis le téléphone. Pour Flutterwave, utilisez ensuite une URL publique HTTPS et configurez `DJANGO_CSRF_TRUSTED_ORIGINS` et l'URL webhook correspondantes.

## Déploiement et reprise

En production, désactivez le debug, utilisez une clé Django secrète, configurez les hôtes et origines HTTPS, collectez les fichiers statiques et exécutez `migrate`. Avant une release, lancez les commandes de vérification ci-dessus. Les migrations sont additives et ne doivent pas être réécrites. Le service de paiement, l'assistant et les règles de stock sont isolés dans leurs modules pour faciliter la maintenance.
