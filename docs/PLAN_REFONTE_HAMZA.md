# Plan de refonte Gestion Boutique

Objectif : mettre en œuvre le cahier des charges de Hamza (phases 0–13), directement dans le dossier courant, sans reconstruire Django ni modifier les données réelles.
Architecture : conserver Bootstrap 5.3.7, les templates et les applications ; ajouter des modules ciblés de recherche et sécurité. Django, SQLite/PostgreSQL, CSS et JavaScript natif.

## Contraintes
- Conserver la modification initiale de config/settings.py (double espace dans import dj_database_url), exclue des commits.
- Aucun push, merge, GitHub Actions, migration de la base réelle ni appel de paiement réel.
- Prix Decimal et promotions existantes ; comptes et permissions par rôle.
- Tests Django sur base isolée ; responsive aux largeurs 320, 375, 390, 768, 1024, 1280, 1920.

## Exécution directe
1. Audit : applications, routes, modèles, assets, tests initiaux, branche feat/gestion-boutique-refonte-v2.
2. Recherche/catalogue : tests de recherche partielle, fautes, produits inactifs, promotions, catégorie et bornes réelles. Implémenter products/search.py et adapter views.py, catégories, endpoint et formulaire existant. Vérifier puis commit.
3. Interface : conserver navigation et rôles, CSS de refonte isolé, hauteur sticky dynamique, retours avec secours, suppression des deux éléments du hero et animation localisée, autocomplétion accessible, indicateur de mot de passe. Vérifier en navigateur puis commit.
4. Sécurité : tests permissions, revue préalable, motif, suspension/expiration/révocation de session, audit et absence de faux positifs sur navigation. Modèles dans accounts, backend et middleware dédiés ; dashboard réservé admin. Migration créée mais non appliquée à la base réelle. Vérifier puis commit.
5. Validation : suite Django entière, check, migration sans dérive, navigateur avec données temporaires, revue finale et rapport français de soutenance. Commit documentation.

## Points de revue
- Catégories vides/inactives et prix non finis ; pagination conserve les filtres.
- Requêtes autocomplete concurrentes et saisies contenant du HTML ; pas de données privées.
- Petits écrans : hamburger visible, pas de débordement, résumé utilisable.
- Suspension : un simple rôle staff ne suffit pas ; aucun automatisme punitif ; compte administrateur protégé ; contrôle côté serveur.
- Sessions : clés et mots de passe jamais affichés ; journaux limités aux événements utiles, purgables.

## Journal
Audit : aucun AGENTS.md trouvé. Bootstrap 5 déjà chargé. Contrôle Django initial sans erreur. Suite initiale lancée.


## Bilan d'exécution
- Audit et branche : terminés ; 573 tests initiaux réussis.
- Catalogue, autocomplétion et catégories : implémentés et testés.
- Header, accueil, retours, responsive, checkout et inscription : implémentés, vérifiés dans Edge.
- Live Security : implémenté ; migration créée, jamais appliquée à la base existante.
- Revue indépendante : verrouillage PostgreSQL corrigé ; limites documentées.
- Vérification finale : 596 tests Django et un scénario navigateur (70 combinaisons), tous réussis ; contrôles Django, migration et JavaScript réussis.
- Rapport de soutenance et preuves : livrés ; détails dans `validation/RESULTATS_REFONTE.md`.
- Intégration : commits locaux uniquement, conformément à la consigne ; modification préexistante des settings conservée hors commit.
