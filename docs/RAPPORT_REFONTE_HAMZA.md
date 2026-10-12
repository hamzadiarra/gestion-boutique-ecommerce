# Rapport de refonte — Gestion Boutique de Hamza

Projet académique de soutenance EUTG. Réalisation du 12 octobre 2026.
Branche : `feat/gestion-boutique-refonte-v2`, issue de `master`.

## 1. Présentation générale

Gestion Boutique est une application de commerce électronique et de gestion interne. Le client consulte le catalogue, prépare son panier, commande et suit sa livraison. Les vendeurs, comptables, livreurs et administrateurs disposent de parcours distincts. Cette intervention modernise l'expérience sur la structure existante ; elle ne reconstruit pas l'application.

L'objectif pédagogique est d'expliquer le lien entre interface, règles métier, base de données et sécurité, avec des résultats reproductibles. Aucun produit de démonstration n'a été injecté dans la base existante. Les produits et comptes des tests appartiennent exclusivement à des bases temporaires.

## 2. Architecture Django existante

L'environnement vérifié utilise Python 3.12.10 et Django 5.2.7. Le commentaire historique de `settings.py` mentionne Django 6.0.7 ; il ne reflète pas la version exécutée. Les dépendances sont déclarées dans `requirements.txt`.

| Application | Responsabilité existante |
| --- | --- |
| `core` | Accueil, assistant boutique, synchronisation hors connexion, langues |
| `accounts` | Authentification, inscription, profil, photo, rôles |
| `products`, `categories` | Catalogue, promotions, stock, favoris, catégories |
| `cart` | Articles, quantités et sous-total du panier |
| `orders` | Commandes, adresses, parcours de livraison et historique |
| `payments` | Paiements, références, confirmations et intégrations prestataires |
| `reviews`, `notifications` | Avis et notifications |
| `dashboard` | Ventes, clients, finances, dépenses, clôtures, administration |

`config/urls.py` assemble les routes. Les templates sont dans `templates/`, les assets dans `static/`. Bootstrap 5.3.7 et Bootstrap Icons 1.11.3 étaient déjà chargés. Crispy Bootstrap 5, django-filter, Unfold et WhiteNoise sont conservés. SQLite est la configuration locale par défaut ; `DATABASE_URL` permet une autre base, notamment PostgreSQL.

Les principaux modèles existants comprennent `Profile`, `Product`, `Category`, `Wishlist`, `Cart`, `CartItem`, `Order`, `OrderItem`, `Payment`, les modèles de livraison, et les modèles de ventes/finances. Les montants utilisent des champs décimaux.

## 3. Audit et problèmes rencontrés

Aucun `AGENTS.md` n'a été trouvé dans le projet ni dans les répertoires parents examinés. La branche initiale était `master`. Une modification non commitée existait dans `config/settings.py` : un double espace après `import`. Elle est conservée dans le fichier de travail et exclue des commits de refonte.

L'audit a relevé un catalogue sans autocomplétion, un comptage des produits inactifs dans les catégories, des filtres de prix fondés sur le tarif ordinaire malgré une promotion, une page de catégorie sans les mêmes filtres que le catalogue, et un message de résultat vide qui pouvait ne pas apparaître. Le CSS contenait plusieurs générations de règles ; les corrections sont regroupées dans un complément ciblé pour limiter les risques.

Les tests visuels ont également montré des champs de livraison affichant `None` et une bulle d'assistance susceptible de recouvrir un champ sur mobile.

## 4. Modifications réellement réalisées

| Domaine | Déjà existant | Ajout ou amélioration |
| --- | --- | --- |
| Navigation | Header Bootstrap, liens par rôle, menus, thème | Hamburger renforcé, hauteur sticky mesurée, accessibilité, menu mobile défilable |
| Accueil | Photo, titre, boutons, couleurs bleu/violet | Suppression des deux mentions demandées, mouvement horizontal de la seule courbe |
| Catalogue | Produits réels, filtres, tri, pagination | Recherche approchée, bornes de prix réelles, promotions dans tri/filtres, compteurs actifs |
| Catégories | Liste et détails | Recherche, tri, filtres et pagination partagés avec le catalogue |
| Panier/commande | Calculs et cinq étapes | Résumé sticky adaptatif, amélioration des champs et du petit écran |
| Inscription | Trois étapes et validateurs serveur | Quatre niveaux colorés, critères plus précis, retour accessible |
| Sécurité | Rôles et journal d'activité métier | Événements de connexion, alertes, revue, suspensions temporaires et audit |
| Retour | Liens spécifiques sur certaines pages | Composant commun, historique navigateur et URL de secours sûre |

