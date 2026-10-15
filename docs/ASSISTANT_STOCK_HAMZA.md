# Assistant : disponibilité réelle — soutenance EUTG

## Audit et règle métier

Le catalogue public filtre `Product.actif=True` et `Category.active=True` (`products/views.py`, fonction `public_products`). La disponibilité utilise `Product.stock > 0`, comme le filtre du catalogue et le panier. `Product.stock` est un entier positif ; zéro signifie rupture. Le checkout verrouille les produits dans une transaction, vérifie les quantités cumulées puis déduit le stock dès la création de la commande. Les ventes au comptoir utilisent le même champ et les annulations admissibles le restaurent. Il ne faut donc jamais soustraire une seconde fois les commandes ou paniers lors d'une consultation.

Aucun modèle de variantes, réservation séparée ni réglage de confidentialité des quantités n'a été trouvé. Les quantités exactes sont déjà affichées publiquement sur les fiches produits. Le seuil d'alerte vendeur ne définit pas la disponibilité à l'achat.

## Architecture et fonctionnement

L'intention locale `STOCK_PRODUIT` complète le moteur existant dans `core/assistant.py`. `core/assistant_stock.py` réutilise ses fonctions de recherche, de sélection des produits publics et de sérialisation. Le moteur du catalogue `products/search.py` demeure inchangé. Aucun appel à une API d'intelligence artificielle, aucune migration, aucune écriture métier.

Les réponses différencient disponible, rupture, introuvable dans le catalogue public, plusieurs correspondances et information non vérifiable. Un produit non publié ou appartenant à une catégorie inactive est traité comme introuvable : révéler son existence serait une fuite d'information. Les liens correspondent aux fiches réellement trouvées. Le stock est relu à chaque demande, y compris lors d'une reprise de requête après erreur réseau.

Les formulations de quantité telles que « Combien en reste-t-il ? » passent avant les règles de prix. Les phrases FR/EN sont normalisées et leurs termes de conversation sont retirés avant la recherche catalogue. Le moteur reste déterministe : il ne comprend pas toutes les formulations possibles.

## Catégories et variantes

Une catégorie active contient des produits disponibles si au moins un de ses produits publiés possède un stock positif. Le compteur est le nombre de produits distincts vendables, et non la somme de leurs unités ni la taille de la liste affichée. Le comptage porte sur toute la catégorie ; la réponse affiche au maximum cinq exemples. Une catégorie sans produit vendable annonce zéro.

Il n'existe pas de stock par taille ou couleur dans ce projet. Une demande de variante reconnue reçoit donc une réponse indiquant que cette disponibilité ne peut pas être vérifiée. Le stock global ne permet jamais d'affirmer qu'une taille 42 est disponible. Aucune gestion de variantes n'a été créée.

## Mémoire et confidentialité

Les identifiants réels et ordonnés des résultats sont conservés dans la mémoire existante. Après « Le deuxième est-il en stock ? », le produit sélectionné reste celui utilisé par « Et combien coûte-t-il ? ». Une référence ambiguë demande une précision. Les produits sont filtrés à nouveau s'ils ont été masqués depuis la recherche. Le contexte de page est vérifié côté serveur par `core/assistant_session.py` ; les identifiants et quantités envoyés par le navigateur ne constituent pas une autorisation.

Les limites existantes de mémoire (quinze minutes, douze échanges), CSRF, limitation des appels et isolation des sessions sont conservées. Les données privées des commandes ne sont pas utilisées pour calculer le stock. Aucun compte ni quantité de la base locale n'est modifié par les validations.

## Démonstration pratique FR/EN

Utiliser des produits publics existants, ou les fixtures synthétiques du script Edge :

1. « Je cherche des chaussures Nike » / « I am looking for Nike shoes ».
2. « Le deuxième est-il en stock ? » / « Is the second in stock? ».
3. « Et combien coûte-t-il ? » / « And how much does it cost? ».
4. « Combien de produits sont en stock dans la catégorie chaussures ? » / « How many products are in stock in the shoes category? ».
5. Depuis une fiche : « Ce produit est-il disponible ? », puis une demande de taille 42. Comparer l'affirmation de stock global et le refus de confirmer une variante non gérée.

Le script de navigateur crée sa propre base de test ; il ne dépend pas de l'existence de chaussures Nike dans la boutique réelle.

## Commandes de validation

```powershell
.\.venv-security\Scripts\python.exe -B manage.py check
.\.venv-security\Scripts\python.exe -B manage.py makemigrations --check --dry-run
.\.venv-security\Scripts\python.exe -B tools/run_security_tests.py
.\.venv-security\Scripts\python.exe -B tools/run_security_tests.py tools.validate_assistant_stock
```

