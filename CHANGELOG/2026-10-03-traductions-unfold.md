# Textes de l'admin Unfold traduisibles / Translatable Unfold admin strings

**Date :** 2026-10-03
**Migration :** Non

## Resume / Summary
**Quoi / What :** Ajout de `Administration/traductions_unfold.py`. Il declare les 66 textes de l'admin Unfold
qu'aucun catalogue installe ne traduit (« Search apps and models... », filtres, editeur de texte, theme...).
/ Adds a file declaring the 66 Unfold admin strings no installed catalogue translates.

**Pourquoi / Why :** django-unfold 0.89.0 n'a aucune traduction francaise. `makemessages` ne lit pas
site-packages : ce fichier permet de garder ces textes dans notre `.po` et de les traduire.
/ Unfold ships no French locale; makemessages ignores site-packages, so we declare the strings in the project.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/traductions_unfold.py` | Nouveau : liste des textes Unfold (`gettext_noop` / `ngettext_lazy`). Importe nulle part. |

---

## Comment tester (a la main) / Manual test

### Test 1 — scenario nominal
1. Le mainteneur lance `makemessages -l fr -l en`.
2. Verifier que `locale/fr/LC_MESSAGES/django.po` contient `msgid "Search apps and models..."`,
   avec la reference `Administration/traductions_unfold.py`.
3. Remplir les `msgstr` FR (par exemple « Rechercher des applications et des modeles... »).
4. Lancer `compilemessages` et redemarrer le serveur.
5. Ouvrir l'admin en francais : la barre de recherche, les filtres et le selecteur de theme sont en francais.

### Test 2 — textes au pluriel
1. Dans la palette de recherche, taper un mot : « Found N results in X seconds » doit etre traduit.
2. Dans une liste admin, exporter une selection : « Export N selected items. » doit etre traduit.

### Apres une mise a jour d'Unfold
Verifier que chaque texte du fichier existe toujours dans `site-packages/unfold` (avec `rg`).
Un texte modifie par Unfold n'est plus traduit, sans erreur visible.