La liste exhaustive des fichiers et les résultats finaux figurent dans `validation/RESULTATS_REFONTE.md`.

## 5. Header Bootstrap 5

Bootstrap n'a pas été remplacé ni chargé une deuxième fois. La navigation existante conserve logo, recherche, accueil, boutique, catégories et accès conditionnels au panier, commandes, favoris et espaces professionnels. Un lien Live Security est ajouté au menu des administrateurs et superutilisateurs.

Le header utilise `position: sticky`, une position supérieure explicite et un niveau d'empilement cohérent. Un `ResizeObserver` mesure sa hauteur : les récapitulatifs se placent dessous, même lorsque le contenu du header varie. Sous 1200 px, le hamburger possède une surface d'au moins 44 × 44 px et ne dépend pas d'une couleur implicite. Le menu ouvert peut défiler dans la hauteur disponible. Les rôles et les contrôles Django restent déterminants ; masquer un lien ne constitue jamais une autorisation serveur.

## 6. Responsive universel

Les règles couvrent conteneurs fluides, largeur minimale des enfants de grille, formulaires, cartes, images, récapitulatifs et footer. Sur écran large, la largeur utile est augmentée tout en gardant des marges. Sur petit écran, les filtres s'empilent et les champs restent accessibles.

Les largeurs 320, 375, 390, 768, 1024, 1280 et 1920 px sont vérifiées dans Edge piloté par Playwright : pages publiques, inscription, panier, checkout, commandes et supervision. Le test vérifie l'absence de débordement de la page, la visibilité du hamburger, le header après défilement et la navigation de bureau.

Ces essais de dimensions ne remplacent pas des tests sur appareils physiques Android/iPhone, claviers virtuels et Safari iOS. Cette distinction doit être annoncée au jury. Captures : `validation/home-390.png`, `validation/home-1280.png`, `validation/checkout-390.png`.

## 7. Refonte de l'accueil

Le texte « La sélection du moment » placé au-dessus du titre et le badge « Coup de cœur » avec son éclair ont été retirés du template. Le titre principal, la photographie, les boutons « Découvrir les produits » et « Voir les catégories », ainsi que le bleu/violet sont conservés.

La photographie n'a pas été remplacée. Les apparitions animées des titres et boutons ont été neutralisées afin de laisser ces éléments fixes et immédiatement lisibles. Les sections de produits continuent d'utiliser la base Django et les catégories actives.

## 8. Animation horizontale du hero

La forme seule se déplace de 14 px sur une durée de neuf secondes, en alternance douce. Elle ne reçoit aucun événement de pointeur et reste derrière le contenu. Le conteneur masque ses débords sans faire défiler la page horizontalement. Sur mobile, la hauteur de la forme suit le bloc de texte afin de conserver un fond lisible derrière les boutons.

L'animation utilise une transformation CSS, sans boucle JavaScript par image. `prefers-reduced-motion` désactive le mouvement. Les mesures de taille utilisent `ResizeObserver` ; elles ne déplacent pas les boutons.

## 9. Recherche intelligente

L'endpoint public `/products/autocomplete/` propose au maximum huit produits à partir de deux caractères. Le navigateur attend 250 ms après une saisie, annule la requête précédente et ignore les réponses devenues obsolètes. Chaque suggestion indique nom, image produit autorisée si disponible, prix effectif en FCFA, stock et lien vers la fiche.

La recherche partielle couvre les noms français/anglais, la marque et la description. Si aucune correspondance directe n'est trouvée, une comparaison normalisée sans accents et insensible à la casse tolère certaines fautes de frappe. La comparaison porte sur au maximum 400 produits éligibles : le coût est borné, mais les fautes ne sont pas corrigées exhaustivement dans un grand catalogue. Ce mécanisme est une recherche approchée explicable, pas un modèle d'IA.

Les produits inactifs et ceux des catégories inactives sont exclus. Les résultats ne sont pas mis en cache afin de limiter l'affichage d'informations périmées. Les suggestions utilisent `textContent` plutôt qu'une insertion de HTML issu des noms. Les flèches, Entrée et Échap sont prises en charge ; un état accessible annonce les résultats et les erreurs réseau. Aucun produit fictif n'est utilisé par l'endpoint.

## 10. Catégories, prix et filtres

