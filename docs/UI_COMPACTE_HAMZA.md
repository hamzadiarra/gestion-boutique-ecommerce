# Interface compacte et tarifs de livraison — 12 octobre 2026

## Périmètre et audit

Travail direct dans `gestion-boutique-ecommerce`, branche existante
`feat/livraison-preuve-tarification`, après les commits `7ca2cf3` et `46072ee`.
Aucun AGENTS.md trouvé dans le projet ou ses parents inspectés.
Bootstrap 5.3.7, templates Django, `style.css`, `refonte.css`, composants
header/footer, scripts de navigation et de connectivité inspectés.

La modification utilisateur préexistante de `config/settings.py` a été conservée
sans inclusion dans le commit. SHA-256 avant/après :
`493D81EF28C42FDE050606802173C38DFBD38F0D41DA474357EC4531BE50A24D`.
Aucun changement des modèles, des services métier, des migrations, des utilisateurs,
des mots de passe ou de la production pour cette correction. Aucune migration
appliquée à la base de développement pendant cette intervention UI.

## Corrections

- Valeurs partagées `--page-space`, `--section-space`, `--page-gutter`,
  `--page-max` ; espacements adaptatifs et largeur des dashboards harmonisée.
- Suppression des `overflow-x: hidden/clip` du document. Le défilement horizontal
  reste local aux tableaux lorsqu'ils ont besoin de davantage de largeur.
- Réduction des marges cumulées du retour, du titre, des sections de l'accueil,
  des cartes et du footer ; réduction du padding des formulaires.
- Suppression des hauteurs minimales artificielles du checkout, du profil,
  de l'inscription, des dashboards et du hero ; image produit au ratio 4/3.
- Indicateurs sur deux colonnes mobiles. Les grilles secondaires se répartissent
  dans la largeur disponible, sans être écrasées par la règle des grilles principales.
- Graphiques vides compacts ; graphiques remplis conservés et vérifiés.
  Les placeholders portant `hidden` ne sont pas affichés.
- Navigation livraison et comptabilité regroupée dans des panneaux natifs
  `details/summary`, utilisables au clavier et sans JavaScript.
  Tous les liens restent disponibles. La notice de suivi est dépliable en bas.
- Header sticky conservé avec offset calculé existant ; menus mobiles vérifiés.
- Pas de bandeau « En ligne » transitoire à chaque chargement normal. Les
  événements de perte/reprise de connexion et la synchronisation restent actifs.

## Tarifs : fonctionnement et permissions

Le formulaire existait déjà pour les livreurs. L'absence de formulaire dans
l'espace administrateur correspond au mode A : **le livreur propose,
l'administrateur décide**. La session personnelle du navigateur de l'utilisateur
n'était pas attachée à l'outil ; son rôle réel n'a pas été déduit de manière certaine.
Le rôle et le nom du compte sont maintenant affichés dans la page.

| URL exacte | Utilisation et rôle |
| --- | --- |
| `/orders/livraisons/tarifs/` | Livreur actif : consulter ses propositions, proposer ; administrateur/superutilisateur actif : consulter toutes les propositions |
| `/orders/livraisons/tarifs/#proposer-tarif` | Accès direct au formulaire du livreur |
| `/orders/livraisons/tarifs/<id>/decision/` | POST administrateur : approuver, refuser ou désactiver, avec motif |
| `/orders/livraisons/offres/?mode=standard&ville=Bamako` | Offres approuvées pour le checkout d'un utilisateur connecté |
| `/orders/create/` | Checkout : choix du tarif et calcul serveur existants conservés |
| `/orders/livraisons/supervision/` | Suivi des preuves et confirmations, administration |
| `/dashboard/security/` | Live Security, administration |
| `/dashboard/` | Dashboard administrateur |
| `/dashboard/vendeur/` | Dashboard vendeur |
| `/dashboard/livreur/` | Dashboard livreur |
| `/dashboard/comptable/` | Dashboard comptable |

Clients, vendeurs et comptables ne peuvent pas accéder à la gestion des tarifs.
Le bouton « Proposer un tarif » mène au formulaire standard/express, ville exacte
ou toutes les villes, montant FCFA. Les filtres affichent leur état et leurs comptes.
L'historique montre décision, motif, date et administrateur. Les erreurs s'affichent
sur la page en conservant les saisies ; les filtres et la pagination reviennent à
la liste même après une décision invalide.
Les devis signés, contrôles serveur et montants acceptés restent inchangés.
Un seul header et un seul footer ont été constatés dans le navigateur ; aucun
composant n'a été supprimé sur la base d'un texte copié.

