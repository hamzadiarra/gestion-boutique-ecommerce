# Livraison V1

## Architecture et reprise

Order reste commercial, Livraison logistique (OneToOne), HistoriqueLivraison trace
les evenements et affectations, MessageLivraison les textes humains. LectureLivraison
conserve le dernier ID lu par participant. Aucun backfill de commandes anciennes.

Checkout existant : standard/express uniquement, pas de retrait. Initialisation
automatique a ce checkout, en attente de confirmation commerciale. Initialisation
manuelle pour anciennes commandes avec adresse+ville et mode standard/express,
non annulees/non livrees. Tout autre mode, dont retrait, est exclu.

Rue/Porte facultatives : entiers 0..1000, formulaire serveur et contraintes DB.
Repere conserve dans code_postal_livraison, expose par Order.repere. Aucune ancienne
adresse modifiee. Rue/Porte sont formatees par Order.rue_porte, y compris la valeur 0.
Telephone : copie au checkout du champ saisi ou du profil, puis snapshot Order.
Anciennes commandes sans telephone : non renseigne, pas de lecture du profil actuel.

## Permissions

Admin/superuser et vendeurs actifs supervisent toutes les commandes, comme dans
l'espace vendeur existant. is_staff seul ne suffit pas. Comptable non participant.
Client proprietaire et livreur actuellement affecte seulement ; une reaffectation
retire immediatement l'acces de l'ancien livreur, meme aux messages historiques.
Les notifications anciennes ne permettent pas de contourner le controle objet.
L'inscription publique reste client ; le role livreur est attribue par l'admin.

## Transitions

a_affecter -> affectee (boutique apres confirmation) -> acceptee (livreur)
-> en_preparation (boutique, facultatif) -> prete (boutique)
-> en_route -> arrive -> livree (livreur affecte).

Acceptee peut passer directement a prete par la boutique. Echec exige un motif ;
Autre exige aussi un commentaire. Echec, livree et annulee sont terminaux en V1.
Nouvelle tentative apres echec differee a V2. Reaffectation possible avant terminal :
retour affectee, dates du nouvel itineraire remises a zero, ancien historique garde.

En route -> Order.expediee ; livree -> Order.livree. Pas d'annulation commerciale
automatique apres echec/annulation logistique. Annulation commerciale -> livraison
non terminale annulee, historique/messages conserves. Anciennes actions vendeur
expedier/livrer dirigent vers le suivi lorsqu'une Livraison existe.

Les mutations logistiques ne changent jamais Payment ni le stock. Aucun encaissement
a la livraison invente. Les notifications Order de depart/livraison sont remplacees
par l'evenement logistique pour ne pas doubler le meme avis.

## Discussion et securite

Texte seul, 1..1000 caracteres, echappement Django, POST/CSRF, aucun changement de
statut depuis le texte. Jeton signe utilisateur/livraison et cle unique pour les
resoumissions, PRG. Pas d'edition/suppression. Chat lecture seule apres terminal.
50 messages par page, ordre chronologique ; page recente par defaut, anciennes pages
accessibles. Ouvrir la discussion marque les messages jusqu'au dernier affiche comme
lus ; la liste ne marque rien. L'auteur n'est pas compte parmi ses propres non-lus.

Notifications internes aux autres participants, sans adresse/telephone ni contenu
du message dans la notification (notamment pour le payload offline existant).
Une seule serie par transition effective ; verrou Order puis Livraison dans les
services, transaction et retries SQLite limites. Conflit persistant : HTTP 409.

Online only : no-store sur les nouvelles vues et commandes clientes ; exclusion
Service Worker des commandes, routes livreur/livraisons et details vendeur. Version
du cache incrementee pour evacuer les anciennes pages. Aucun nouveau store IndexedDB.
Pas de polling, WebSocket, API externe ou geolocalisation.

## Livraison V2, hors perimetre

GPS/cartes/ETA, preuves photo/signature/OTP/QR, SMS/WhatsApp/push, chat multimedia,
temps reel, tournees, optimisation, zones/tarification distance, nouvelle tentative.
Le responsive et Chrome Offline reel necessitent un controle navigateur manuel.
