# Audit de sécurité — Gestion Boutique de Hamza

Date : 15 octobre 2026. Référence initiale : `de44714`, branche `feat/livraison-preuve-tarification`. Branche de travail : `audit/securite-soutenance-hamza`.

## 1. Périmètre et protection du projet

Audit du code Django, des routes, formulaires, services, templates et JavaScript concernant les comptes, rôles, panier, commandes, paiements, livraisons, fichiers, exports, bot et configuration. Aucun `AGENTS.md` trouvé dans le dépôt ou ses parents inspectés.

La base configurée localement est `db.sqlite3` (SQLite). L'état des migrations a été lu : les migrations existantes, notamment `accounts.0006` et `orders.0006`, sont appliquées. Aucune migration créée ou appliquée pendant cette intervention. Aucune opération métier sur cette base, aucun compte supprimé, aucun mot de passe réinitialisé, aucune intervention en production. Les exemples et tests utilisent des données synthétiques.

`config/settings.py` était déjà modifié avant l'audit : son empreinte SHA-256 finale est identique à celle relevée au départ. Il est exclu des commits. Les tests finaux utilisent une base SQLite de test et deux répertoires temporaires distincts pour `MEDIA_ROOT` et `PRIVATE_EXPENSE_ROOT`. Les commandes de purge apparaissant dans leur sortie ne concernent que les données de test.

## 2. Architecture de sécurité existante

- Authentification Django, hachage des mots de passe, sessions serveur, CSRF et échappement des templates. Validation des mots de passe et redirection de connexion limitée aux destinations locales.
- Profils client, vendeur, livreur, comptable et administrateur ; contrôles serveur dans les vues et services, filtrage des objets selon leur propriétaire ou leur affectation. L'inscription publique ne peut attribuer un rôle privilégié.
- Backend et middleware de suspension : refus de connexion et fermeture des sessions suspendues. Ces protections restent actives même quand Live Security est masqué.
- Checkout transactionnel, calculs serveur, vérification du stock, copie des prix dans la commande, protection des montants acceptés. Paiement distinct lié à la commande et contrôles d'idempotence.
- Signatures conservées en base, hors des médias publics ; accès authentifié contrôlé et journalisé. Normalisation PNG, limites de taille et dimensions, preuve unique, transitions transactionnelles et procédure de dérogation administrative.
- Tarifs proposés par les livreurs puis approuvés par l'administration ; devis signé lié au client, à la ville, au mode et au montant, avec expiration.
- Pièces comptables privées, téléchargements soumis aux permissions, en pièces jointes avec protections de contenu. Neutralisation des cellules dangereuses dans les exports CSV examinés.

## 3. Méthode et preuves

Lecture ciblée des points d'entrée et des services, recherche des exemptions CSRF, redirections, téléchargements, usages de `safe`, `mark_safe`, `innerHTML` et accès SQL. Reproduction locale des défauts avant correction lorsque possible ; tests négatifs et positifs après correction. Vérification des dépendances par `pip-audit`, contrôles Django et scénarios Edge sur serveur de test.

Les tests de référence ont réellement été exécutés avant modification : **626 tests réussis en 441,553 s**. Ils ne constituent pas une preuve d'absence de vulnérabilité. Aucun scan intrusif ni paiement réel n'a été réalisé.

## 4. Vulnérabilités confirmées et corrections