## Validation

Python 3.12 / Django 5.2.7. Tests sur bases temporaires exclusivement.

- `python manage.py check` : aucune anomalie.
- `python manage.py makemigrations --check --dry-run` : aucun changement détecté.
- `python manage.py test --noinput` : **624 tests réussis**, 490,948 s.
- `orders.test_delivery_pricing` : **13 tests réussis**, incluant le test ajouté
  après le démarrage de la suite complète. Permissions, création, validation,
  approbation, refus, historique, devis, frais serveur et prix accepté couverts.
- Playwright / Microsoft Edge : **200 vues**, 20 pages × 10 largeurs :
  320, 375, 390, 430, 768, 820, 1024, 1280, 1440, 1920 px.
- Aucun débordement horizontal du document détecté ; réponses 200, header/footer
  uniques, header sticky et ouverture des menus mobiles contrôlés.
- Parcours navigateur de proposition, approbation et refus avec historique réussi ;
  offres peuplées contrôlées aux dix largeurs.
- Graphiques admin/comptable avec ventes fictives : visibles aux dix largeurs.
- Parcours de signature desktop/émulation Android/iPhone et checkout avec tarif
  approuvé : réussis, sans erreur JavaScript dans ces parcours.
- Revue de code effectuée ; erreurs de ciblage des graphiques et de liens après
  validation corrigées puis vérifiées.
- `git diff --check` : aucune erreur de whitespace.

Pages capturées : accueil, boutique, catégories, fiche produit, panier, checkout,
connexion, inscription, profil, commandes, détail livraison, liste livraisons,
tarifs administrateur/livreur, preuves, Live Security et quatre dashboards.

Quelques mesures à 320 px (même contenu de test) :

| Mesure | Avant | Après |
| --- | ---: | ---: |
| Header → titre livraisons | 295 px | 113 px |
| Header → titre comptabilité | 562 px | 145 px |
| Header → titre inscription | 99 px | 79 px |
| Écart main → footer checkout | 96 px | 48 px |

Le checkout conserve le bouton d'assistance dans le flux mobile pour éviter
qu'il recouvre les actions. La hauteur totale d'une page n'est pas un objectif
à minimiser au détriment de son contenu : la page des tarifs contient désormais
une explication, des filtres explicites et un formulaire correctement identifié.

## Captures et reproduction

Captures locales : `%TEMP%/gestion-boutique-compact-ui/before/` et `after/`.
Comparateur : `%TEMP%/gestion-boutique-compact-ui/comparaison.html`.
Mesures : `metrics.json` dans chaque dossier ; `metrics-targeted.json` pour la
revérification finale des dashboards. Captures de décisions tarifaires :
`%TEMP%/gestion-boutique-pricing-audit/`.

```powershell
$env:UI_AUDIT_PHASE='after'
python manage.py test tools.validate_compact_ui tools.validate_pricing_ui tools.validate_delivery_proof_browser --noinput
```

`UI_AUDIT_WIDTHS` permet une liste de largeurs séparées par virgules et
`UI_AUDIT_PAGES` une sélection de pages pour un contrôle ciblé. Sans ces variables,
le contrôle reprend toutes les pages et largeurs. `PLAYWRIGHT_CHANNEL` vaut
`msedge` par défaut. Les captures complètes sont prises à 390 et 1280 px,
et celles des autres largeurs sur un viewport de 900 px de haut.

Limites : données fictives représentatives, pas la session personnelle existante.
Les appareils mobiles sont émulés dans Edge, pas des essais matériels Safari/iOS.
Les captures sont des artefacts temporaires locaux, non publiés et non committés.
Aucun blocage restant identifié sur le périmètre contrôlé.

## Fichiers du correctif

- `static/css/style.css`, `static/css/refonte.css`, `static/css/delivery.css`
- `static/js/offline-manager.js`
- `templates/accounts/login.html`, `templates/accounts/register.html`
- `templates/dashboard/depenses/_navigation.html`
- `templates/orders/delivery/base.html`, `templates/orders/delivery/tarifs.html`,
  `templates/orders/delivery/_pagination_proof.html`
- `orders/proof_forms.py`, `orders/proof_views.py`, `orders/test_delivery_pricing.py`
- `tools/validate_compact_ui.py`, `tools/validate_pricing_ui.py`
- `docs/UI_COMPACTE_HAMZA.md`

Aucun push ni fusion. Les migrations précédentes de livraison sont inchangées.
