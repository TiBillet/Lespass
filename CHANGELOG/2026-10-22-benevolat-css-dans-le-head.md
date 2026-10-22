# CSS du bénévolat chargé dans le head / Volunteering CSS loaded in the head

**Date :** 2026-10-22
**Migration :** Non

## Resume / Summary
**Quoi / What :** `booking/css/benevolat.css` est maintenant chargé dans le `<head>` des trois shells (classic, V2, faire_festival). Les `<link>` posés par les pages et les partials du bénévolat sont supprimés.
/ `benevolat.css` is now loaded in the `<head>` of the three shells; the per-page and per-partial `<link>` tags are removed.

**Pourquoi / Why :** Quand le lieu n'a qu'un seul planning, le lien « Bénévolat » du menu (htmx) est redirigé vers la page de ce planning. Cette page est alors rendue avec `headless.html`, qui n'a pas de bloc `extra_meta` : son `<link>` disparaissait, et la page s'affichait sans style. Le `<head>` n'est jamais remplacé par htmx, comme pour `tb-blocs.css`.
/ With a single planning, the htmx menu link is redirected to the planning page, rendered with `headless.html`, which has no `extra_meta` block: the stylesheet was dropped.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/classic/shell.html` | `<link>` vers `benevolat.css` après `tb-blocs.css` |
| `pages/templates/pages/V2/shell.html` | Idem, avant `V2.css` |
| `pages/templates/pages/faire_festival/shell.html` | Idem, avant `faire_festival.css` |
| `booking/templates/booking/benevolat/planning.html` | Bloc `extra_meta` (le `<link>`) supprimé |
| `booking/templates/booking/benevolat/desistement.html` | `<link>` retiré du bloc `extra_meta` (le `noindex` reste) |
| `booking/templates/booking/benevolat/partials/cartes_accueil.html` | `<link>` dans le corps supprimé |
| `booking/templates/booking/benevolat/partials/mes_creneaux.html` | `<link>` dans le corps supprimé |
| `booking/templates/booking/benevolat/liste.html` | Commentaire mis à jour |

---

## Comment tester (a la main) / Manual test

### Test 1 — un seul planning, depuis le menu (le bug)
1. Sur un lieu avec le module bénévolat activé et **un seul** planning à venir.
2. Partir de l'accueil, cliquer sur l'entrée « Bénévolat » du menu.
3. Vérifier : la page du planning s'ouvre directement, **avec** son style (grille, badges, boutons « Je viens »).

### Test 2 — plusieurs plannings
1. Lieu avec au moins deux plannings à venir.
2. Menu « Bénévolat » → la liste des cartes est stylée → cliquer une carte → le planning est stylé.

### Test 3 — autres pages
1. Accueil avec un bloc « Coups de main » : les cartes sont stylées.
2. Mon compte → « Mes créneaux » : les boutons « bv- » sont stylés.
3. Lien « Je ne peux plus venir » d'un mail : la page est stylée.
4. Tester en skin classic, V2 et faire_festival.

### Verifs automatiques
- pytest bénévolat : 236 passés. E2E `test_benevolat_flow.py` : 7 passés.
- `curl` : le `<head>` de `/booking/benevolat/` contient bien `/static/booking/css/benevolat.css`.
