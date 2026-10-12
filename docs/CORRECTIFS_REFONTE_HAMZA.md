# Correctifs de la refonte — 12 octobre 2026

Branche : `feat/gestion-boutique-refonte-v2`. Base auditée : `ecd0344` ;
commits antérieurs `a429719` et `9878a4f` présents. Aucun AGENTS.md trouvé.
La modification locale préexistante de `config/settings.py` a été conservée et
exclue des commits. Aucune migration ni donnée de démonstration appliquée à la
base réelle. Aucun push, déploiement ou workflow GitHub Actions.

## Constats et corrections réelles

- **Accueil** : le badge « Coup de cœur » et son éclair étaient déjà absents du
  template. Le badge photo restant était « Sélection vérifiée » : il est supprimé,
  avec les styles et animations inutilisés des anciens badges. Les anciennes
  entrées de traduction ne génèrent aucun élément HTML et sont conservées.
  Photo, titre, boutons et courbe animée restent en place ; l'ancien surtitre
  n'est pas recréé.
- **Inscription** : le vert était déjà atteignable selon les seuils existants,
  ce que le navigateur a confirmé. La barre passe de 4 à 8 px et une légende
  numérotée montre les quatre niveaux. Le jaune porte exactement « Moyen ».
  Les indications textuelles, la couleur et les attributs ARIA restent synchronisés.
  Modifier le prénom, le nom ou l'e-mail recalcule désormais l'indicateur : une
  valeur devenue prévisible ne conserve plus une ancienne appréciation positive.
  Les validateurs Django et le traitement des mots de passe côté serveur restent inchangés.
- **Live Security** : la route, la vue, le template, les ressources et le lien du
  menu de compte existaient. Un bouton visible est ajouté au tableau de bord
  effectivement utilisé, `admin_dashboard_v2.html`. Les permissions restent
  contrôlées côté serveur. Examen, suspension motivée et réactivation sont testés.
- **Catégories** : comparaison avec `16f3504`, avant refonte. Les photos n'avaient
  pas changé dans Git ; une surcharge CSS avait remplacé leur cadrage `cover`
  par `contain`. Le cadrage initial, le fil d'Ariane, la description de secours
  et le singulier/pluriel sont rétablis. L'héritage du catalogue conserve recherche,
  filtres, prix dynamiques et pagination. Les images téléversées dans les médias
  ne sont pas versionnées : Git ne permet pas de récupérer une ancienne photo
  éventuellement remplacée dans la base ou le stockage.
- **Cache** : version du service worker portée à `v4-corrections` pour renouveler
  le cache des ressources. Sa politique de cache n'est pas modifiée.

## Quatre exemples pour vérifier l'indicateur

Ces valeurs sont des exemples publics de test, pas des mots de passe à utiliser.
Avec prénom « Amina », nom « Diallo » et une adresse ne figurant pas dans les valeurs :

| Exemple | Niveau | Couleur |
| --- | --- | --- |
| `abc` | 1 — Très faible | Rouge |
| `abcdefgh2` | 2 — Moyen | Jaune |
| `MyVaried482!` | 3 — Bon | Vert |
| `Unique-Secret-482!Long` | 4 — Robuste | Bleu |

Les seuils sont conservés : 8 caractères et 2 types pour le niveau 2 ;
10 caractères et 3 types pour le niveau 3 ; 14 caractères et 3 types, ou
20 caractères et 2 types, pour le niveau 4. Les types sont minuscules,
majuscules, chiffres et autres caractères. Les valeurs reconnues prévisibles
sont ramenées au niveau 1. Ce score est une aide, pas une garantie de sécurité
ni un remplacement des validateurs Django.

## Validation exécutée

- `python -B manage.py check` : aucun problème.
- `python -B manage.py test --noinput --parallel 4` : **598 tests réussis**.
- `python -B manage.py test tools.validate_ui_corrections accounts.test_security products.test_refonte --noinput` : **25 tests réussis**,
  dont 4 scénarios navigateur. Les tests Django ciblés sont aussi inclus dans les 598 ; ne pas additionner ces nombres comme des tests distincts.
- `python -B manage.py test tools.validate_refonte_browser --noinput` : **1 scénario réussi**, couvrant **70 combinaisons** de pages et de largeurs
  (320, 375, 390, 768, 1024, 1280 et 1920 px), navigation, recherche, panier,
  commande en cinq étapes, récapitulatif sticky et réduction des animations.
- `node --check` : syntaxe valide pour le script d'inscription extrait en mémoire,
  le service worker, `security.js` et `refonte.js`.
- `git diff --check` : aucune erreur d'espacement.
- Captures inspectées : accueil, quatre couleurs, catégories et Live Security.
  Le test ciblé écrit ses captures dans `%TEMP%/gestion-boutique-ui-corrections`.
  Le test historique accepte `BROWSER_SCREENSHOT_DIR` pour éviter de remplacer
  les captures déjà versionnées ; cette option a été utilisée.

Les tests avant correction ont reproduit le badge, le mauvais cadrage, le lien
absent, le libellé jaune et le défaut de recalcul après modification de l'e-mail.
Un sélecteur de test a été ajusté pour cliquer le libellé du bouton radio de genre.
Aucun échec ne subsiste après correction. Les tests utilisent Edge installé et
Playwright ; Android est émulé via le profil Pixel 5, pas testé sur un téléphone
physique. Les service workers sont bloqués dans les tests navigateur : la mise à
jour réelle d'un ancien cache installé n'a pas été testée. Les feuilles de style
et scripts CDN nécessitent un accès réseau pour reproduire ces vérifications.

## Migration nécessaire sur la base actuelle

La consultation `python -B manage.py showmigrations accounts --plan` indique :
`[ ] accounts.0006_securityevent_accountsuspension_and_more`.
La route existe mais la base actuelle ne dispose donc pas encore des tables
nécessaires au fonctionnement complet de Live Security.

Avant toute application manuelle : identifier la base configurée, effectuer une
sauvegarde restaurable et vérifier celle-ci. Pour SQLite, arrêter tous les processus
qui écrivent puis utiliser une sauvegarde SQLite cohérente ; pour PostgreSQL,
utiliser les outils de sauvegarde adaptés, par exemple `pg_dump`. Conserver la
sauvegarde hors du dépôt. Valider d'abord l'opération sur une copie de la base.
Après ces précautions, l'opérateur pourra exécuter :

```powershell
python manage.py migrate accounts 0006
python manage.py showmigrations accounts
python manage.py runserver
```

Cette migration n'a pas été exécutée sur la base réelle durant les corrections.
Avec un compte administrateur autorisé, ouvrir le tableau de bord puis le bouton
**Live Security**, ou `/dashboard/security/`. Vérifier aussi `/`, `/categories/`
et `/accounts/register/`. Recharger la page après activation du nouveau service
worker si un ancien affichage persiste. Aucun compte administrateur ni fausse
alerte n'a été créé dans la base réelle.

## Fichiers du correctif

- `templates/home.html`
- `templates/accounts/register.html`
- `templates/dashboard/admin_dashboard_v2.html`
- `templates/categories/category_detail.html`
- `static/css/style.css`
- `static/css/refonte.css`
- `static/service-worker.js`
- `accounts/test_security.py`
- `tools/validate_ui_corrections.py`
- `tools/validate_refonte_browser.py`
- `docs/CORRECTIFS_REFONTE_HAMZA.md`