| Référence | Gravité estimée | Preuve et risque métier | Correction |
| --- | --- | --- | --- |
| SEC-01 | Élevée | Le téléversement vendeur acceptait une image PNG valide suivie de HTML, déclarée comme image mais nommée `.html`. La validation Pillow seule ne rejetait pas ce fichier. Un média servi comme HTML sur la même origine pouvait exécuter du script lors de son ouverture. | Extension et format réel cohérents, décodage et réencodage des pixels, nom UUID et extension canonique pour les nouveaux produits et logos ; même normalisation dans l'admin produits. Tests du polyglotte, des routes et de la conservation des anciennes photos. |
| SEC-02 | Moyenne | Les mutations du panier acceptaient GET : un lien ou une navigation pouvait modifier le panier sans jeton CSRF. | Ajout, retrait, augmentation et diminution uniquement en POST ; formulaires avec jeton CSRF, contrôles de propriétaire conservés. GET/HEAD sans mutation, POST sans CSRF refusé. |
| SEC-03 | Faible | GET déconnectait l'utilisateur, permettant une déconnexion imposée. | Déconnexion POST/CSRF ; menu adapté et purge du cache privé attendue avant l'envoi du formulaire. |
| SEC-04 | Moyenne | Les échecs de connexion étaient journalisés, sans limitation effective des tentatives. La récupération de mot de passe ne limitait pas les demandes de courrier. | Compteurs temporaires de tentatives par IP et identifiant, partagés par connexion boutique et admin ; limite IP sur la récupération. Réponses génériques, expiration fixe, pas de suspension définitive. |
| SEC-05 | Moyenne | Le bot limitait la longueur du message, mais pas la taille globale spécifique du JSON ni la fréquence des appels. Du remplissage JSON dépassant 4 Kio était accepté. | Corps limité à 4 096 octets, 60 requêtes/minute/IP par défaut ; 413 ou 429, erreurs de structure gérées. Aucun changement du moteur conversationnel. |
| SEC-06 | Variable, potentiellement élevée selon le chemin concerné | Les versions épinglées Django 5.2.7 et sqlparse 0.5.5 avaient des avis de sécurité connus. L'audit initial a retourné 59 avis pour Django et 9 pour sqlparse. Ce ne sont **pas 68 exploitations démontrées de cette application**. | Django 5.2.18 et sqlparse 0.6.0, installation et validation dans `.venv-security`. Audit final sans avis connu sur les dépendances résolues et Gunicorn contrôlé séparément. |
| SEC-07 | Moyenne | Le service worker précachait la page d'accueil avec les cookies et pouvait enregistrer le HTML personnalisé ainsi que `/offline/sync/` dans un cache commun. Les quatre tests ciblés échouent sur le code antérieur. `no-store` HTTP ne suffit pas à empêcher un `cache.put` explicite. | Page de secours chargée sans credentials, aucune mise en cache du HTML de session ou des réponses privées, renouvellement du cache et nettoyage des anciens caches de l'application seulement. Lecture limitée au cache de cette version. Test Edge d'installation avec un utilisateur connecté. |

L'exploitation par navigateur de SEC-01 dépend du service des médias et de leur type HTTP ; la validation défectueuse est reproduite, aucune victime réelle n'a été exposée. La gravité décrit le risque, pas un incident constaté.

Renforcements complémentaires, sans les présenter comme des exploitations démontrées :

- Redirection des notifications limitée à l'origine courante et à HTTPS lorsque la requête est sécurisée. Le POST/CSRF préexistant limitait déjà le scénario d'exploitation externe.
- `Cache-Control: no-store` pour la synchronisation contenant des données privées et pour les réponses du bot. Le stockage hors ligne explicite reste une fonctionnalité distincte, cloisonnée et purgée à la déconnexion.
- Profil de production opt-in, CSP minimale et vérifications de déploiement.
- Interface Live Security désactivée par défaut, liens retirés conditionnellement ; routes refusées si désactivées. Pas de nouveau suivi, aucune capture d'écran, aucune suppression de modèles ou données.

## 5. Paramètres des nouvelles protections

| Paramètre Django | Valeur par défaut | Effet |
| --- | --- | --- |
| `AUTH_LOGIN_MAX_FAILURES` / `AUTH_LOGIN_WINDOW_SECONDS` | 10 / 300 | Échecs par couple adresse serveur / identifiant ; réussite remet le compteur à zéro. |
| `AUTH_PASSWORD_RESET_MAX_REQUESTS` / `AUTH_PASSWORD_RESET_WINDOW_SECONDS` | 5 / 300 | Demandes de récupération par adresse ; même redirection générique quand la limite est dépassée. |
| `ASSISTANT_MAX_BODY_BYTES` | 4096 | Taille maximale du JSON du bot. |
| `ASSISTANT_MAX_REQUESTS` / `ASSISTANT_WINDOW_SECONDS` | 60 / 60 | Requêtes du bot par adresse ; rotation des cookies sans effet sur la limite. |
| `LIVE_SECURITY_ENABLED` | Faux | Paramètre Django ou variable d'environnement `LIVE_SECURITY_ENABLED=1` pour réactiver explicitement l'interface. |
| `DELIVERY_PROOF_RETENTION_DAYS` | 365, préexistant | Conservation des preuves ; commande `purge_delivery_proofs` en prévisualisation par défaut, suppression uniquement sur action explicite. Non exécutée sur les données locales. |