Une sélection de catégorie restreint le jeu de produits avant le calcul des bornes et des disponibilités. Les minimum et maximum proviennent d'agrégats sur le prix effectif. La promotion, lorsqu'elle est utilisée par les règles existantes, est prise en compte dans le filtrage et le tri. Les valeurs non finies, négatives ou hors limite sont écartées.

Les bornes représentent la sélection catégorie/recherche avant l'application du filtre de prix ; le nombre de résultats correspond au filtrage final. Changer de catégorie réinitialise prix et disponibilité, puis soumet le formulaire. Ce fonctionnement est un rechargement serveur cohérent, pas une mise à jour AJAX complète du catalogue. La pagination conserve les paramètres. Les catégories comptent uniquement leurs produits actifs et une sélection vide affiche un message.

## 11. Panier et commandes

Le panier et le checkout conservent leur structure. À partir de 992 px, articles ou formulaire restent à gauche et résumé à droite. Le résumé est sticky sous le header ; s'il dépasse la hauteur utile, il possède son propre défilement. Sur mobile, il revient dans le flux normal après le formulaire.

Les cinq étapes Livraison, Mode, Récapitulatif, Paiement, Confirmation sont conservées. Aucun calcul serveur de commande, frais de livraison, paiement ou confirmation n'a été modifié. Les champs facultatifs n'affichent plus `None`. Sur petit écran, l'assistant est placé après le contenu du checkout, afin de ne pas masquer un champ.

Le composant Retour utilise l'historique lorsque le précédent document est du même site et une destination locale de secours autrement. Le lien peut conserver catégorie, recherche et page dans sa query string. Le retour spécifique au panier du checkout est conservé sans ajout d'un second bouton global.

## 12. Inscription et robustesse du mot de passe

Les trois étapes existantes restent en place. L'indicateur comporte quatre barres et un texte : rouge « Très faible », jaune « Moyen ou insuffisant », vert « Bon », bleu « Robuste ».

Le calcul tient compte de la longueur, de la diversité des caractères, des répétitions, de motifs courants et des informations personnelles renseignées. Un mot de passe long et varié obtient un niveau supérieur ; une suite prévisible est pénalisée. Il s'agit d'une estimation locale, sans envoi du mot de passe vers un service extérieur, sans dictionnaire exhaustif de mots de passe compromis.

Le navigateur informe ; les validateurs Django décident côté serveur. Le système existant de hachage Django est conservé. Aucun mot de passe en clair n'est enregistré par la refonte.

## 13. Live Security

La page `/dashboard/security/` est réservée au rôle administrateur et aux superutilisateurs actifs. Le simple attribut `is_staff` ne suffit pas. Les autres utilisateurs et visiteurs reçoivent un refus côté serveur.

Le journal enregistre connexions réussies, déconnexions, échecs, consultations d'alertes et décisions administratives. À partir de cinq échecs corrélés en quinze minutes, une alerte invite à examiner le contexte. Une alerte ne suspend jamais automatiquement un compte : un oubli de mot de passe, une adresse partagée ou une tentative visant un tiers peuvent expliquer ces échecs.

Avant suspension, le même administrateur doit avoir examiné une alerte liée au compte dans les dernières 24 heures. Un motif de 5 à 500 caractères et une durée parmi 1 h, 6 h, 24 h, 3 jours ou 7 jours sont obligatoires. L'alerte ne peut pas être réutilisée pour une nouvelle suspension. Les comptes administratifs sont protégés depuis cet espace.

La suspension bloque l'authentification et ferme les sessions Django du compte. Un middleware contrôle aussi les requêtes authentifiées. L'expiration lève le blocage sans tâche planifiée ; les anciennes sessions restent fermées. La réactivation manuelle exige un motif et produit un événement d'audit. Elle ne réactive pas un compte désactivé par un autre mécanisme.

La page montre au maximum 100 sessions non expirées, sans leurs clés. Cela ne prouve pas qu'un utilisateur soit actuellement devant son écran. L'actualisation de page se fait toutes les 30 secondes, peut être mise en pause et s'interrompt pendant la saisie d'un formulaire. Aucun WebSocket ni suivi des écrans n'est implémenté.

## 14. Sécurité et confidentialité des données

Les actions administratives utilisent POST et CSRF. Les transactions, le verrouillage de l'utilisateur et une contrainte d'unicité empêchent les états contradictoires de suspension. Les identifiants de corrélation réseau/utilisateur sont des HMAC ; les adresses IP brutes, mots de passe et clés de session ne figurent pas dans les événements affichés.

