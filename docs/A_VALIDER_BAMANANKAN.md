# Bamanankan - validation humaine

## Motif de la liste

Le projet Anw Kalan n'est pas présent dans les emplacements locaux accessibles.
Les modèles publics trouvés en ligne ne constituent pas, à eux seuls, une
source linguistique validée pour injecter des libellés d'interface. Aucune
nouvelle traduction n'est donc ajoutée automatiquement à `django.po`.

## Traductions préexistantes à revoir

Ces entrées existaient déjà dans Gestion Boutique. Elles sont conservées, mais
ne sont pas considérées comme confirmées par Anw Kalan :

- Téléphone -> Tɛlɛfɔni
- Paiement -> Wari sara
- Produit -> Fɛn
- Produits -> Fɛnw
- Fermer -> Datugu
- Retour -> Segin
- produit -> Fɛn
- Total -> Bɛɛ
- Prix -> Sɔngɔ
- Rechercher -> Ɲini
- Quantité -> Hakɛ
- Envoyer -> Ci

Pour chacune, valider le sens, le registre, la casse et l'orthographe avec un
locuteur Bamanankan avant réactivation publique.

## Navigation et actions

- Accueil
- Retour
- Continuer
- Fermer
- Annuler
- Enregistrer
- Modifier
- Supprimer
- Confirmer
- Valider
- Rechercher
- Envoyer
- Voir
- Profil
- Notifications

## Compte et authentification

- Connexion
- Déconnexion
- Créer un compte
- Nom
- Prénom
- Mot de passe
- Adresse e-mail
- Téléphone
- Adresse
- Ville
- Langue

## E-commerce

- Produit / Produits
- Catégorie
- Catalogue
- Prix
- Quantité
- Stock
- Panier
- Commande
- Paiement
- Livraison
- Client
- Vendeur
- Livreur
- Reçu
- Facture
- Adresse de livraison
- Rue
- Porte
- Repère

## Comptabilité

À ne pas injecter sans validation spécialisée :

- Comptable
- Encaissement
- Dépense
- Compte financier
- Mouvement financier
- Transfert
- Ajustement
- Régularisation
- Clôture
- Solde théorique
- Solde constaté
- Écart
- Trésorerie
- Chiffre d'affaires

## Données exclues

Les noms, adresses, repères, messages, commentaires, références, montants,
téléphones et emails restent des données métier et ne doivent pas être
traduits automatiquement.