Le runner appelle la suite Django avec `--noinput`, une base de test et des dossiers de fichiers temporaires. Les captures Edge sont enregistrées dans `%TEMP%/gestion-boutique-assistant-stock/`. Les tests du moteur contrôlent également le nombre de requêtes et l'absence de requête d'écriture.

## Limites et questions du jury

**Le stock annoncé est-il réservé ?** Non. C'est une photographie du stock au moment de la lecture. Un autre achat peut intervenir ensuite ; seul le checkout valide effectivement la disponibilité dans sa transaction.

**Pourquoi ne pas compter les commandes en attente ?** Leur quantité est déjà déduite de `Product.stock` à la création de la commande. La soustraire à nouveau rendrait le calcul faux.

**Pourquoi cacher les produits inactifs même à une question précise ?** Le chatbot consulte le catalogue public et ne doit pas permettre de découvrir des produits non publiés.

**Que signifie trois produits disponibles dans une catégorie ?** Trois références ont au moins une unité vendable. Cela ne signifie pas trois unités au total.

**Pourquoi ne pas confirmer une taille ?** Le modèle actuel ne conserve pas cette information. Une réponse honnête indique cette limite plutôt que d'inventer un stock de variante.

**Une panne complète de base peut-elle être masquée ?** Non. L'application utilise aussi la base pour les sessions et les pages. Un message de stock non vérifiable ne garantit pas que tout le site reste utilisable pendant une panne.

**Quelles limites de performance ?** Le comptage utilise SQL et la liste est plafonnée à cinq résultats. Les limites de recherche approximative existantes restent applicables. Le verrou de conversation utilise le cache local ; une exploitation multi-processus nécessite un cache partagé et une validation adaptée.

## Fichiers livrés

- `core/assistant.py` : intention stock, conservation du contexte, reconnaissance des références et protection des intentions de paiement/livraison.
- `core/assistant_stock.py` : consultation seule des produits et catégories publics, réponses de disponibilité.
- `core/test_assistant_stock.py` : 18 tests du moteur, dont limites de requêtes, absence d'écriture et erreurs de lecture.
- `core/test_assistant_stock_endpoint.py` : 3 tests HTTP, mémoire anonyme, stock relu lors d'une reprise, CSRF et données navigateur non fiables.
- `tools/validate_assistant_stock.py` : scénario Edge FR 390 px et EN 1280 px sur données synthétiques.
- Le présent document. Aucun modèle, template, JavaScript, paramètre local ou module Live Security modifié.

Les noms numériques comme « iPhone 7 » restent des noms de produits. Les nombres seuls peuvent sélectionner un résultat ; les demandes portant explicitement sur plusieurs unités ne déclenchent ni réservation ni confirmation de quantité et invitent à préciser la demande. La fonctionnalité vise la consultation du stock courant, pas la simulation complète d'un panier.

## Validation navigateur constatée

Le scénario Edge FR/EN a réussi en 24,777 secondes. Les captures `stock-fr-390.png` et `stock-en-1280.png` ont été examinées. Elles présentent les produits synthétiques Nike Alpha et Nike Beta, un prix promotionnel réel de 15 000 FCFA pour le second et un seul produit vendable dans la catégorie. Le produit masqué est exclu. Les quantités de départ restent inchangées après le scénario. Aucun débordement horizontal ni erreur JavaScript détecté. Un favicon manquant est signalé par le serveur, sans incidence sur le scénario.

Les essais initiaux ont détecté puis permis de corriger une formulation complète de catégorie et une suite de prix en anglais. La revue a ajouté des régressions pour les modèles numériques et les questions de disponibilité des moyens de paiement/livraison. Les tests ne prétendent pas couvrir toutes les formulations ni tous les navigateurs.

## Résultats finaux — 15 octobre 2026

- Référence : **712 tests réussis en 426,783 s**, avant ajout de la fonctionnalité.
- Suite finale complète : **733 tests Django réussis en 424,153 s**, soit 21 tests supplémentaires. Aucun test ignoré ou échec rapporté par le runner.
- Test Edge séparé : **1 scénario réussi**, couvrant français et anglais, en 24,777 s.
- `manage.py check` : aucun problème. `makemigrations --check --dry-run` : aucun changement détecté. `git diff --check` : sans anomalie.
- La première tentative de suite finale a été interrompue volontairement après les défauts trouvés dans Edge ; les résultats ci-dessus proviennent de la relance complète avec les corrections finales.
- Branche : `feat/assistant-stock-availability`. Commit local : `feat(assistant): add real product stock availability` (SHA fourni dans le bilan et disponible avec `git log -1`).
- La modification préexistante de `config/settings.py` est préservée à l'identique et exclue du commit. Aucun push, fusion, déploiement, migration appliquée ou modification de données de production.

Si un serveur local a été démarré avec `--noreload`, le redémarrer pour charger ce nouveau code. Cette livraison n'a pas redémarré ni déployé de service existant.
