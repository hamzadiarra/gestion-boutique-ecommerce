# Comptes financiers, phase 2

Le CA et les charges restent dans leurs registres existants. Les liquidites sont
calculees par devise : solde initial + entrees - sorties, comptes inactifs inclus.
Aucun taux de change implicite. FCFA et XOF sont normalises en FCFA.

## Demarrage et historique

La migration 0004 contient uniquement du schema. Configurer les comptes, leurs
soldes d'ouverture et un compte actif par defaut par moyen (carte -> banque).
Ne pas inclure dans le solde initial les operations nouvelles qui seront ensuite
regularisees, sinon elles seraient comptees deux fois. La reprise historique
necessitera un outil explicite avec date de coupure et controles de doublons.

Les anciennes ventes et paiements deja payes ne sont pas repris lors d'un simple
save. Les creations et transitions futures passent par les services financiers.
Ne pas utiliser bulk_create ou QuerySet.update pour les transitions metier : ces
API contournent les hooks Django. La validation des depenses appelle explicitement
le service dans sa transaction conditionnelle existante.

## Exceptions visibles

- Aucun compte compatible : mouvement non affecte, visible dans Regularisations.
- Paiement sans date de paiement : non affecte, correction metier prealable.
- Paiement gratuit (montant zero) : aucune variation monetaire, aucun mouvement.
- Annulation d'une depense historique sans sortie : entree non affectee et bloquee
  jusqu'a reprise historique ; ne jamais crediter un compte sans la sortie initiale.
- Annulation avec compte initial inactif : contrepassation non affectee ; reactiver
  le compte initial avant regularisation. Ne pas utiliser un nouveau compte defaut.
- Depense et contrepassation non affectees : affectation ensemble au meme compte.
- Commande payee puis annulee : entree conservee, aucun remboursement automatique.

## Integrite

Montants Decimal positifs, references generees avec ID, contraintes DB sur sources
et doublons. Mouvements et transferts sans modification/suppression UI, modeles et
QuerySets immuables. Affectation reservee au service atomique audite. Aucun modele
financier enregistre dans Django Admin. Les soldes initiaux utilises sont verrouilles
par validation modele et verrou de compte, corrections par ajustement motive.

Transfert : deux jambes et audit dans la meme transaction. Jetons signes par
utilisateur/type pour les formulaires de transfert/ajustement, unicite DB pour
rejouer sans doublon. SQLite utilise des reprises limitees sur conflit de verrou,
avec reponse 409 invitant a reessayer quand le conflit persiste.

## Securite et limites

Comptable/admin/superuser seulement. POST + CSRF pour les mutations, pages no-store,
prefixe /dashboard/comptable/ deja exclu du Service Worker, aucune donnee financiere
dans le payload offline ou IndexedDB. CSV BOM et protection des formules.

Restent en phase suivante : rapprochement, solde physique, clotures, reprise
historique, avoirs/remboursements et comptabilite generale. Le test visuel responsive
et le test Chrome Offline reel restent manuels.
