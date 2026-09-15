# Clotures financieres, phase 3

Une cloture est un constat humain, jamais une correction automatique. Aucun
mouvement, transfert ou ajustement n'est cree par creation, validation ou annulation.

Le theorique a date comprend le solde initial et les mouvements affectes au compte
anterieurs au debut local du lendemain. Le fuseau Django est utilise, avec une borne
exclusive pour inclure toutes les fractions de seconde du jour. Decimal et SQL.

Le brouillon conserve un snapshot a sa creation, recalcule a chaque modification.
La validation recalcule une derniere fois selon les mouvements alors connus, puis
fige solde initial, devise, entrees, sorties, nombre de mouvements et ecart. Un ecart
non nul exige un commentaire. Les validations repetees ne recalculent rien.

Une seule cloture validee par compte et date (contrainte DB conditionnelle).
Les brouillons multiples sont permis. L'annulation garde le snapshot et son
validateur et permet une nouvelle validation de remplacement. Aucune suppression.

Comptes inactifs : cloture autorisee pour aujourd'hui ou le passe pour finaliser
l'historique ; proposes apres les actifs et explicitement identifies. Aucun solde
constate futur n'est autorise. Les soldes constates negatifs restent possibles.

Detection retroactive : mouvements dates de la periode mais crees apres validation,
plus comparaison des totaux/nombre/solde initial/devise courants au snapshot pour
detecter notamment l'affectation tardive d'un mouvement ancien. Avertissement sans
blocage financier et sans alteration de l'ancien constat.

Les indicateurs monetaires regroupent uniquement les clotures validees, par devise.
Les ecarts cumules sont des constats de controles successifs, pas une perte ou un
profit et pas necessairement des incidents economiques distincts. Comptes non
clotures : actifs sans cloture validee aujourd'hui. Les brouillons et annulations
ne les considerent pas comme clotures.

Justificatifs : validation et stockage prive reutilises depuis Depense, sous
clotures/justificatifs/YYYY/MM. Telechargement autorise comptable/admin/superuser,
attachment, no-store, nosniff, CSP sandbox. Aucun endpoint offline nouveau.

Le bouton d'ajustement ouvre le workflow existant avec compte, sens, montant et
reference CLO proposes dans le motif. Aucune ecriture sur GET et aucun ajustement
automatique. Le lien est textuel, sans FK ; verifier les ajustements precedents et
les mouvements retroactifs avant d'enregistrer une correction distincte.

Phase 4 : rapprochements/imports operateurs, remboursements/avoirs, comptabilite
generale restent exclus. Audit visuel responsive et vrai test Chrome Offline manuels.
