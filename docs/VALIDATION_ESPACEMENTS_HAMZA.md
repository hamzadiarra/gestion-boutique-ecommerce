# Validation des espacements — Gestion Boutique de Hamza

## 1. Objectif pour la soutenance EUTG

Une interface compacte doit montrer les informations utiles rapidement, sans
rendre les textes difficiles à lire ni réduire excessivement les zones tactiles.
Il ne s'agit donc pas de supprimer toutes les marges. L'objectif est de supprimer
les espaces sans fonction et de conserver une hiérarchie visuelle cohérente.

Le correctif initial est dans le commit `4415ae0`. Cette validation complémentaire
ajoute les scénarios à faible et fort volume de données, les vérifications
techniques fraîches et le présent document. Un défaut supplémentaire est corrigé : l'étirement vertical d'une carte vide
à la hauteur de sa voisine. Le commit précédent n'est pas réécrit.
Branche de travail : `feat/livraison-preuve-tarification`.

## 2. Causes identifiées et corrections

| Cause | Effet visible | Correction |
| --- | --- | --- |
| Marges du retour + padding de page + marge du titre | Contenu repoussé sous le header | Valeurs d'espacement partagées et réduction des marges cumulées |
| `min-height` élevés sur pages et cartes | Zones vides avec peu de données | Hauteurs dépendantes du contenu ; ratio 4/3 pour la photo produit |
| Menus secondaires multiligne avant le titre | Navigation prenant plusieurs écrans sur mobile | Panneaux natifs `details/summary`, liens conservés |
| Grille mobile forcée à une colonne | Dashboard très long malgré de petits indicateurs | Deux colonnes mobiles ; grille secondaire fluide |
| Canvas réservé même sans données | Grand rectangle vide dans le dashboard | État vide compact ; graphique rempli toujours visible |
| Bandeau « En ligne » temporaire au démarrage | Décalage du contenu et du header | Bandeau réservé aux transitions de connectivité et au mode hors ligne |
| Marges du footer ajoutées au padding principal | Double espace en fin de page | Suppression de la marge supplémentaire |
| Alignement `stretch` implicite des grilles à deux colonnes | Carte vide aussi haute que la longue liste voisine | `align-items:start` sur `.control-two-col`, sans hauteur imposée ni contenu supprimé |
| Masquage global du débordement horizontal | Défauts dissimulés | Retrait du masque global ; défilement local des tableaux conservé |

Les variables `--page-space`, `--section-space`, `--page-gutter` et `--page-max`
centralisent les proportions répétées. `clamp()` adapte progressivement les
espacements à la largeur, sans ajouter une règle différente pour chaque téléphone.
Le header reste sticky et les offsets existants restent liés à sa hauteur réelle.

## 3. Pages et volumes testés

Vingt vues sont contrôlées : accueil, boutique, catégories, fiche produit,
connexion, inscription, panier, checkout, profil, mes commandes, détail livraison,
liste livraisons, tarifs administrateur, tarifs livreur, preuves et confirmations,
Live Security et dashboards administrateur, vendeur, livreur et comptable.

Chaque vue est ouverte aux largeurs 320, 375, 390, 430, 768, 820, 1024, 1280,
1440 et 1920 px, dans Microsoft Edge piloté par Playwright.

| Jeu de données isolé | Volume |
| --- | --- |
| Faible volume | 4 produits, 1 catégorie, 1 commande/livraison, 1 ligne de panier ; tarifs et ventes vides |
| Fort volume | 52 produits, 12 catégories, 31 commandes/livraisons, 12 lignes de panier, 30 tarifs, 24 ventes et 66 événements de sécurité |

Les données volumineuses comprennent des titres de produits longs, des descriptions
longues, plusieurs statuts tarifaires et des motifs détaillés. Les listes paginées
présentent une page remplie et une pagination ; cela évite de confondre « beaucoup
de données en base » avec « tout afficher sans limite dans le navigateur ».
Les écrans connexion et inscription ne dépendent pas du volume des commandes.

Les fixtures sont créées dans les bases temporaires Django. Les images sont dans
un répertoire temporaire nettoyé à la fin. Aucun utilisateur, mot de passe ni donnée
réelle n'est modifié. `config/settings.py` conserve sa modification préexistante,
avec le même SHA-256 :
`493D81EF28C42FDE050606802173C38DFBD38F0D41DA474357EC4531BE50A24D`.

## 4. Ce qui est mesuré

Pour chaque vue : statut HTTP, largeur du document, éléments débordants visibles,
unicité du header et du footer, distance du titre au header, distance main/footer,
hauteur du document, position du header après défilement et ouverture du menu mobile.
Les exceptions JavaScript émises par la page sont collectées et font échouer le test.
Un test supplémentaire contrôle les graphiques avec de vraies ventes fictives et
l'ouverture de la navigation comptable aux dix largeurs.

L'alignement en haut supprime la hauteur artificielle de la carte courte ; une
grille à deux colonnes peut conserver de l'espace sous la colonne la plus courte.
Le contenu n'est ni masqué ni inventé pour remplir cet espace.

La hauteur totale n'est pas, seule, une mesure de qualité. Un panier de douze
articles doit être plus long qu'un panier d'un article. Les comparaisons avant/après
ne sont pertinentes qu'à largeur et contenu identiques. Un tableau large peut
avoir son propre défilement horizontal, sans faire déborder toute la page.

## 5. Résultats techniques

- `check` : aucune anomalie.
- `makemigrations --check --dry-run` : aucun changement détecté.
- `test --noinput` : **625 tests réussis**, 518,377 secondes.
- `node --check static/js/offline-manager.js` : code de sortie 0.
- Matrice initiale : **400 combinaisons page/largeur/volume**, toutes accessibles
  (HTTP 200), sans débordement horizontal ni exception JavaScript détectés.
