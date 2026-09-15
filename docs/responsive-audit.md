# Audit responsive — Gestion Boutique

## Périmètre

Audit statique de `templates/`, `static/css/style.css`, `static/css/admin.css` et `static/css/delivery.css`. La logique Django, les modèles, les migrations et les services métier n'ont pas été modifiés.

## Corrections

| Page / zone | Risque repéré | Correction |
|---|---|---|
| Header / profil | navigation et menu pouvant dépasser | marque bornée, menu replié, dropdown limité au viewport et défilement vertical |
| Accueil / catalogue | grilles et hero trop larges | grilles fluides, cartes mono-colonne sous 480 px, hero et actions empilés |
| Fiche produit | image et informations compressées | colonne unique mobile, image fluide, achat empilé |
| Panier / commandes | actions et résumé serrés | cartes fluides, résumé sous le contenu, actions sur largeur disponible |
| Checkout / paiement | champs et cartes radio compressés | formulaire mono-colonne sous 768 px, options de paiement mono-colonne sur petit écran |
| Compte / inscription | grilles nom, naissance et informations | champs empilés sur mobile, actions pleine largeur |
| Vendeur | KPI, vente comptoir, actions | KPI mono-colonne mobile, formulaire de vente empilé, boutons tactiles |
| Comptable | KPI, filtres, graphiques et tableaux | colonnes fluides, graphiques bornés, tableaux défilables dans leur conteneur |
| Livraison / discussion | actions et messages trop serrés | actions mono-colonne, textes cassables, formulaire pleine largeur |
| Paramètres boutique | formulaires et logo | grilles mono-colonne, logo borné, boutons fluides |
| Admin Unfold | tableaux et formulaires larges | tableaux contenus dans un wrapper défilable, formulaires repliés |
| Images / textes | longues références et médias | `max-width: 100%`, `overflow-wrap: anywhere`, `min-width: 0` |

## Breakpoints

- `max-width: 900px` : layouts vendeur et paramètres passent en colonne.
- `max-width: 767.98px` : règles mobile globales, formulaires, KPI, actions, header et tableaux.
- `max-width: 600px` : densité vendeur et éditeur produit réduite.
- `max-width: 575.98px` : footer et marque compacts.
- `max-width: 480px` : catalogue, filtres et cartes en colonne.
- `max-width: 390px` : densité spécifique aux écrans 320–390 px, titres et espacements réduits.

## Matrice de tailles

Les règles sont basées sur des seuils de viewport et couvrent 320, 360, 375, 390, 393, 412, 430, 600, 768, 820, 1024, 1280, 1366, 1440, 1600 et 1920 px. Les contrôles visuels automatisés n'ont pas pu être exécutés dans cet environnement : aucun navigateur pilotable n'était disponible.

## Validation

- `python manage.py check` : OK.
- `python manage.py makemigrations --check --dry-run` : `No changes detected`.
- Suite applicative précédente après les changements fonctionnels : 507 tests OK.
- Les modifications de cette mission sont CSS uniquement, sans changement de logique ou de schéma.
