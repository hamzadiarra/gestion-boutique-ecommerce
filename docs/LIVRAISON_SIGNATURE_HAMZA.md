# Livraison, signature et tarification — Hamza

## Audit et périmètre
Le module `orders` possédait déjà Order, Livraison, HistoriqueLivraison,
MessageLivraison, LectureLivraison, les affectations, le suivi livreur et les
permissions client/livreur/vendeur/admin. Ils sont réutilisés sans reconstruction.
Le checkout calculait côté serveur standard = 0 et express = 2 500 FCFA.
Aucune source de distance fiable ni grille personnalisée n’existait.
Aucun AGENTS.md trouvé dans le projet et ses répertoires parents inspectés.

Branche de départ : `feat/gestion-boutique-refonte-v2`, commit `90bae1a`.
Branche de travail : `feat/livraison-preuve-tarification`.
La modification préexistante de `config/settings.py` est préservée et exclue des
commits. Exécution avec Python 3.12 et Django 5.2.7 (le .venv voisin contient
Django 6.0.7 et n’est pas utilisé pour les validations finales).

## Architecture et modèles
- `orders/proof_models.py` : PreuveLivraison, DemandeDerogation,
  RetourLivraison et AccesPreuve.
- `orders/proof_services.py` : validation PNG, confirmation, demandes/décisions
  exceptionnelles, retours clients. Réutilise `operation_atomique` et le verrou
  commande puis livraison du module existant.
- `orders/pricing_models.py` : TarifLivreur et HistoriqueTarif.
- `orders/pricing_services.py` : propositions, décisions, devis signés et calcul.
- `orders/proof_views.py` / `proof_forms.py` : routes privées et validation HTTP.
- `orders/models.py` : référence facultative au tarif et protection du montant
  accepté, contrôle de preuve lors du passage d’une commande physique à livrée.

PreuveLivraison a une relation OneToOne avec Livraison : une seule preuve de
remise. Elle conserve le livreur, l’heure serveur, le réceptionnaire, le PNG
normalisé et son SHA-256, l’échéance et la date d’effacement. Une preuve
exceptionnelle identifie l’administrateur et la demande motivée, sans image.
Les historiques réutilisent TraceModel et interdisent les modifications usuelles.
Les contraintes SQL renforcent unicité, états et note entre 1 et 5.

## Signature mobile et stockage privé
Le destinataire utilise le canvas sur le téléphone du livreur affecté. Pointer
Events gère souris, stylet et toucher ; `touch-action: none` empêche le défilement
pendant le tracé. Le bouton Effacer vide le canvas ; aucun brouillon n’est stocké
dans localStorage. Le livreur renseigne le nom du réceptionnaire. La notice
explique la finalité, la conservation et l’accès ; sa confirmation est requise.

Seul un PNG base64 est accepté. Maximum : 128 Kio décodés, enveloppe texte
180 000 caractères, dimensions de 160×80 à 1200×600. Pillow décode et réencode
l’image, élimine les métadonnées, refuse les animations, données illisibles et
signatures vides ou trop petites. La vérification serveur est indépendante du JS.
Cette validation détecte un tracé, pas l’identité biométrique du signataire.

Le PNG est un BinaryField en base : aucun fichier sous MEDIA_ROOT, aucune URL
publique ou clé d’objet. Image, preuve, statut, dates, historique et notifications
sont enregistrés dans une transaction. Une erreur annule l’ensemble. La clé
unique et le verrou empêchent deux remises concurrentes ; un second envoi renvoie
un conflit sans écraser la première preuve. Les services SQLite réessaient les
verrous temporaires ; PostgreSQL utilise également les verrous de lignes.

## Processus de livraison
Parcours réutilisé : à affecter → affectée → acceptée → en préparation/prête →
en route → arrivée → **attente de signature** → livrée et confirmée.
Les seuls nouveaux codes sont `attente_signature` et `contestee`.
`en_route` représente « en cours » ; `arrive` représente l’arrivée chez le client.
Les états d’échec et d’annulation restent disponibles selon les droits existants.
Le passage direct à `livree` par l’ancienne action est interdit.

Le vendeur prépare et affecte, le livreur affecté assure les transitions terrain.
La confirmation de remise ne valide ni paiement ni stock une seconde fois.
Les anciennes commandes physiques expédiées sans Livraison sont initialisées
lorsqu’un vendeur tente leur remise, puis dirigées vers le parcours de preuve.
Les commandes déjà livrées avant cette fonctionnalité ne reçoivent pas de preuve
inventée. Les commandes non physiques restent soumises à leur parcours antérieur.

