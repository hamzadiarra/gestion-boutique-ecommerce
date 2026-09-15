# Internationalisation Django, phase 1

Le francais reste la source. Les valeurs techniques en base et les calculs
Decimal sont conserves. Aucune migration n'est necessaire.

## Configuration

Langues actives : fr et en. Le catalogue bm (Bambara / Bamanankan) est
conservé en archive, mais retiré de l'interface jusqu'à validation humaine.
LocaleMiddleware suit
SessionMiddleware et precede CommonMiddleware. Le POST Django set_language
utilise le cookie django_language et conserve une URL locale via next.
Aucun prefixe de langue n'est ajoute aux routes.

Le catalogue bm reste disponible dans locale/bm pour une future réactivation.
Les formats utilisent un separateur de milliers espace inseparable. Les
montants restent des Decimal; l'anglais utilise le point decimal.

## Catalogues et limites actuelles

Les catalogues PO sont initialises a partir des chaines marquees. L'outil
tools/prepare_i18n_phase1.py est un outil ponctuel de preparation, pas un
compilateur ni un remplacement de GNU gettext. Ne pas le relancer pour
maintenir les traductions : utiliser makemessages.

Le premier passage a marque 1366 messages, dont 277 traduits en anglais.
La couverture anglaise reste partielle, pas une traduction complete.
Les traductions Bambara restent vides pour validation humaine. Les messages
absents conservent le texte source francais. Les textes dynamiques complexes,
les f-strings et une partie du JavaScript inline restent a traiter avec
blocktrans et des parametres nommes. Les messages simples du gestionnaire
offline sont fournis par le template via data-*, sans dictionnaire anglais JS.

## Blocage GNU gettext sur ce poste Windows

makemessages echoue : Can't find msguniq. Make sure you have GNU gettext
tools 0.19 or newer installed.

compilemessages echoue : Can't find msgfmt. Make sure you have GNU gettext
tools 0.19 or newer installed.

Aucun compilateur de remplacement ni fichier MO artificiel n'est fourni.
Le catalogue anglais est compilé. BM n'est volontairement pas sélectionnable
via set_language dans cette phase.

Apres installation de GNU gettext >= 0.19 et ajout de ses binaires au PATH :

```powershell
python manage.py makemessages -l en
python manage.py makemessages -l bm
python manage.py compilemessages
python manage.py test core.test_i18n
```

Completer et relire les traductions anglaises avant livraison multilingue.
Les tests necessitant les MO sont explicitement ignores tant que les
catalogues ne sont pas compiles; ce ne sont pas des tests declares reussis.
Les autres tests couvrent configuration, cookies, URLs, CSRF, permissions,
checkout FR/EN, montants et valeurs de statut inchangees.

La liste des fichiers du premier passage est dans docs/i18n-files.txt.
Le SEO multilingue, les URL prefixees et la traduction des donnees saisies
par les utilisateurs ne font pas partie de cette phase.