Les clés de limitation utilisent un HMAC : ni identifiant ni adresse en clair dans la clé de cache. Les en-têtes `X-Forwarded-For` fournis par le client ne sont pas considérés fiables. Les tentatives déjà bloquées ne génèrent plus une nouvelle entrée de journal à chaque appel.

Nouvelles images publiques concernées : JPEG, PNG et WebP statiques, maximum 5 Mio avant et après normalisation, 8 192 pixels par côté et 20 millions de pixels. Orientation EXIF appliquée puis métadonnées et octets supplémentaires éliminés. Transparence PNG/WebP conservée. GIF/BMP et animations refusés pour ces nouveaux téléversements. Aucune réécriture des photographies déjà stockées. Les avatars, déjà soumis à une liste d'extensions et à une validation d'image, n'ont pas été transformés.

## 6. Résultats par domaine

| Domaine | Vérifications et résultat | Limite |
| --- | --- | --- |
| Comptes | Connexion, reset, déconnexion, rotation/session, suspension, redirection locale, alias e-mail, partage avec admin, expiration et CSRF. Tests réussis. | Pas de simulation distribuée de credential stuffing ; cache partagé nécessaire en multiworker. |
| Permissions | Anonyme et rôles client, vendeur, livreur, comptable, admin ; objets panier/notifications, commandes, preuves, tarifs et tableaux de bord couverts par tests existants et nouveaux. | Revue du code et cas testés, pas exploration exhaustive de toutes les combinaisons. |
| Commandes et stock | Montants du navigateur ignorés, stock insuffisant refusé, double checkout séquentiel refusé, opérations atomiques. Tests réussis. | SQLite ne réalise pas de verrouillage de lignes avec `select_for_update`. La concurrence sur PostgreSQL n'a pas été simulée ; risque d'erreurs de verrouillage SQLite à qualifier sous charge. |
| Paiements | Fournisseurs actifs : vérification serveur, montant/devise/référence, propriété de commande, signatures webhook et idempotence dans les tests mockés. Retour navigateur seul insuffisant. | Pas d'appel financier réel ni certification fournisseur. La fonction historique `wave_webhook` n'est pas exposée dans les routes actuelles ; ne pas l'exposer sans authentification de webhook. Moov reste une préparation d'intégration, pas une activation opérateur. |
| Livraison | Signature absente/invalide, doublon, accès d'un autre client/livreur, dérogation, retours, tarifs approuvés, conservation du montant, purge en base de test. | Une image manuscrite ne prouve pas cryptographiquement l'identité humaine du signataire. |
| Fichiers/CSV | Téléversements publics normalisés, fichiers comptables privés contrôlés, preuve de livraison hors MEDIA_URL, neutralisation CSV examinée. | Aucun balayage ni nettoyage des fichiers utilisateurs existants ; leur revue éventuelle doit être séparée et sauvegardée. |
| Web | CSRF, échappement, ORM, usages sensibles des templates/JS, redirections et en-têtes examinés ; pas d'injection SQL ou IDOR supplémentaire confirmée. | Pas de pentest externe ; CSP complète avec nonces non déployée. |
| Bot | Taille, fréquence, entrées JSON, liens vers des routes protégées, réponses et données privées vérifiés. | Moteur et cohérence des réponses inchangés, comme demandé. |

## 7. Production et dépendances

`config.production` est un profil séparé, à sélectionner explicitement avec `DJANGO_SETTINGS_MODULE=config.production`. Le serveur local continue d'utiliser `config.settings` et HTTP.

Le profil exige `DJANGO_SECRET_KEY` externe d'au moins 50 caractères et des `DJANGO_ALLOWED_HOSTS` explicites sans `*`. Fournir un secret aléatoire réel via le gestionnaire de secrets, jamais dans Git. Les origines `DJANGO_CSRF_TRUSTED_ORIGINS` doivent être HTTPS. Cookies Secure/HttpOnly pour la session, SameSite Lax, redirection HTTPS, HSTS, nosniff, referrer same-origin et X-Frame-Options DENY sont définis.

La CSP ajoutée est volontairement limitée à `object-src 'none'; base-uri 'self'; frame-ancestors 'none'`. Elle préserve une CSP plus stricte fixée par une vue privée. Elle ne bloque pas tous les scripts injectés et ne doit pas être présentée comme une protection XSS complète.