Les réponses de supervision portent `no-store` et cette route est exclue du cache du service worker. L'inscription et la connexion expliquent la journalisation. La commande `python manage.py purge_security_events` simule la purge des événements de connexion de plus de 90 jours. `--execute` réalise la suppression ; les événements référencés par une suspension et les décisions administratives sont conservés. Cette purge n'est pas planifiée automatiquement. La durée de conservation des audits administratifs reste à définir selon la politique de l'établissement.

Le module ne capture aucun écran et ne journalise pas la simple navigation. Un futur partage d'écran nécessiterait un consentement explicite, une durée et une révocation ; il n'est pas développé ici. Le journal applicatif est auditable mais pas inviolable face à un opérateur ayant accès à la base.

## 15. Tests exécutés

La suite initiale comptait 573 tests et a réussi avant la refonte. Des tests supplémentaires couvrent suggestions, fautes, prix promotionnels, catégories, requêtes bornées, valeurs invalides, permissions, CSRF, suspensions, expiration, réactivation, sessions, purge et navigation.

Les commandes et bilans finaux sont consignés dans `validation/RESULTATS_REFONTE.md`. Les tests utilisent une base Django isolée. Le navigateur emploie exclusivement des fixtures de test. Les intégrations de paiement réel, SMTP réel, Safari iOS et PostgreSQL réel ne sont pas certifiées par ces tests. Les parcours de paiement existants sont vérifiés dans la suite avec leur configuration de test, sans transaction financière réelle.

Les échecs intermédiaires ont été conservés dans le bilan : fonctionnalités initialement absentes, page 500 sans contexte de requête, langue de test non isolée et problèmes du dispositif Playwright. Ils ne doivent pas être présentés comme des fonctionnalités finales en échec lorsqu'une nouvelle exécution valide leur correction.

## 16. Difficultés et solutions

- **CSS historique cumulatif** : ajout d'un fichier de corrections ciblées, sans remplacement global du thème.
- **Courbe mobile et boutons** : hauteur mesurée sur le contenu et animation limitée à la forme.
- **Page 500 sans request** : le tag Retour accepte l'absence de requête, avec test de régression.
- **PostgreSQL et verrouillage** : retrait d'une jointure externe du `select_for_update`, relevée par la revue indépendante. La validation sur un serveur PostgreSQL reste à effectuer.
- **Playwright** : son Chromium embarqué était absent ; Edge installé a permis les vérifications. Les sessions de test sont créées avant la boucle Playwright pour respecter les contraintes synchrones de Django.
- **Langue des tests** : le rendu direct de la page 500 fixe explicitement la langue afin de ne pas dépendre du test précédent.
- **Champ absent** : `default_if_none` affiche une valeur vide, sans changer les règles de commande.
- **Modification locale de settings** : les ajouts de sécurité sont commités séparément de l'espace préexistant.

## 17. Fonctionnalités partielles et perspectives

Les fonctionnalités demandées ont été mises en œuvre dans l'architecture existante, avec les limites suivantes :

1. Recherche approchée limitée à 400 candidats ; envisager un index spécialisé ou PostgreSQL trigram pour un grand catalogue.
2. Supervision par rafraîchissement, sessions non expirées et événements de connexion ; pas de présence temps réel fine ni de détection antifraude exhaustive.
3. Audit administratif conservé sans durée automatique, purge des connexions à exécuter par l'exploitation.
4. Tests physiques Android/iPhone, Safari, PostgreSQL et prestataires réels à organiser.
5. Réaliser un audit complet du cache hors connexion historique et une politique de conservation à l'échelle de toute l'application.
6. Revoir à grande échelle le scan des sessions lors d'une suspension et ajouter une limitation des tentatives au niveau du reverse proxy si l'exposition publique le nécessite.
7. Compléter les traductions des nouveaux textes français, notamment l'espace sécurité et l'indicateur de mot de passe.
8. Partage d'écran volontaire : perspective seulement, aucune surveillance ajoutée.

La migration de sécurité est livrée mais n'a pas été appliquée à la base existante. Son application dans l'environnement de démonstration est nécessaire avant d'utiliser les nouveaux modèles.

## 18. Questions possibles du jury EUTG

- Pourquoi conserver Django et Bootstrap ?
- Pourquoi une recherche avec une faute retrouve-t-elle un produit ?
- D'où proviennent les prix et les bornes des filtres ?
- Pourquoi le résumé reste-t-il visible sans recouvrir les champs ?
- Une alerte signifie-t-elle qu'un client est malveillant ?
- Peut-on accéder à Live Security en devinant son URL ?
- Que devient une session après une suspension puis une réactivation ?
- Le niveau « Robuste » garantit-il la sécurité du mot de passe ?
- Quels tests ont été exécutés et que ne prouvent-ils pas ?
- Qu'avez-vous réellement ajouté par rapport à l'existant ?

