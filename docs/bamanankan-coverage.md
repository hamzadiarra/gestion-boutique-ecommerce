# Couverture Bamanankan de Gestion Boutique

## Mesure au 13 septembre 2026

Mesure réalisée avec GNU gettext (`msgattrib`) sur
`locale/bm/LC_MESSAGES/django.po`, hors en-tête du catalogue :

- msgid utilisateur : **1 339**
- msgstr BM non vides : **12**
- msgstr BM vides : **1 327**
- fuzzy : **0**
- obsolètes : **0**
- couverture : **0,9 %**
- traductions provenant d'Anw Kalan : **0**
- nouvelles chaînes injectées pendant cette passe : **0**

Les douze traductions existantes sont listées dans
`docs/bamanankan-glossary.csv` et restent marquées `validated=false` tant
qu'une source linguistique indépendante n'est pas disponible.

## Répartition indicative par domaine

Classification heuristique à partir des références et du texte des msgid.

| Domaine | Chaînes |
| --- | ---: |
| Navigation | 34 |
| Actions communes | 44 |
| Authentification | 60 |
| Profil | 0 |
| Catalogue | 71 |
| Catégorie | 26 |
| Panier | 33 |
| Commande | 83 |
| Paiement | 59 |
| Livraison | 34 |
| Notifications | 7 |
| Vendeur | 81 |
| Comptabilité | 65 |
| Autres | 742 |
| **Total** | **1 339** |

## Ressources évaluées

| Ressource | Constat | Décision |
| --- | --- | --- |
| `djelia/bm-mistral-7b-v1` | Modèle de génération 7,25B, BF16, licence Apache-2.0; accès aux fichiers soumis à conditions. | Non utilisé : modèle lourd et sortie non validée comme corpus UI. |
| `oza75/nllb-600M-mt-french-bambara` | Modèle 0,6B, F32, licence CC-BY-NC-4.0; dépendances Transformers/PyTorch et téléchargement des poids. | Non utilisé : une sortie unique ne suffit pas pour une traduction de production. |
| `oza75/bm-nllb-1.3B` | Fiche/artefacts non vérifiables depuis l'environnement de travail. | Non utilisé; taille/licence/dépendances à confirmer. |
| `sudoping01/nllb-bambara-v2` | Référencé comme modèle MT de MALIBA-AI, mais fiche complète non accessible pour vérifier licence et poids. | Non utilisé jusqu'à audit reproductible. |
| `MALIBA-AI/maliba-framework` | SDK regroupant MT, LLM, ASR, TTS et embeddings; les poids sont téléchargés au premier usage. | Non installé; ce n'est pas un corpus bilingue validé. |
| `MALIBA-AI/bambara-text-normalization` | Outil de normalisation orthographique, licence MIT; utile pour comparer des variantes, pas pour produire une traduction. | Pas exécuté faute de corpus de propositions. |

## Faisabilité machine

Le 600M F32 demanderait environ 2,4 Go rien que pour les poids, plus le
processus et les tenseurs; CPU possible mais lent. Le modèle Mistral 7B BF16
demanderait environ 14,5 Go pour les seuls paramètres, avant les buffers et
le runtime. Aucun modèle n'a été téléchargé automatiquement.

## Décision d'injection

Il n'existe pas de correspondance Anw Kalan locale à comparer. Les modèles
évalués sont des moteurs potentiels, non des preuves linguistiques
convergentes.

- HIGH : 0
- MEDIUM : 0
- LOW / à valider : les 12 traductions préexistantes et tous les termes non traduits
- injection BM : aucune

BM reste archivé et non réactivé dans l'interface active. Une prochaine passe
peut reprendre dès que le dépôt Anw Kalan ou un export de son corpus est rendu
accessible.