`DJANGO_REDIS_CACHE_URL` active Redis pour partager les compteurs entre workers. Le client Redis est épinglé ; son instanciation a été testée sans connexion réseau. Le déploiement doit fournir un Redis privé et protégé. Sans cette variable, le cache local ne constitue pas une limitation globale multiworker.

Le contrôle de déploiement utilise un secret éphémère et un hôte synthétique, sans interroger une base de production. Résultat : aucune erreur, **un avertissement `security.W021`**, car `SECURE_HSTS_PRELOAD=False`. L'inscription preload nécessite un domaine réel et une décision opérationnelle ; elle n'a pas été activée artificiellement pour supprimer l'avertissement. HSTS inclut les sous-domaines : vérifier leur disponibilité en HTTPS avant activation réelle du profil.

L'environnement global Python n'a pas été mis à jour : les résultats finaux concernent `.venv-security` et Django 5.2.18. Pour lancer la version validée, utiliser cet environnement ou installer `requirements.txt` dans l'environnement de déploiement. L'environnement de validation local hérite des outils système ; un build de production propre et reproductible reste recommandé.

Audit final : 15 dépendances résolues sur Windows, aucun avis connu ; Gunicorn 23.0.0, exclu par le marqueur Windows, contrôlé séparément sans avis connu. `pip check` ne signale aucune dépendance cassée. Cet audit dépend de la base d'avis disponible à la date d'exécution et ne remplace pas une revue de code.

