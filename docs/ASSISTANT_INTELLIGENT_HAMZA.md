# Assistant local FR/EN — soutenance EUTG

## Architecture et algorithmes

Le moteur existant `core/assistant.py` reste déterministe et local : normalisation, reconnaissance de formulations, pondération des intentions et règles ciblées. Aucune API IA externe ni traduction automatique des noms de produits. `core/views.py` conserve la validation des requêtes, CSRF et limitation des appels ; `core/assistant_session.py` gère le contexte privé. Le JavaScript affiche les réponses comme du texte, jamais comme du HTML fourni par un message.

Les intentions distinguent vouloir payer, refuser de payer, avoir déjà payé et signaler un échec. Dire avoir payé ne valide jamais une transaction. Les formulations ambiguës produisent des demandes de précision ; les questions multiples proposent des suites distinctes. Ce moteur n'offre pas une compréhension générale du langage naturel.

La recherche réutilise `products.search.search_products`, filtre les produits et catégories actifs et conserve les prix, promotions et stocks de la base. Elle limite les recherches à huit termes, cent catégories candidates, quatre cents candidats pour le rapprochement approximatif existant et cinq résultats. La catégorie reste disponible lorsqu'une marque précise la demande. Une référence au deuxième produit utilise son identifiant dans les résultats précédemment affichés ; les données sont relues, jamais inventées. Les noms traduits existants sont utilisés sans génération de traduction.

## Mémoire, navigation et sécurité

La mémoire en session expire après quinze minutes d'inactivité ou douze échanges. Elle conserve uniquement une intention, une étape, une requête de cent caractères, cinq identifiants de produits et les identifiants nécessaires à la sélection. Aucun état envoyé par le navigateur n'est accepté comme mémoire serveur.

Le chemin de la page courante est transmis : accueil, catalogue, fiche produit, panier, checkout ou commandes. Django résout la route et vérifie le produit actif, sa catégorie et le propriétaire d'une commande. Un chemin externe, malformé, inconnu ou privé non autorisé est ignoré. La connaissance d'un identifiant ne donne aucun droit supplémentaire.

Un verrou de trente secondes par session rejette les requêtes simultanées avec HTTP 409. Le dernier identifiant de requête permet une reprise sans ajouter un tour ; sa réutilisation pour une autre question est refusée. Les données catalogue sont recalculées lors d'une reprise. Le verrou et cette reprise utilisent le cache Django : le cache mémoire local convient à la démonstration en un processus. Une exploitation avec plusieurs processus nécessite un cache partagé et des essais de concurrence sur cette architecture. Ce verrou ne couvre pas toutes les écritures effectuées par d'autres vues dans la même session.

La limite existante de soixante appels par minute et la protection CSRF restent actives. Les commandes sont toujours limitées à leur propriétaire. Les liens sont contrôlés côté interface ; l'autorisation finale appartient aux vues Django.

## Interface

Le design existant est conservé. Une seule requête peut être en cours ; les boutons sont temporairement désactivés, un indicateur annonce le chargement, et une erreur réseau permet de reprendre la question. Le délai maximal est de quinze secondes. Les réponses tardives ne doivent pas remplacer une réponse plus récente. L'historique visible est limité à vingt échanges. Échap ferme le panneau et rend le focus à son bouton ; les boutons de suggestion restent utilisables au clavier. Le rendu des prix utilise la langue de l'interface.

## Démonstrations

1. Français : « Je cherche des chaussures », « Nike », « Combien coûte le deuxième ? ». Comparer le résultat au prix réel de la fiche. Le résultat dépend des produits présents, aucun produit fictif n'est ajouté à la base locale.
2. Anglais : « I am looking for shoes », « Nike », « How much is the second? ». Depuis une fiche, demander « What is its price? ».
3. Comparer « Je veux payer », « Je ne veux pas payer », « J'ai déjà payé », « Mon paiement a échoué ».
4. Simuler une interruption réseau dans les outils développeur puis réessayer. Vérifier qu'un seul échange est affiché.
5. Vérifier qu'une commande appartenant à un autre compte n'apparaît jamais.