## 19. Réponses pédagogiques

**Architecture.** Conserver le projet limite les régressions et réutilise des règles métier éprouvées. Bootstrap est déjà intégré ; une seconde bibliothèque aurait augmenté la complexité.

**Recherche.** On essaie d'abord la correspondance partielle, puis une comparaison de chaînes normalisées. Les résultats viennent toujours des modèles Django publics ; l'algorithme n'invente pas de produit.

**Prix.** Les agrégats et tris utilisent les prix enregistrés, en intégrant les promotions selon la règle existante. Le navigateur affiche ; le serveur demeure responsable des calculs transactionnels.

**Sticky.** CSS maintient le résumé sous la hauteur mesurée du header. Sur mobile, il revient dans le flux normal. La forme du hero est le seul élément animé de ce bloc.

**Alertes.** Plusieurs échecs justifient une vérification, pas une sanction automatique. Une revue récente et un motif sont exigés avant la décision humaine.

**Permissions.** Le contrôle Django refuse la page et ses actions à un utilisateur non autorisé, même si l'URL est connue. CSRF protège les actions de formulaire.

**Sessions.** La suspension supprime les sessions existantes et interdit une nouvelle authentification. La réactivation autorise une nouvelle connexion ; elle ne restaure pas les anciens cookies de session.

**Mot de passe.** La barre est une estimation pédagogique ; elle ne remplace ni les validateurs serveur, ni le hachage, ni l'unicité du secret.

**Tests.** Les assertions métier prouvent des comportements précis dans une configuration isolée. Le navigateur contrôle des dimensions et interactions. Aucun de ces résultats ne prouve à lui seul une compatibilité avec tous les appareils et prestataires.

**Travail ajouté.** Présenter le tableau de la section 4 et les commits, en distinguant les écrans déjà présents des modifications apportées.

## 20. Démonstration de 5 à 10 minutes

**Préparation locale.** Utiliser une base de démonstration connue, vérifier `DATABASE_URL` et sauvegarder toute base utile. Ne pas lancer ces opérations sur une base de production. Installer les dépendances du projet si nécessaire, puis :

```powershell
python manage.py check
python manage.py migrate
python manage.py runserver
```

La migration `accounts/0006` ajoute les tables de sécurité. Employer des comptes locaux de démonstration déjà autorisés ; `python manage.py createsuperuser` est possible sur cette seule base. Les produits de présentation doivent être de vrais enregistrements de cette base.

**0–1 minute.** Présenter l'architecture et les rôles. Afficher l'accueil, le titre et la courbe ; passer en largeur 390 px et ouvrir le hamburger.

**1–3 minutes.** Rechercher un produit existant avec un fragment puis une faute simple. Montrer le prix réel et ouvrir la fiche au clavier. Revenir, sélectionner une catégorie, expliquer les bornes et la pagination.

**3–5 minutes.** Montrer le panier puis les cinq étapes. Faire défiler un panier long sur ordinateur ; afficher la disposition mobile. Ne pas déclencher un paiement réel pendant la soutenance.

**5–6 minutes.** Ouvrir l'inscription et expliquer les quatre couleurs du mot de passe, en rappelant le contrôle serveur.

**6–8 minutes.** Avec un compte local de test, provoquer cinq erreurs de connexion. Dans un autre navigateur administrateur, consulter Live Security, examiner l'alerte puis expliquer qu'elle ne prouve pas une fraude. Suspendre temporairement ce seul compte de démonstration avec un motif. Vérifier le refus, puis réactiver et montrer l'audit.

**8–10 minutes.** Présenter les résultats de tests, les captures, les commits et les limites annoncées. Terminer par une perspective mesurable : index de recherche, appareils réels ou politique d'archivage.

Commandes de validation reproductibles :

```powershell
python manage.py test --noinput
python manage.py makemigrations --check --dry-run
node --check static/js/refonte.js
node --check static/js/security.js
python manage.py test tools.validate_refonte_browser --noinput
```

Le dernier test exige Playwright et Edge. Pour Chrome installé : `$env:PLAYWRIGHT_CHANNEL = "chrome"`. Le navigateur de test bloque le service worker pour isoler le rendu ; le fonctionnement hors connexion complet n'est pas validé par cette matrice. Aucun push, merge ou GitHub Actions n'a été utilisé.
