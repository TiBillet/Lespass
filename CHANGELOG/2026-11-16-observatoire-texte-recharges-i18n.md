# Observatoire : texte des recharges en ligne réécrit pour gettext / Observatory: online top-ups text rewritten for gettext

**Date :** 2026-11-16
**Migration :** Non

## Resume / Summary
**Quoi / What :** la tuile « Recharges sur 12 mois » affiche « en ligne : 42 % » au lieu de « 42 % en ligne » (EN : « online: 42 % »). Les deux `.po` sont mis à jour à la main pour ce msgid.
/ The "top-ups" tile now reads "online: 42 %" instead of "42 % online"; both `.po` files updated for this msgid.

**Pourquoi / Why :** dans « {pourcentage} % en ligne », xgettext lit « % e » comme une directive Python `%e` et pose le drapeau `python-format`. La traduction anglaise (« % online » = `% o`) ne correspond plus : `msgfmt -c` échoue et `compilemessages` aussi. Avec le « % » en fin de texte, xgettext ne pose que `python-brace-format` (vérifié). Le texte est formaté en JS (`seo/static/seo/observatoire.js`, `{pourcentage}`), jamais avec `%`.
/ xgettext read "% e" as a Python `%e` directive; the English translation broke `compilemessages`. With "%" at the end, only `python-brace-format` is set.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `seo/views_observatoire.py` | `tuile_recharges_detail` : « en ligne : {pourcentage} % » + commentaire de contrainte |
| `locale/fr/LC_MESSAGES/django.po`, `locale/en/LC_MESSAGES/django.po` | msgid et msgstr de cette entrée |

---

## Comment tester (a la main) / Manual test
1. Lancer `compilemessages` : aucune erreur.
2. Ouvrir l'observatoire (`/observatoire/` ou depuis l'admin) en français puis en anglais.
3. Tuile « Recharges sur 12 mois » : « en ligne : N % » / « online: N % ».

### Verifs automatiques
- `docker exec lespass_django sh -c 'for f in fr en; do msgfmt -c -o /dev/null /DjangoFiles/locale/$f/LC_MESSAGES/django.po && echo $f OK; done'`
- `docker exec lespass_django poetry run pytest tests/pytest/test_observatoire.py -q`