### Dérogation exceptionnelle
1. Le livreur atteint attente de signature et expose le motif d’impossibilité
   (10 à 1000 caractères), avec le nom du réceptionnaire.
2. L’administrateur consulte la demande depuis Preuves et confirmations,
   vérifie la remise par un moyen approprié et renseigne un motif de décision.
3. Le refus conserve l’état en attente. L’accord confirme atomiquement une remise
   explicitement exceptionnelle ; aucune fausse signature n’est créée.
4. Une réaffectation invalide automatiquement la demande encore en attente de
   l’ancien livreur. Le nouveau livreur peut déposer sa propre demande.

Une seule demande peut être en attente par livraison. Une décision traitée ne
peut pas être rejouée. Les refus et décisions sont conservés jusqu’à l’échéance
applicable aux données privées.

## Confirmation client et avis
Le client retrouve ses commandes via Mes commandes puis Suivi & discussion.
Il peut confirmer une remise enregistrée, donner une note facultative de 1 à 5,
et écrire jusqu’à 1000 caractères. Il peut signaler un problème à partir de la
mise en route, y compris après une première confirmation. Une explication d’au
moins 10 caractères est requise pour une réclamation.

Un retour de chaque type est autorisé par livraison. Les envois répétés sont
refusés et les retours ne sont pas écrasés. Un problème fait passer la livraison
à `contestee` et notifie les participants sans exposer le commentaire dans la
notification. Le statut commercial et les écritures financières ne sont pas
réécrits par une réclamation. Le contrôle du propriétaire est exécuté côté serveur.
Les actions impossibles sont masquées dans l’interface et toujours refusées par
les services en cas d’appel HTTP direct.

## Tarifs, devis et conservation du prix
Le livreur propose un montant standard ou express et éventuellement une ville.
La zone est normalisée (espaces et casse) ; vide signifie toutes les villes.
La grille correspond à un ensemble d’offres immuables. L’administrateur approuve,
refuse ou désactive avec motif. Chaque action conserve auteur et heure.
Un changement de montant exige une nouvelle proposition : les refus et tarifs
désactivés ne sont pas réactivés silencieusement.

Au checkout, après la saisie de la ville et du mode, le client peut consulter les
offres approuvées et en choisir une. Seuls les livreurs actifs ayant toujours le
rôle livreur peuvent proposer des offres visibles. Les tarifs boutique historiques
restent le choix par défaut pour préserver le parcours existant.

Le serveur émet un devis signé de 30 minutes liant utilisateur, offre, montant,
mode et ville. À la confirmation, il vérifie signature, échéance, disponibilité et
zone, puis utilise le montant de la base, jamais une somme envoyée par le navigateur.
Une offre retirée ou un devis invalide provoque un conflit, sans vider le panier
ni décrémenter le stock. Le client doit choisir et accepter un nouveau devis.

Order conserve `frais_livraison` et `tarif_livraison_id`. Toute modification
ultérieure via save ou l’administration est bloquée ; les nouvelles approbations
ne recalculent pas les anciennes commandes ni leurs paiements. Aucun mécanisme de
correction financière implicite n’est introduit. L’affectation opérationnelle
reste celle du vendeur : changer de livreur ne change pas le montant accepté.
La tarification par distance reste absente faute de source serveur fiable.

## Administration, permissions et sécurité
| Acteur | Droits ajoutés |
| --- | --- |
| Client propriétaire | Confirmation, problème, note, commentaire, consultation privée de sa signature |
| Livreur affecté | Capture de signature et demande de dérogation ; pas de relecture du PNG après dépôt |
| Livreur | Proposer ses tarifs, consulter leur historique |
| Vendeur | Affectation et suivi existants ; pas d’approbation de tarif/dérogation ni d’accès PNG |
| Administrateur actif / superutilisateur | Supervision, preuves, demandes, décisions tarifaires |
| Autre compte ou visiteur | Aucun accès aux preuves d’autrui |

L’espace de supervision filtre tous les statuts, présente preuves, avis,
contestations et demandes exceptionnelles. Il relie les tarifs proposés/approuvés.
Il est accessible depuis le tableau de bord administrateur et les pages livraison.
Les pages de tarifs sont aussi accessibles depuis Mes livraisons.

Les mutations sont exclusivement POST avec CSRF. Les preuves et pages privées
sont `no-store`; la réponse image est `nosniff`, avec CSP restrictive. Chaque accès
réussi au PNG crée AccesPreuve. Nom et image ne sont jamais intégrés aux notifications.
La possession d’un identifiant de livraison n’accorde aucun droit.

