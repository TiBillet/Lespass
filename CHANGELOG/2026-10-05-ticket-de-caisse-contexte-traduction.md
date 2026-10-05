# « Ticket » de caisse reste « Ticket » en français / POS "Ticket" stays "Ticket" in French

**Date :** 2026-10-05
**Migration :** Non

## Resume / Summary
**Quoi / What :** l'en-tête de l'addition en caisse (LaBoutik) utilise maintenant un contexte de traduction `receipt` : `{% translate "Ticket" context "receipt" %}`. Il affiche « Ticket » en français. Les autres « Ticket » (billet d'événement) restent traduits en « Billet ».
/ The POS cart header now uses the `receipt` translation context, so it reads "Ticket" in French. Event tickets are still translated as "Billet".

**Pourquoi / Why :** gettext n'accepte qu'une traduction par `msgid` ; le contexte (`msgctxt`) crée une entrée séparée. / gettext allows one translation per msgid; a context (msgctxt) creates a separate entry.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/templates/cotton/addition.html` | `{% translate "Ticket" context "receipt" %}` (2 occurrences) |
| `locale/fr/LC_MESSAGES/django.po`, `locale/en/LC_MESSAGES/django.po` | Nouvelle entrée `msgctxt "receipt"` / `msgid "Ticket"` / `msgstr "Ticket"` |

Côté Python, même principe : `pgettext_lazy("receipt", "Ticket")`.

---

## Comment tester (a la main) / Manual test
1. `python manage.py compilemessages`.
2. Caisse LaBoutik en français : l'en-tête de l'addition affiche « Ticket ».
3. Mon compte > Réservations : le panneau affiche toujours « Billet ».