- Captures longues reprises sur les 20 pages à 390 et 1280 px pour chaque volume,
  après défilement réel afin de charger les images paresseuses : essais réussis.
- L'inspection visuelle des données denses a ensuite révélé deux cartes vides
  étirées. Un test de régression a échoué sur les dashboards admin et comptable à
  1440 px avant correction, confirmant le défaut.
- Après correction : **40 contrôles ciblés réussis** (2 dashboards × 10 largeurs
  × 2 volumes), sans carte vide artificiellement étirée. Les graphiques remplis
  et la navigation comptable ont aussi été revérifiés avec succès aux dix largeurs.
- La suite Django complète a précédé cette dernière modification exclusivement
  CSS ; les tests navigateur ciblés vérifient le comportement après la correction.
  `check` et `makemigrations --check --dry-run` ont également été relancés ensuite.
- Revue ciblée en lecture seule : aucun blocage identifié.
- `git diff --check` : aucune erreur de whitespace.

Le JavaScript modifié est `static/js/offline-manager.js`. Sa syntaxe est contrôlée
avec `node --check static/js/offline-manager.js` (Node 24.19.0). Ce contrôle syntaxique
ne remplace pas les essais dans le navigateur.

Environnement Django : Python 3.12, Django 5.2.7. Les commandes demandées sont :

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
node --check static/js/offline-manager.js
```

## 6. Captures et reproduction

Artefacts locaux dans `%TEMP%/gestion-boutique-compact-ui/` :

- `before/` : captures de référence avant le correctif initial.
- `after/` et `comparaison.html` : comparaison initiale à contenu identique.
- `after-sparse/` : nouvelle validation à faible volume.
- `after-dense/` : nouvelle validation à fort volume.
- `before-density-fix/` : dashboards chargés avant correction des cartes étirées.
- `comparaison-dashboards.html` : avant/après de cette dernière correction.
- Chaque nouveau dossier contient `metrics.json`, `fixtures.json` et les PNG.

Les captures sont complètes à 390 et 1280 px ; les autres montrent un viewport
de 900 px de haut. Les captures complètes finales sont prises après un parcours de la page pour
charger les images paresseuses. Les mesures et le test sticky portent sur le document
et le défilement. Les images ne contiennent que des données fictives.

```powershell
$env:UI_AUDIT_PHASE='after'
$env:UI_AUDIT_DENSITY='sparse'
python manage.py test tools.validate_compact_ui --noinput
$env:UI_AUDIT_DENSITY='dense'
python manage.py test tools.validate_compact_ui --noinput
```

Supprimer `UI_AUDIT_PAGES` et `UI_AUDIT_WIDTHS` pour exécuter toute la matrice.
Le canal navigateur est `msedge` par défaut ; `PLAYWRIGHT_CHANNEL` permet de le changer.

## 7. Fichiers concernés

Corrections CSS du commit initial :

- `static/css/style.css` : hauteurs, cartes, grilles, espacements historiques.
- `static/css/refonte.css` : variables partagées, header/contenu, footer, états vides.
- `static/css/delivery.css` : livraisons et présentation des tarifs.

Templates corrigés :

- `templates/accounts/login.html` et `templates/accounts/register.html`.
- `templates/dashboard/depenses/_navigation.html`.
- `templates/orders/delivery/base.html`, `tarifs.html` et `_pagination_proof.html`.

JavaScript corrigé : `static/js/offline-manager.js`.
Le complément courant modifie `static/css/style.css` (alignement des cartes),
`tools/validate_compact_ui.py` (scénarios et contrôles) et ce document.
Les contrôles précédents des tarifs sont dans `tools/validate_pricing_ui.py` et
`orders/test_delivery_pricing.py`. Aucun changement de modèle ni nouvelle migration.

## 8. Limites et questions du jury

Aucune des vingt vues prévues n'a été inaccessible et Microsoft Edge a pu être
lancé. Chrome, Firefox et Safari n'ont pas été exécutés : aucune validation n'est
revendiquée pour ces moteurs. Les tailles mobiles sont émulées dans Edge, pas
sur des appareils Android/iPhone physiques. La session personnelle déjà ouverte
et les données de production ne font pas partie de ces essais.

La matrice couvre les vues et états décrits, pas toutes les combinaisons possibles
ni tous les dialogues. Les contrôles automatiques de débordement ne suffisent pas
à prouver l'absence de tout défaut visuel : le défaut d'étirement a justement été
trouvé lors de l'inspection des captures puis ajouté aux assertions.
Aucun blocage restant identifié après les validations ciblées décrites ci-dessus.

**Pourquoi ne pas utiliser `overflow:hidden` sur toute la page ?**
Cela cache les éléments qui dépassent sans corriger leur largeur. Le problème
peut alors devenir invisible tout en rendant des actions inaccessibles.

**Pourquoi tester avec plusieurs volumes de données ?**
Les écrans vides révèlent les hauteurs artificielles. Les écrans remplis révèlent
les problèmes de retour à la ligne, de tableaux, de listes et de pagination.

**Comment préserver la logique métier ?**
Les corrections d'espacement concernent la présentation. Les modèles, calculs de
prix et services métier restent inchangés. Les tests Django contrôlent les
permissions, transactions et workflows existants ; les tests navigateur contrôlent
leur présentation et les interactions principales.

**Comment prouver le résultat ?**
Présenter les captures à largeur identique, les mesures JSON, les sorties des
commandes de validation et l'historique Git. Distinguer ce qui a été testé de ce
qui reste hors périmètre, plutôt que d'annoncer une absence universelle de défauts.
