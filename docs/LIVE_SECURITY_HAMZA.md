# Live Security — démonstration locale

Le module existant est conservé : journal de sécurité, examen des alertes, suspension temporaire, fermeture des sessions et levée de suspension. Il est réservé à un administrateur actif (`profile.role == "admin"`) ou à un superutilisateur actif. Le statut `is_staff` seul ne donne pas accès.

## Activation et arrêt

Le profil de démonstration utilise SQLite, exige `DEBUG=True` et limite les hôtes à la boucle locale. Depuis PowerShell, dans le dépôt :

```powershell
$env:LIVE_SECURITY_ENABLED = "1"
.\.venv-security\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.demo
```

Ouvrir `http://127.0.0.1:8001/dashboard/security/` avec un administrateur. Le lien apparaît uniquement pour les comptes autorisés lorsque le module est activé. Pour le désactiver, arrêter le serveur, définir `$env:LIVE_SECURITY_ENABLED = "0"`, puis le redémarrer. Aucun changement de `config/settings.py` n'est nécessaire.

Le profil `config.production` impose `LIVE_SECURITY_ENABLED=False`. Le prédicat commun refuse aussi le module dès que `DEBUG=False`, même si le drapeau est vrai. Désactiver le tableau de bord ne désactive ni le contrôle des suspensions ni les protections de connexion.

Le serveur utilise la base configurée : effectuer les démonstrations de suspension uniquement avec des comptes synthétiques dans une base locale dédiée. Les tests automatisés ci-dessous créent leur propre base SQLite et isolent les fichiers temporaires ; ils ne suspendent aucun compte réel.

## Parcours de démonstration

1. Afficher le journal avec un administrateur. Le filtre « Alertes uniquement » limite l'affichage ; la pagination conserve ce filtre.
2. Examiner une alerte et confirmer cet examen. L'action crée un événement `alert_reviewed`. Une alerte ne prouve aucune fraude et ne déclenche jamais de sanction automatique.
3. Sélectionner une alerte examinée par cet administrateur dans les dernières 24 heures. Seules les alertes encore utilisables, associées à un compte actif non administratif et sans suspension active, sont proposées.
4. Choisir 1, 6, 24, 72 ou 168 heures et saisir un motif de 5 à 500 caractères sans donnée sensible. La suspension ferme les sessions existantes et bloque les nouvelles connexions.
5. Lever la suspension avec un motif. Une nouvelle connexion est alors nécessaire. Les sessions supprimées ne redeviennent jamais valides.
6. Laisser une suspension expirer : le contrôle d'accès cesse de la considérer active à son échéance, sans tâche planifiée. Une tentative de levée d'une suspension déjà expirée est refusée et ne crée pas de faux audit de réactivation.

Un compte désactivé par ailleurs reste désactivé après levée de suspension. Les administrateurs, superutilisateurs, membres du personnel et le compte de l'opérateur sont protégés contre une nouvelle suspension. Une suspension antérieure peut néanmoins être levée si son titulaire est devenu administrateur entre-temps.

## Données, contrôles et audit

- Les actions sont des requêtes POST avec protection CSRF. Les paramètres GET ne provoquent aucune mutation.
- L'alerte, son titulaire, l'administrateur ayant effectué l'examen et sa fraîcheur sont revérifiés côté serveur. Une même alerte ne peut justifier deux suspensions.
- La suspension et son audit sont enregistrés dans une transaction. Le motif complet reste dans `AccountSuspension.reason` ; le résumé `account_suspended` respecte les 500 caractères et référence la suspension et son échéance.
- Une nouvelle suspension peut fermer l'ancienne ligne expirée pour respecter l'unicité : `revoked_at` prend son échéance et `revoked_by` reste nul. Cette clôture ne prétend pas être une réactivation manuelle.
- Le tableau indique des sessions **non expirées**, pas des personnes actuellement en ligne. Il inspecte au maximum 100 sessions pour l'affichage ; les identifiants malformés sont ignorés et aucune clé de session n'est rendue.
- Aucun écran, contenu de conversation privée, parcours de pages, mot de passe ni jeton n'est capturé. Le journal conserve des événements d'authentification et d'intervention. La corrélation des échecs utilise des empreintes HMAC, pas les adresses sources en clair.
- La page est exclue du cache. Son actualisation de 30 secondes peut être suspendue ; elle s'arrête pendant la saisie et lorsque l'onglet est masqué. JavaScript associe l'alerte sélectionnée au compte, y compris lorsque le navigateur restaure une sélection.

La commande existante `purge_security_events` simule par défaut une purge des événements de connexion de plus de 90 jours. Elle conserve les audits administratifs et les événements référencés par une suspension. L'option `--execute` supprime réellement les éléments éligibles ; aucune purge réelle n'a été exécutée pour cette livraison.

## Vérification

```powershell
.\.venv-security\Scripts\python.exe tools/run_security_tests.py dashboard.test_live_security accounts.test_security -v 1
node --check static/js/security.js
```

Les tests dédiés couvrent les motifs maximaux, l'expiration, les comptes promus ou désactivés, les sessions malformées, la sélection des alertes utilisables, les comptes protégés, POST/CSRF, le maintien du contrôle avec le tableau désactivé, les doublons et la conservation des preuves lors d'une purge de données synthétiques. Aucun modèle, schéma ou fichier de migration n'a été modifié.

Les métriques de validation globale et les vérifications navigateur sont consignées dans le compte rendu final de la livraison.

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

## Cause de désactivation et fichiers concernés

L'audit précédent avait volontairement masqué l'interface derrière un feature flag désactivé par défaut. Il ne manquait pas de migration : `accounts.0006` est déjà appliquée localement. Le profil explicite `config/demo.py` réactive l'interface pour la démonstration, sans changer la configuration normale ni les protections de suspension.

Fichiers : `config/demo.py`, `config/production.py`, `core/security_flags.py`, `core/context_processors.py`, `dashboard/security_views.py`, `static/js/security.js`, `templates/base.html`, `templates/dashboard/admin_dashboard_v2.html`, `templates/dashboard/security.html`, `core/test_demo_security.py`, `dashboard/test_live_security.py`, `accounts/test_security.py`, `core/test_security_hardening.py`. La validation navigateur commune est dans `tools/validate_assistant_live_security.py`.

## Questions possibles du jury et limites

**Pourquoi deux profils ?** La démonstration exige une activation explicite ; la production conserve une désactivation forcée. SQLite, DEBUG et les hôtes locaux sont vérifiés dans le profil de démonstration.

**Une alerte suffit-elle à sanctionner ?** Non. L'administrateur doit l'examiner, choisir une durée autorisée et expliquer le motif. Une alerte peut avoir une cause légitime.

**Masquer le menu suffit-il ?** Non. Chaque requête vérifie côté serveur le rôle, l'activité du compte, le flag et, pour une mutation, POST/CSRF. Les tests appellent aussi directement l'URL.

**Comment garantir l'audit ?** Les changements et événements sont transactionnels, l'auteur et la date sont enregistrés, et les doublons sont refusés. Cela ne remplace pas une conservation externe sécurisée des journaux en production.

**Observe-t-on secrètement les personnes ?** Non. Aucun écran, mot de passe, compte bancaire ni conversation privée n'est collecté. Les sessions affichées ne prouvent pas une présence en temps réel.

**Quelles limites ?** Les tests locaux SQLite ne démontrent pas le comportement sous une forte concurrence en production. L'interface reste désactivée en production ; une éventuelle ouverture nécessite une revue distincte des opérations, de la rétention et de la conformité. Aucune purge réelle n'a été exécutée.