## Conservation
`DELIVERY_PROOF_RETENTION_DAYS` est configurable dans les settings ou dans
l’environnement du processus, 365 jours par défaut. Chaque preuve reçoit son
échéance à la création. Modifier la durée ne réécrit pas les preuves existantes.
L’accès au PNG est refusé après échéance, même avant la purge physique.

Prévisualiser : `python manage.py purge_delivery_proofs`

Exécuter explicitement : `python manage.py purge_delivery_proofs --apply`

La purge retire PNG, empreinte, réceptionnaire et motifs des preuves expirées.
Elle retire aussi les données privées des demandes refusées/abandonnées sans
preuve finale, à partir de leur date de création ; les demandes périmées encore
en attente sont fermées. Références, acteurs et chronologie opérationnelle restent.
La purge est à planifier par l’exploitant ; aucun ordonnanceur ni GitHub Actions
n’est ajouté. Les sauvegardes doivent suivre leur propre politique de conservation.

## Migration et mise en service
Migration additive : `orders/0006_delivery_proof_and_pricing.py`, dépendant de
`orders.0005`. Elle crée les six nouveaux modèles, ajoute la référence tarifaire
facultative à Order et étend la contrainte de statuts. Aucun utilisateur ni montant
historique n’est transformé, aucune migration fake, aucun mot de passe réinitialisé.

Avant application sur une autre base : vérifier l’environnement, sauvegarder avec
l’API SQLite backup (ou l’outil du moteur utilisé), vérifier l’intégrité et le plan.
Puis appliquer `python manage.py migrate orders` uniquement sur la base autorisée.
En cas d’échec, arrêter et examiner l’erreur ; ne pas supprimer la base et ne pas
simuler l’application. Utiliser HTTPS lors du déploiement et protéger l’accès à la
base/ses sauvegardes. Ce travail n’effectue aucun déploiement de production.