## Validation reproductible

```powershell
.\.venv-security\Scripts\python.exe -B manage.py check
.\.venv-security\Scripts\python.exe -B manage.py makemigrations --check --dry-run
.\.venv-security\Scripts\python.exe -B tools/run_security_tests.py
.\.venv-security\Scripts\python.exe -B tools/run_security_tests.py tools.validate_assistant_live_security
node --test static/js/tests/*.test.cjs
```

Le runner exécute les tests Django avec `--noinput` et isole les fichiers dans un dossier temporaire. Les tests navigateur utilisent Edge, une base de test et des comptes synthétiques. Largeurs : 320, 390, 768, 1280 et 1920 px, français et anglais. Les captures et métriques se trouvent dans `%TEMP%/gestion-boutique-assistant-live-security/`. Elles montrent des données de test, pas des utilisateurs réels. Aucun modèle ni migration n'a été ajouté.

## Questions possibles du jury

**Est-ce une intelligence artificielle générative ?** Non, c'est un assistant local à intentions et recherche contextuelle. Ses limites sont explicites et il oriente vers le support après plusieurs incompréhensions.

**Comment éviter un faux prix ?** Les résultats et références ordinales relisent les produits actifs en base et utilisent leur prix promotionnel éventuel.

**Un client peut-il demander la commande d'un autre ?** Les requêtes restent filtrées par le propriétaire connecté. Un contexte navigateur n'est jamais une autorisation.

**Pourquoi limiter la mémoire ?** Pour réduire les ambiguïtés, la consommation et la conservation d'informations inutiles. Le contexte expire et les champs persistés sont strictement bornés.

**Les tests prouvent-ils une sécurité absolue ?** Non. Ils démontrent les scénarios couverts. Les expressions inédites, recherches au-delà des limites et déploiements multi-processus nécessitent une validation supplémentaire.

## Résultats constatés le 15 octobre 2026

- Référence avant modifications : 667 tests Django réussis.
- Validation finale : **712 tests Django réussis en 666,945 s**, avec base et fichiers de test isolés.
- `manage.py check` : aucun problème ; `makemigrations --check --dry-run` : aucun changement.
- **21 tests JavaScript réussis** ; syntaxe de `assistant.js` et `security.js` vérifiée.
- **4 scénarios Edge réussis en 84,255 s** : conversations FR/EN, contexte fiche produit, reprise réseau/double envoi, Live Security vide et rempli, suspension/réactivation et refus d'accès client. Largeurs 320, 390, 768, 1280 et 1920 px. Aucun débordement horizontal détecté, header sticky conservé.
- Captures réellement examinées : assistant FR 320, EN 390 et 1920 ; tableau rempli 390, vide 390 et suspension 1280. Le premier essai a révélé un pronom anglais mal interprété et un titre de widget masqué sur mobile ; ils ont été corrigés avant la passe finale.
- Les réponses HTTP 400/403/404 provoquées par les tests de refus sont attendues. Edge signale aussi un favicon manquant, sans incidence fonctionnelle ; ce fichier n'a pas été ajouté dans cette intervention.
- `config/settings.py` est resté strictement inchangé par cette intervention ; sa modification locale antérieure est exclue des commits. Aucun compte réel, migration ou donnée de production modifié.

Les captures restent dans le dossier temporaire local indiqué plus haut. Elles ne sont pas incluses dans Git. Le script versionné permet de les régénérer. Les résultats portent sur Edge et les scénarios décrits, pas sur tous les navigateurs ni tous les comportements possibles.

## Fichiers concernés

`core/assistant.py`, `core/assistant_session.py`, `core/views.py`, `core/test_assistant_conversation.py`, `core/test_assistant_session.py`, `static/js/assistant.js`, `static/js/tests/assistant.test.cjs`, `static/css/style.css`, `templates/base.html` et `tools/validate_assistant_live_security.py`. Le moteur de catalogue `products/search.py` est réutilisé sans modification.