Référence primaire pour les correctifs Django : [publication officielle Django 5.2.18 du 6 octobre 2026](https://www.djangoproject.com/weblog/2026/oct/06/security-releases/). Aucun détail de secret, de compte réel ou de transaction client n'est inclus ici.

## 8. Fichiers modifiés

- Authentification : `accounts/security.py`, `accounts/views.py`, `accounts/urls.py`, `accounts/test_auth_hardening.py`, `accounts/tests.py`, `accounts/test_security.py`.
- Panier et navigation : `cart/views.py`, `cart/tests.py`, `templates/cart/cart_detail.html`, `templates/products/_product_card.html`, `templates/products/product_detail.html`, `templates/base.html`, `static/css/style.css`.
- Notifications : `notifications/views.py`, `notifications/test_redirect_security.py`.
- Bot, cache et Live Security : `core/views.py`, `core/context_processors.py`, `core/security_flags.py`, `core/test_security_hardening.py`, `core/test_e2e.py`, `dashboard/security_views.py`, `templates/dashboard/admin_dashboard_v2.html`, `static/js/offline-manager.js`, `static/js/tests/offline-logout.test.cjs`, `static/service-worker.js`, `static/js/tests/service-worker-security.test.cjs`, `dashboard/test_finance.py` et `dashboard/test_clotures.py`.
- Images : `core/image_uploads.py`, `dashboard/vendeur_views.py`, `dashboard/views.py`, `dashboard/test_upload_security.py`, `products/admin.py`.
- Déploiement et validation : `config/production.py`, `core/security_middleware.py`, `core/test_production_security.py`, `requirements.txt`, `.gitignore`, `tools/run_security_tests.py`, `tools/validate_security_browser.py` et ce rapport.

Aucun modèle ni migration modifié. `config/settings.py` est une modification locale préexistante, exclue de cette liste de corrections et des commits.

## 9. Tests et reproduction

Depuis la racine du dépôt, utiliser l'interpréteur validé :

```powershell
.venv-security/Scripts/python.exe -B manage.py check
.venv-security/Scripts/python.exe -B manage.py makemigrations --check --dry-run
.venv-security/Scripts/python.exe -B tools/run_security_tests.py
.venv-security/Scripts/python.exe -B tools/run_security_tests.py tools.validate_security_browser tools.validate_delivery_proof_browser
node --check static/js/offline-manager.js
node --check static/service-worker.js
node --test static/js/tests/offline-logout.test.cjs static/js/tests/service-worker-security.test.cjs
.venv-security/Scripts/python.exe -m pip check
```

`run_security_tests.py` appelle réellement `manage.py test --noinput` via Django en surchargeant uniquement les deux destinations des fichiers de test ; il refuse une base par défaut non SQLite. Il conserve les hashers usuels pour la suite, sauf les classes de tests qui les remplacent explicitement pour leurs propres fixtures. Le `manage.py test --noinput` initial a également été exécuté directement.

| Validation | Résultat |
| --- | --- |
| Référence avant corrections | 626 tests, OK, 441,553 s |
| Suite complète après corrections et mises à jour | **667 tests, OK, 406,109 s** |
| Nouveaux tests Django découverts | 41 : authentification 12, notifications 4, panier 7, images 8, bot/flag/cache 6, production 4 |
| Contrôle Django | Aucun problème signalé |
| Migrations à générer | Aucune modification détectée |
| Suite navigateur finale | **4 tests Edge, OK, 36,331 s**, en plus des 667 tests Django |
| Edge, parcours compte/panier/déconnexion | 390 et 1 280 px, POST/CSRF réels, purge IndexedDB vérifiée, aucun débordement du panier ni erreur JS constatée |
| Edge, service worker | Installation authentifiée : page mise en cache anonyme, aucune identité de fixture ni réponse de synchronisation dans Cache Storage |
| Edge, livraison/checkout | Signature desktop et émulations Pixel 5/iPhone 13 ; offre tarifaire signée transmise et total confirmé en base de test |
| JavaScript | Syntaxe des deux scripts valide ; 9 tests Node réussis sur purge, échec stockage, double soumission, transaction annulée, mode hors ligne et absence de cache privé |
| Déploiement | Aucune erreur ; W021 preload conservé et documenté |
| Dépendances | Aucun avis connu après correction ; `pip check` OK |

Les premiers essais du nouveau script Edge ont échoué sur des sélecteurs trop génériques ; ils ont été corrigés avant validation. Le premier test de déploiement traitait W021 comme bloquant : il vérifie maintenant explicitement cet avertissement assumé. Deux assertions Python recherchant littéralement un ancien sélecteur JavaScript ont été remplacées par des tests Node exécutant réellement le gestionnaire de cache, y compris les chemins comptables. La relance intermédiaire devenue obsolète a été interrompue puis reprise avec ces tests. Aucune de ces exécutions intermédiaires n'a été présentée comme réussie.

## 10. Risques résiduels et recommandations avant déploiement

1. Construire un environnement propre depuis les dépendances validées et refaire les tests sur le système cible. Configurer TLS, hôtes, secrets et proxy de confiance. Ne jamais servir les fichiers privés via une règle générale du serveur web.
2. Utiliser un cache partagé et une limitation au proxy pour les attaques distribuées. `REMOTE_ADDR` derrière un proxy peut représenter le proxy lui-même : régler l'adresse source au niveau d'une infrastructure de confiance, pas depuis un en-tête client arbitraire. Une attaque répartie entre de nombreuses IP ou identifiants reste possible.
3. Tester PostgreSQL et les commandes concurrentes sous charge. SQLite est adapté à cette démonstration locale, pas une validation du verrouillage en production. Définir l'expiration métier des réservations de stock impayées ; ce comportement n'a pas été changé sans procédure explicite.
4. Clarifier le moment d'acceptation du prix : le panier contient déjà un instantané serveur et le checkout le reprend. L'audit n'a pas changé cette politique ni les montants acceptés. Une politique de revalidation des anciens paniers nécessite une décision métier.
5. Vérifier les fournisseurs de paiement en sandbox officielle, le proxy, les tailles de requêtes et le traitement des erreurs avant activation réelle. Ne pas réactiver des intégrations historiques uniquement parce qu'une fonction existe.
6. Servir les médias publics depuis une origine dédiée, limiter les téléversements au proxy et prévoir une revue non destructive des anciens fichiers. Les avatars existants peuvent conserver des métadonnées ; prévoir une politique de confidentialité pour de futurs uploads si nécessaire.
7. Planifier sauvegardes/restaurations, rétention des preuves et journaux, accès administratifs minimaux, surveillance des dépendances. La purge de preuves doit être décidée et exécutée par l'exploitant, pas automatiquement par cet audit.
8. Étudier une CSP avec nonces après inventaire des scripts et ressources. La CSP minimale n'est pas une certification anti-XSS.
9. Le cache hors ligne est une donnée locale au navigateur. Le scénario nominal de purge passe ; la synchronisation multi-onglets concurrente, les pannes de stockage et les appareils partagés exigent une politique et des essais supplémentaires. Une erreur de stockage ne doit pas empêcher la déconnexion serveur. Le service worker conserve sa portée existante `/static/` : celle-ci ne contrôle pas les navigations à la racine dans la configuration locale actuelle. Le test Edge vérifie l'installation réelle ; les tests Node exercent ses gestionnaires de requêtes. La page de secours est anonyme et générique, sans restitution des pages privées. L'élargissement de la portée et le parcours hors ligne complet sont hors de cette correction de sécurité.
10. L'audit ne constitue ni un pentest exhaustif, ni une preuve de conformité juridique, ni une garantie d'absence de vulnérabilité.

## 11. Démonstration pédagogique

Sur des comptes et données de démonstration uniquement :

- Ouvrir le panier, montrer les formulaires POST et le jeton CSRF. GET sur une action authentifiée renvoie 405 sans modifier le panier ; POST sans jeton est refusé.
- Montrer les tests d'un client tentant d'accéder aux objets d'un autre client : 403 ou 404 selon le contrat de la route.
- Montrer le rejet d'une image valide portant une extension `.html`, puis un PNG accepté avec un nom généré. Ne pas charger de fichier hostile sur un environnement partagé.
- Montrer le blocage temporaire de connexion dans les tests à seuil réduit, puis son expiration ; ne pas bloquer un compte réel pour la soutenance.
- Montrer `/orders/livraisons/<id>/preuve/` avec le propriétaire autorisé et un autre client refusé ; la preuve n'a pas d'URL publique sous `/media/`.
- Montrer `/orders/livraisons/tarifs/` : proposition livreur, décision administrative, prix de commande conservé.
- Montrer `/dashboard/security/` désactivé par défaut et les tests de suspension toujours actifs.
- Montrer la suite de tests et expliquer pourquoi le contrôle de déploiement conserve W021.

## 12. Questions possibles du jury EUTG

**Pourquoi un bouton masqué ne suffit-il pas ?** Le navigateur est contrôlé par l'utilisateur. Une requête peut être construite manuellement ; la vue et le service doivent vérifier le rôle et le propriétaire.

**Pourquoi POST et CSRF ensemble ?** POST évite les mutations par simple lecture ; le jeton CSRF vérifie que la requête de modification provient d'un contexte autorisé. POST seul n'est pas une protection CSRF.

**Pourquoi Pillow.verify ne suffit-il pas ?** Il vérifie une structure d'image mais ne garantit pas le nom, le type HTTP de service ou l'absence de données ajoutées. Le format réel, l'extension et le réencodage complètent la protection.

**Comment empêcher une manipulation du prix ?** Le serveur calcule à partir des valeurs enregistrées et vérifie le devis signé ; un montant envoyé par le navigateur ne fait pas autorité.

**Une signature tactile garantit-elle l'identité ?** Non. Elle documente une remise avec le livreur, la livraison et l'heure. L'autorisation, la traçabilité et le processus métier apportent du contexte ; ce n'est pas une signature électronique qualifiée.

**Un retour de paiement réussi suffit-il ?** Non. L'état est confirmé auprès du fournisseur côté serveur, lié à la bonne transaction et au bon montant, avec traitement idempotent.

**Pourquoi ne pas activer HTTPS en développement ?** Le serveur local HTTP serait rendu inutilisable. Le profil de production est distinct et testé séparément.

**Pourquoi 667 tests ne signifient-ils pas “totalement sécurisé” ?** Ils vérifient les cas définis, pas tous les états, fournisseurs et déploiements possibles. La sécurité exige aussi configuration, exploitation, mises à jour et audits réguliers.

## 13. Traçabilité Git

Commits locaux regroupés par corrections applicatives, téléversements et configuration/dépendances, puis rapport. Les tests associés sont versionnés avec les corrections. Les SHA exacts sont présentés dans le bilan final et peuvent être retrouvés avec `git log --oneline audit/securite-soutenance-hamza`. Aucun push, merge, déploiement ou workflow GitHub Actions.


| Commit de correction | Objet |
| --- | --- |
| `65aa728` | Actions authentifiées, limites des requêtes, caches privés, Live Security et tests associés |
| `ce96e7c` | Normalisation des téléversements publics et tests |
| `8a2275e` | Dépendances corrigées, profil de production séparé et tests |

Le présent rapport fait l'objet d'un commit documentaire distinct. Ensemble : 41 fichiers liés à l'audit ; `config/settings.py` reste hors commit.
