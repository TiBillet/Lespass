# i18n EN : sync + complétion des traductions manquantes + fix extraction f-string / i18n EN: sync + fill missing translations + f-string extraction fix

**Date :** 2026-06-18
**Migration :** Non / No

**Quoi / What :**
1. **Sync FR/EN** (mode SYNC du skill i18n-translate) : 9 chaînes fuzzy / fuites de langue corrigées.
2. **Complétion EN** : 74 chaînes de **source française** sans traduction anglaise (msgstr EN vide →
   français affiché sur le site anglais) traduites FR→EN. Surtout l'app **crowds/contrib**
   (`Filter by tags`, `venues & organisations`, `contributors`, etc.). Les ~1463 autres msgstr EN
   vides sont de **source anglaise** (repli correct) et restent intacts.
3. **Fix extraction f-string** dans `minutes_to_human` (`BaseBillet/templatetags/tibitags.py`) :
   les unités de durée `_('j')` / `_('h')` / `_('min')` étaient **à l'intérieur de f-strings**
   (`f"{n} {_('j')}"`) → `makemessages` (xgettext) **n'extrait pas** un `_()` dans une f-string,
   donc « j/h/min » restaient en français partout (ex. « 2 j » sur la page Contribuez). Les `_()`
   sont sortis dans des variables locales + commentaires `# Translators:`. **Nécessite un nouveau
   `makemessages`** pour extraire ces 3 unités, puis traduire « j » → « d » en anglais.

**Pourquoi / Why :** supprimer le français qui fuit sur le site anglais (chaînes externalisées mais
non traduites), et corriger un piège d'extraction qui rendait 3 unités invisibles à `makemessages`.

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `locale/en/LC_MESSAGES/django.po` | 9 (sync) + 74 (complétion FR→EN) msgstr remplis ; intégrité blocs 2526=2526, `msgfmt` OK |
| `locale/fr/LC_MESSAGES/django.po` | corrections fuzzy du sync (FR inchangé pour la complétion EN) |
| `BaseBillet/templatetags/tibitags.py` | `minutes_to_human` : `_()` sortis des f-strings (extraction xgettext) + `# Translators:` |
