# Socle `classic` : contrat de jetons + identité éditoriale / Classic base: token contract + editorial identity

**Date :** 2026-07-16
**Migration :** Oui — `pages/migrations/0004_alter_configurationsite_skin.py`
(`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`)

## Resume / Summary

**Quoi / What :** Le socle `classic` (le skin que voit tout le monde : le défaut
`reunion` n'a pas de dossier, il *est* classic) sort du Bootstrap générique et reçoit
un contrat de jetons CSS que les autres skins consomment sans le forker. Trois skins
deviennent sélectionnables depuis l'admin.
/ The `classic` base leaves generic Bootstrap behind and gains a CSS token contract
that other skins consume without forking it. Three skins become selectable from the admin.

**Pourquoi / Why :** `tb-blocs.css` chaînait son accent sur `var(--bs-primary)`. Or
**`--bs-primary` n'était défini nulle part dans le projet** — aucun champ en base, aucun
template, aucun CSS : le `#0d6efd` visible partout était le **défaut de Bootstrap**, que
personne n'avait choisi. Par ailleurs les jetons vivaient sur `.tb-page`, c'est-à-dire
uniquement dans le `<main>` des pages CMS : navbar, footer, agenda, adhésions et
événement n'en recevaient aucun et restaient en Bootstrap brut.
/ The accent was chained to `--bs-primary`, which was defined **nowhere** in the project:
the blue everyone saw was Bootstrap's default, chosen by no one. And the tokens lived on
`.tb-page`, so the chrome never received them.

### Le contrat de jetons (FIGÉ) / The token contract (FROZEN)

| Jeton | Rôle |
|---|---|
| `--tb-accent` | **encre portante** — on pose `--tb-accent-contraste` dessus. Garanti ≥ 4.5:1. |
| `--tb-accent-vif` | **le geste** — filets, bordures, pastilles. Le socle n'y pose **jamais** de texte. |
| `--tb-accent-contraste` | ce qui se pose **sur** `--tb-accent` |
| `--tb-fond` / `--tb-fond-contraste` | **fond** d'un élément plein + son encre. Par défaut = l'accent → zéro régression. |

Points d'entrée des skins : `--skin-accent`, `--skin-accent-vif`,
`--skin-accent-contraste`, `--skin-fond`, `--skin-fond-contraste`,
`--skin-texte-doux`, + `--skin-accent-sombre`, `--skin-accent-contraste-sombre`,
`--skin-texte-doux-sombre`. C'est une **indirection** (le socle *lit*, le skin *pose*),
pas une redéfinition : `page.html` charge le CSS dans le `<body>`, donc après celui du
skin — un `:root` posé par un skin perdrait la cascade.

**L'identité ne vient pas de nulle part** : `commun/css/vars.css` porte déjà une palette
créole nommée (`--kouler-letsi`, `--kouler-piton`…) qui ne servait qu'aux dégradés. Le
socle la remonte au rang d'accent. Aucune ligne de `commun/` n'est modifiée.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `pages/static/pages/css/tb-blocs.css` | Jetons `.tb-page` → `:root` ; chaîne `--bs-primary` cassée ; `--tb-accent-vif`, `--tb-fond`, `--tb-fond-contraste` ajoutés ; bloc `[data-bs-theme="dark"]` ; `overflow-x: clip` sur `html`+`body` ; sections CHROME / AGENDA / ACCORDÉON / ADHÉSIONS / ÉTIQUETTES |
| `pages/templates/pages/classic/shell.html` | Charge `tb-blocs.css` dans le `<head>` : le shell enveloppe **toutes** les pages, `page.html` seulement les pages CMS |
| `pages/templates/pages/classic/partials/footer.html` | Ft3 → grille asymétrique ; les `btn-success` vert / `btn-warning` jaune (couleurs **sémantiques** détournées en couleurs de marque) → liens fléchés |
| `pages/static/pages/css/tb-blocs.css` (suite) | **`.btn-primary` / `.btn-outline-primary` rebranchés** sur les jetons via `--bs-btn-*` : le CTA de réservation, le « voir plus » de l'agenda et les boutons de l'accueil prenaient encore le `#0d6efd`. `success`/`danger`/`warning` **non** rebranchés (couleurs sémantiques, et ce fichier atteint `commun/`). `.form-check-input:checked` réécrit (Bootstrap y compile le bleu en dur au Sass) + `accent-color` |
| `pages/static/pages/css/tb-blocs.css` (suite) | **Lavis d'accent supprimés** : `.tb-bloc--cta` et `--tb-hero-fond` passent sur `--tb-surface-alt`. Un `color-mix(accent N%, surface)` fabrique une **troisième surface** hors des deux calibrées — l'accent y tombait à 4.40:1 et 4.23:1. La couleur reste dans le filet |
| `pages/templates/pages/classic/vues/adhesions.html` | Grille `card`/`card-footer`/`btn-primary` → jetons `--tb-*` |
| `pages/templates/pages/classic/vues/agenda_liste{,_suite}.html` | Barre de dates en dégradé `--mayaj-pons` → serif + filet |
| `pages/templates/pages/classic/partials/evenement_accordeon.html`, `evenement_benevoles.html` | 3 aplats en dégradé → filet ; **attribut `class` dupliqué corrigé** (le second était ignoré en silence) |
| `pages/templates/pages/classic/vues/{agenda,evenement}.html`, `partials/carte_evenement.html` | Badges de tags : aplat `style_attr` → **pastille + encre** |
| `pages/templates/pages/classic/vues/evenement.html`, `pages/templates/pages/faire_festival/vues/evenement.html` | Commentaire `{# #}` multi-lignes qui **fuyait dans le `<head>`** → `{% comment %}` |
| `pages/models.py` + migration `0004` | `choices` de `ConfigurationSite.skin` : ajout de `la_filature` et `miete` |
| `tests/pytest/test_socle_contrastes.py` | **NOUVEAU** — les couples du socle passent AA, en clair ET en sombre, sur les **deux** surfaces |
| `tests/pytest/test_gabarits_commentaires.py` | **NOUVEAU** — aucun `{# … #}` multi-lignes dans `pages/` |

### Les deux pièges qui ont coûté le plus / The two costly traps

1. **`{# … #}` est MONO-LIGNE.** Le lexer Django compile
   `tag_re = re.compile(r'({%.*?%}|{{.*?}}|{#.*?#})')` **sans `re.DOTALL`** : un
   commentaire multi-lignes n'est jamais reconnu et part **en clair dans le HTML**.
   Vérifié : `Template("A{# l1\nl2 #}B").render()` → `"A{# l1\nl2 #}B"`. Il ne se voit
   que dans un gabarit **sans** `{% extends %}` (sinon le texte hors `{% block %}` est
   jeté en silence — bug latent). Multi-lignes ⇒ `{% comment %}` obligatoire.
2. **Le site a DEUX surfaces.** Clair : `#ffffff` / `#f6f5f1`. Sombre : `#212529` /
   `#2b3035`. Le pied de page est sur la **tertiary**. Une encre calibrée sur le seul
   corps de page **échoue dans le pied, sans rien signaler**. Ça a frappé **trois fois**.

---

## Comment tester (a la main) / Manual test

### Test 1 — le bleu Bootstrap a disparu
1. Aller sur `https://lespass.tibillet.localhost/`.
2. Descendre au bloc CTA : les boutons **Agenda** / **Adhésions** sont en letsi (rose-rouge), plus en `#0d6efd`.
3. Le pied de page : les liens sont en **encre** (plus en bleu), et il n'y a plus ni bouton **vert** ni bouton **jaune**.
4. Vérification objective : `curl -sk https://lespass.tibillet.localhost/ | grep -c '0d6efd'` → **0** attendu dans le HTML du socle.

### Test 2 — les jetons atteignent TOUTES les pages (pas que la home)
```bash
for u in / /event/ /memberships/ /federation/; do
  echo -n "$u -> "; curl -sk "https://lespass.tibillet.localhost$u" | grep -c "tb-blocs.css"
done
```
Attendu : `2` sur `/` (shell + page.html, le navigateur déduplique), `1` partout ailleurs.
**Avant ce chantier `/event/` et `/memberships/` renvoyaient `0`.**

### Test 3 — plus aucun dégradé, plus aucun aplat de badge
1. `https://lespass.tibillet.localhost/event/` : les barres de dates sont des titres **serif soulignés d'un filet**, plus des bandes orange→rose.
2. Les étiquettes sont des **pastilles + libellé en encre**, plus des rectangles colorés. La couleur choisie par le lieu (`Tag.color`) est toujours là, dans la pastille.
3. Ouvrir un événement : les entêtes d'accordéon (« Horaires », « Lieu ») n'ont plus d'aplat dégradé.

### Test 4 — le mode sombre (le plus important)
1. Cliquer le bouton **thème** dans la navbar. Basculer en sombre.
2. Descendre au **pied de page** : les liens fléchés « Créez un espace TiBillet… » doivent rester lisibles (c'est là que ça cassait : 3,91:1).
3. Le texte gris du pied doit rester lisible (cassait à 3,89:1).
4. Les boutons pleins doivent avoir une **encre sombre**, pas du blanc.

### Test 5 — le contrat tient : un skin habille le chrome sans forker
1. Admin du tenant → *Configuration du site* → *Thème graphique* → **La Filature** → voir `https://chantefrein.tibillet.localhost/`.
2. Le **pied de page** (qui vient de `classic` par fallback) doit être **cyan**, pas letsi : la Filature pose `--skin-accent` sur `:root` et gagne.
3. `pages/templates/pages/la_filature/` ne contient que `shell.html` + `page.html` + `DESIGN.md` : **aucune ligne de `tb-blocs.css` n'est forkée.**

### Test 6 — l'audit mesuré (3 skins × 3 pages × 2 thèmes)
Le script d'audit vit dans le scratchpad de session, pas dans le dépôt. Sa méthode, si
on veut la refaire : piloter Chrome en CDP, poser `localStorage.theme` **par origine**
(elle est propre à chaque sous-domaine), puis pour chaque page relever les styles
**calculés**, en remontant l'arbre pour trouver le fond réellement peint.

> **Piège de mesure, à ne pas répéter :** résoudre les couleurs avec un parseur maison
> sur la chaîne CSS **ne marche pas** — un skin qui écrit en `oklch()` (c'est le cas de
> `miete`) donne des ratios fantaisistes, et l'audit a d'abord signalé 8 faux bugs chez
> lui. Peindre la couleur sur un `<canvas>` 1×1 et relire le pixel résout **n'importe
> quel** format (hex, `rgb`, `oklch`, `color-mix`).

Résultat au 2026-07-16 : **socle 6/6 propre, miete 6/6 propre** (zéro `#0d6efd`, zéro
échec de contraste, zéro scroll horizontal). `la_filature` : 8 éléments bleus sur
`/event/`, 2 sur `/memberships/` — **son `shell.html` ne charge pas `tb-blocs.css`**, donc
ses pages non-CMS n'ont ni jetons ni rebranchement ; et son `--skin-accent-sombre` est à
4.35:1 sur la surface du pied. Signalé à son agent, correctif = une ligne dans son shell.

### Verifs automatiques
```bash
docker exec lespass_django poetry run pytest \
  /DjangoFiles/tests/pytest/test_socle_contrastes.py \
  /DjangoFiles/tests/pytest/test_gabarits_commentaires.py \
  /DjangoFiles/tests/pytest/test_gabarit_skin.py -q
```

### État de la suite complète
`861 passed, 19 failed, 2 skipped` (13 min). **Les 19 échecs sont préexistants et hors
périmètre** : `test_cloture_caisse.py` (7), `test_caisse_navigation.py` (4),
`test_cloture_enrichie.py` (3) — domaine caisse/laboutik. Aucun des trois fichiers ne
référence `pages`, les skins ni les jetons. Échec type : `assert cloture_m is not None`
(`test_cloture_enrichie.py:303`), une clôture mensuelle non créée. **À traiter hors de
ce chantier.**