## Vérifications
Commandes de référence avec l’interpréteur Django 5.2 :

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
python manage.py test tools.validate_delivery_proof_browser --noinput
```

Les tests couvrent PNG valide/vide/malformé/surdimensionné, notice, absence de
preuve, doublon et concurrence, accès privé et journalisé, CSRF, dérogation et
réaffectation, ancienne commande physique, avis/confirmation/contestation et IDOR,
purge prévisualisée/réelle, approbation et montant invalide, devis falsifié ou lié
à une autre ville/personne, stock/panier en cas d’erreur et prix accepté conservé.

La migration a été exécutée avec succès sur une copie temporaire de la base :
données antérieures conservées sur 37 tables hors sqlite_sequence, 15 utilisateurs,
intégrité et clés étrangères valides. La source est restée identique octet pour
octet pendant cet essai ; la copie de test a été retirée ensuite.

Les deux tests Edge sans fenêtre visible couvrent canvas ordinateur, vues Pixel 5
et iPhone 13 émulées, refus d’une signature vide, absence de débordement horizontal,
choix d’offre au checkout, devis transmis et total final. L’émulation iPhone utilise
Chromium, pas Safari réel ; les gestes mobiles sont des Pointer Events synthétiques.
Les appareils réels restent à valider. Ces tests utilisent une base distincte.

## Limites et questions du jury EUTG
- **Pourquoi un canvas ?** Il permet au destinataire de signer sur le téléphone du
  livreur sans installer une application. Ce n’est pas une signature électronique
  qualifiée ni une preuve biométrique d’identité.
- **Pourquoi la base plutôt qu’un fichier public ?** Elle permet l’atomicité entre
  image et confirmation ; aucun chemin média public ne contourne les permissions.
  Pour un volume important, envisager un stockage privé externe et sa coordination.
- **Pourquoi une transaction ?** Pour éviter une commande livrée sans preuve ou
  deux remises concurrentes. Les paiements et le stock ne sont pas recalculés.
- **Et si le client ne peut pas signer ?** Demande motivée, vérification et décision
  administrative, trace exceptionnelle identifiable, aucune image inventée.
- **Qui peut contester ?** Le propriétaire connecté, même après confirmation.
  La réclamation bloque le cycle logistique ; l’examen/remboursement reste manuel
  dans les procédures de la boutique, aucun remboursement automatique n’est ajouté.
- **Pourquoi figer le tarif ?** Le prix accepté doit rester indépendant des grilles
  futures. Une correction financière demande une procédure distincte à définir.
- **Et sans réseau ?** La confirmation attend une connexion ; aucune preuve hors
  ligne ni géolocalisation automatique n’est annoncée.
- **Quelles limites de sécurité ?** Les comptes administrateurs et l’accès direct
  à la base restent de confiance. Une image peut être imitée ; le SHA-256 assure
  une empreinte technique, pas une vérification d’identité. Les sauvegardes ne sont
  pas chiffrées par cette fonctionnalité. PostgreSQL et appareils réels non testés.

## Revue et décisions d’implémentation
Revue indépendante en lecture seule : trois problèmes relevés et reproduits par
des tests en échec, puis corrigés : ancienne commande sans Livraison, demandes
abandonnées hors purge, demande pendante après réaffectation.
Choix documentés : extension du module existant ; stockage binaire transactionnel ;
tarifs par ville et mode uniquement ; tarifs boutique conservés par défaut ;
aucun recalcul après réaffectation ; résolution financière des litiges manuelle.

## Mise en service locale réalisée le 12 octobre 2026
Une fois les tests ciblés, les essais navigateur et la migration sur copie validés,
une sauvegarde fraîche de la SQLite locale a été créée et contrôlée :
`C:/Users/hamza/gestion-boutique-backups/db-before-delivery-proof-20261012T170755748239Z.sqlite3`.

SHA-256 : `f1b5d1e2bfac7df270a78061ed130998e8b02a4119c5b504c9255cf8b096cc03`.

Seule `orders.0006_delivery_proof_and_pricing` a été appliquée à la base de
`gestion-boutique-ecommerce/db.sqlite3`, après assertions SQLite, DEBUG et chemin
absolu attendu. Aucune opération en production. Les 37 tables antérieures hors
sqlite_sequence conservent leurs lignes ; seules les métadonnées attendues
(migration, types de contenu et permissions des nouveaux modèles) s’ajoutent.
Les 15 utilisateurs sont conservés, intégrité et clés étrangères valides,
aucune migration en attente.

Contrôle après migration : supervision, tarifs, liste des livraisons et Live
Security répondent HTTP 200. Ce contrôle utilisait un compte temporaire dans une
transaction entièrement annulée, sans conserver de données de test.

## Fichiers de cette livraison
- `dashboard/vendeur_views.py`
- `docs/LIVRAISON_SIGNATURE_HAMZA.md`
- `orders/admin.py`
- `orders/delivery_models.py`
- `orders/delivery_services.py`
- `orders/delivery_views.py`
- `orders/management/__init__.py`
- `orders/management/commands/__init__.py`
- `orders/management/commands/purge_delivery_proofs.py`
- `orders/migrations/0006_delivery_proof_and_pricing.py`
- `orders/models.py`
- `orders/pricing_models.py`
- `orders/pricing_services.py`
- `orders/proof_forms.py`
- `orders/proof_models.py`
- `orders/proof_services.py`
- `orders/proof_views.py`
- `orders/test_delivery.py`
- `orders/test_delivery_pricing.py`
- `orders/test_delivery_proof.py`
- `orders/urls.py`
- `orders/views.py`
- `static/js/delivery-pricing.js`
- `static/js/delivery-signature.js`
- `templates/dashboard/admin_dashboard_v2.html`
- `templates/orders/checkout.html`
- `templates/orders/delivery/_pagination_proof.html`
- `templates/orders/delivery/_proof.html`
- `templates/orders/delivery/base.html`
- `templates/orders/delivery/detail.html`
- `templates/orders/delivery/supervision.html`
- `templates/orders/delivery/tarifs.html`
- `tools/validate_delivery_proof_browser.py`

## Résultats finaux des vérifications
- `python manage.py check` : aucune erreur (0 problème).
- `python manage.py makemigrations --check --dry-run` : aucun changement détecté.
- `python manage.py test --noinput` : **618 tests réussis**, 456,208 secondes.
- `python manage.py test tools.validate_delivery_proof_browser --noinput` :
  **2 tests réussis**, 18,874 secondes, couvrant les trois formats d’écran et le checkout.
- Après le dernier ajustement des choix affichés au client : **20 tests ciblés
  preuve/tarification/concurrence réussis**, 1,933 seconde.
- `git diff --check` : aucune erreur de whitespace.
- Revue : les trois problèmes importants ont des tests de reproduction et sont corrigés.
- Aucun push, aucune fusion, aucune action GitHub Actions, aucune donnée de production touchée.
- Limites restantes : Safari et appareils physiques, moteur PostgreSQL, distance
  et résolution/remboursement des litiges à valider ou traiter séparément.

## Commits
Le commit fonctionnel `7ca2cf3` regroupe modèles, services, routes, interfaces,
migration et tests : `feat(delivery): add private proof, customer feedback and courier pricing`.
Ce guide fait l’objet d’un commit documentaire séparé. La branche reste locale.
