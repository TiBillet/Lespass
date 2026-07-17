# Correctifs de lisibilité : montant de réservation, badges de tags, commentaires fuités / Legibility fixes

**Date :** 2026-07-17
**Migration :** Non

## Resume / Summary

**Quoi / What :** Trois correctifs indépendants, sans aucun changement de design.
Le montant total d'une réservation était invisible, les badges de tags étaient
illisibles selon la couleur choisie par le lieu, et un commentaire de gabarit fuyait
dans le `<head>` de chaque page événement.
/ Three independent fixes, no design change. The booking total was invisible, tag
badges were unreadable depending on the venue's colour, and a template comment leaked
into every event page's `<head>`.

**Pourquoi / Why :** Les trois échouent **en silence** — rien ne lève d'erreur, la
page s'affiche, elle est juste fausse. Deux touchent des personnes qui ne peuvent pas
le signaler : celle qui lit un prix avant de payer, et le gestionnaire qui choisit une
couleur dans l'admin sans savoir qu'elle rend ses étiquettes illisibles.
/ All three fail silently. Two affect people who cannot report it: whoever reads a
price before paying, and the manager picking a colour with no way to know it produces
unreadable badges.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/commun/formulaires/reservation.html` | Badge du montant total : ajout de `text-secondary-emphasis` |
| `BaseBillet/models.py` (`Tag.contrast_fg`) | Choix de l'encre : YIQ → WCAG 2.1. Ajout du helper `_luminance_relative` |
| `pages/templates/pages/classic/vues/evenement.html` | Commentaire `{# … #}` multi-lignes → `{% comment %}` |
| `pages/templates/pages/faire_festival/vues/evenement.html` | idem |
| `tests/pytest/test_tag_contraste.py` | **NOUVEAU** — 16 assertions |
| `tests/pytest/test_gabarits_commentaires.py` | **NOUVEAU** — aucun `{# … #}` multi-lignes dans `pages/` |

### Bug 1 — le montant de réservation était à 1.28:1

`.badge` de Bootstrap pose `color: #fff` par défaut, et `bg-*-subtle` est un fond
**clair** par construction : ensemble, sans encre explicite, c'est du blanc sur gris
clair. Un fond `-subtle` se marie avec `text-*-emphasis` — le mariage est documenté
chez Bootstrap, il n'était pas fait ici.

**Le piège ne se voit qu'en thème CLAIR**, c'est-à-dire le thème **par défaut**
(`commun/js/theme-switcher.mjs` : `localStorage.getItem('theme') || 'light'`). En
sombre, `bg-secondary-subtle` devient un fond foncé et le blanc repasse à 17.94:1.
Auditer en sombre ne montre rien.

Mesuré, tunnel réellement ouvert : **1.28:1 → 10.51:1** en clair, 7.84:1 en sombre.

Le dépôt ne contient que deux badges `-subtle` : celui-ci et
`fonctionnel/compte/partials/token_table.html:21`, qui portait **déjà**
`text-info-emphasis`. Le mariage correct était connu du projet.

### Bug 2 — `Tag.contrast_fg` mesurait la luminosité perçue, pas le contraste

La formule YIQ `(r*299 + g*587 + b*114) / 1000` n'est pas la norme d'accessibilité.
Elle choisit du blanc sur des teintes moyennes où seul le noir passe. Sur douze
couleurs courantes elle produisait **quatre badges illisibles** :

| couleur du tag | encre YIQ | contraste |
|---|---|---|
| rouge `#e74c3c` | blanc | **3.82:1** |
| vert `#27ae60` | blanc | **2.87:1** |
| bleu `#2980b9` | blanc | **4.30:1** |
| rose `#e93363` | blanc | **4.10:1** |

WCAG 2.1 linéarise chaque composante (correction gamma) avant de les pondérer. Après
correction : **0 échec sur 14 couleurs testées.**

**Le correctif ne peut pas échouer, et c'est démontrable** : le contraste du noir sur
une couleur de luminance L vaut `(L+0.05)/0.05`, celui du blanc `1.05/(L+0.05)`. L'un
croît avec L, l'autre décroît ; le pire cas est leur croisement, à L ≈ 0.179, où les
deux valent **4.58:1**. Le meilleur des deux est donc toujours ≥ 4.58:1, quelle que
soit la couleur. Aucune teinte n'est « impossible ».

`style_attr` est inchangé — il consomme `contrast_fg`.

### Bug 3 — un commentaire fuyait dans le `<head>` de chaque page événement

Le lexer de gabarits Django compile
`tag_re = re.compile(r'({%.*?%}|{{.*?}}|{#.*?#})')` **sans `re.DOTALL`** : `.` ne
franchit pas le saut de ligne, donc un `{# … #}` multi-lignes n'est **jamais** reconnu
comme un commentaire et part tel quel dans le HTML.

Vérifié au lexer : `Template("A{# court #}B").render()` → `"AB"` ;
`Template("A{# l1\nl2 #}B").render()` → `"A{# l1\nl2 #}B"`.

**`{# #}` est MONO-LIGNE.** Multi-lignes ⇒ `{% comment %}` obligatoire.

Ici le commentaire était **dans** `{% block scripts %}`, donc rendu — il sortait en
clair juste avant le JSON-LD, sur chaque page événement. (Un `{# … #}` multi-lignes
posé **hors** de tout `{% block %}` dans un gabarit qui `{% extends %}` est jeté en
silence : bug latent, invisible. Les deux sont fautifs, seul le délai change.)

Un scan du dépôt trouve **8 autres cas** (laboutik 2, onboard 2, BaseBillet 2,
Administration 1, crowds 1) plus 7 dans `OLD_REPO`. Tous de la variété latente. Le
test est donc cadré sur `pages/` ; l'élargir suppose de les corriger d'abord.

---

## Comment tester (a la main) / Manual test

### Test 1 — le montant est lisible (le plus important)
1. Ouvrir un événement payant, cliquer le bouton de réservation.
2. **En thème clair** (le défaut — vider le `localStorage` si besoin) : le montant à
   droite de « Total : N billet(s) pour » doit être **en encre sombre**, lisible.
   Avant : blanc sur gris, invisible.
3. Basculer en sombre : il doit rester lisible.

### Test 2 — les badges de tags
1. Admin → Tags → passer la couleur d'un tag en **rouge `#e74c3c`** ou **vert `#27ae60`**.
2. `/event/` : le libellé du badge doit être en **noir**, lisible.
   Avant : blanc sur rouge (3.82:1) ou blanc sur vert (2.87:1).

### Test 3 — plus de commentaire dans le HTML
```bash
U=/event/<slug-d-un-evenement>/
curl -sk "https://lespass.tibillet.localhost$U" | grep -c "JSON-LD Event construit"   # attendu : 0
curl -sk "https://lespass.tibillet.localhost$U" | grep -c "application/ld+json"        # attendu : 1
```

### Verifs automatiques
```bash
docker exec lespass_django poetry run pytest \
  /DjangoFiles/tests/pytest/test_tag_contraste.py \
  /DjangoFiles/tests/pytest/test_gabarits_commentaires.py -q
```
État : **20 passed** (avec `test_gabarit_skin.py`). `manage.py check` : 0 issue.

### Hors périmètre / Out of scope
Le redesign du socle `classic` (contrat de jetons `--tb-*`/`--skin-*`, accent losean,
pied de page, grille des adhésions, suppression des dégradés) vit sur la branche
**`v2-skin`** et se merge d'un bloc. Rien n'en est porté ici : un socle à moitié
converti ferait cohabiter deux vocabulaires.

Connus, **non corrigés ici** :
- `btn-outline-secondary` fige `#6c757d` et ne suit pas le thème (3.29:1 sur le corps
  sombre, 2.84:1 sur le pied). Le correctif propre passe par `--tb-texte-doux`, un
  jeton qui n'existe que sur `v2-skin`.
- Les 4 « Annuler » en `btn-danger` (`commun/formulaires/reservation.html:516`,
  `contact.html:34`, `adhesion/form.html:624`, `recherche_evenements.html:72`) sont
  des `<a href=".">` qui ne détruisent rien : le rouge ment sur ce qu'ils font. Sans
  gravité ici — le `primary` étant bleu, les deux boutons restent distinguables.
