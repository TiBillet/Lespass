# LaBoutik : popups de la caisse alignees sur le style de la refonte / POS popups restyled after the redesign

**Date :** 2026-09-03
**Migration :** Non

## Resume / Summary

**Quoi / What :** Les 21 popups de l'interface de caisse (moyens de paiement,
confirmation, lecture NFC, retour de carte, fonds insuffisants, complement,
identification et recapitulatif client, vider la carte, alertes, rapport de
cloture, selection de tarif, panneau contextuel d'article) rejoignent le systeme
visuel deja porte sur les tuiles, le menu ouvrant et le panneau ticket. Elles
gardent leur forme actuelle — couche pleine page, gros boutons d'action — mais
plus une seule couleur ni une seule police n'y est ecrite en dur, et le bas des
popups redevient atteignable sur un terminal de poche.
/ The 21 POS popups join the visual system already ported to the tiles, the
burger panel and the ticket panel. They keep their current shape — full-page
layer, large action buttons — but not a single colour or font is hard-coded any
more, and the bottom of a popup is reachable again on a pocket terminal.

**Pourquoi / Why :** L'ecart se voyait des qu'une popup s'ouvrait par-dessus le
nouveau panneau ticket. L'inventaire a aussi trouve deux defauts qui depassent
le cosmetique : `#messages` et `#confirm` n'avaient ni `overflow`, ni
`max-height`, ni scroll — sur SUNMI V2s (360 x 720), l'ecran des moyens de
paiement empilait 6 boutons de 120 px fixes dans ~670 px utiles, et le dernier
bouton etait **physiquement inatteignable** ; et l'overlay de selection de tarif
etait ecrit deux fois, dans `articles.css` et dans `tarif.css`.
/ The gap showed the moment a popup opened over the new ticket panel. The
inventory also found two defects beyond cosmetics: the overlay layers had no
scroll at all, leaving the last payment button unreachable on a V2s; and the
rate-selection overlay was written twice.

**Isolation des impacts :** **aucun fichier HTML ni JS n'a ete touche** — le
travail est integralement CSS. Les `data-testid` sont conserves : ils sont a la
fois les ancres des tests et les selecteurs de style des regles `:has()`. Le
codage couleur par flux est conserve lui aussi (le caissier reconnait l'ecran a
sa teinte), mais chaque teinte est desormais derivee des jetons par `color-mix`
au lieu d'un hex isole, avec un repli avant chaque `color-mix` pour les WebView
Android sans support.
/ No HTML and no JS were touched — the work is entirely CSS. Every `data-testid`
is preserved: they are both test anchors and the style selectors of the `:has()`
rules. The per-flow colour coding is kept, but each tint is now derived from
tokens via `color-mix`, with a plain fallback for old Android WebViews.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/static/css/palette.css` | 24 jetons ajoutes : semantiques (`--valid-deep`, `--valid-ink`, `--danger`, `--danger-ink`, `--warn`, `--warn-ink`, `--nfc`), voiles neutres en alpha (`--wash-1..4`, `--shade-1/-2`) et par famille (`--info-wash/-edge/-ink`, `--valid-wash/-edge`, `--danger-wash/-edge`, `--warn-wash/-edge`), plus `--overlay-veil`, `--font-ui`, les courbes nommees `--ease-out/-in/-in-out` et les durees `--dur-fast/-base/-slow`. **Aucun jeton herite n'est retire** : `hx_messages.html` et `cotton/bt/paiement.html` en passent les noms depuis le serveur |
| `laboutik/static/css/overlay.css` | **Scroll ajoute sur `#messages` / `#confirm`** (le correctif du bas de popup inatteignable) ; `#messages > :first-child` passe de `height:100%` a `min-height:100%` pour que le contenu puisse grandir ; les 13 regles `:has()` re-derivees des jetons et passees en `:not(.hide)` (sans quoi elles battent le `.hide` de `modele00.css` et la popup ne se ferme plus) ; 134 valeurs brutes et 19 `font-family` jetonises ; typographie des titres et des montants alignee sur `.tk-title` et `.payment-total-val` du prototype ; filet de mise au point et etat desactive universels sur tout ce qui est cliquable dans une couche ; seuils responsive unifies sur 599 px ; plancher SUNMI V2s ; `prefers-reduced-motion` ; tampon Hallmark en tete |
| `laboutik/static/css/modele00.css` | `.bt-basic-container` (le bouton partage par TOUTES les popups) : `height` fixe → `min-height`, `width` → `min(280px, 100%)`, coins `--r-ctrl`, et les **huit etats** qui manquaient (survol, focus, appui, desactive, chargement, erreur, succes) |
| `laboutik/static/css/tarif.css` | Source unique de l'overlay tarif ; 32 valeurs brutes jetonisees ; coffrage de boite du prototype (`--r-panel`, filet `--line`, ombre) ; huit etats sur les boutons ; **contraste corrige** sur le bouton OK du prix libre (blanc sur `--valid` tombait a ~2,4:1 → `--valid-ink`) ; mise au point du champ par `outline` et non par `outline:none` ; `prefers-reduced-motion` |
| `laboutik/static/css/articles.css` | **Suppression des lignes 353-529** (177 lignes) : copie morte de l'overlay tarif. Les 8 regles qui n'existaient que la ont ete reportees dans `tarif.css` **avant** la suppression. Zone du panneau contextuel d'article passee des jetons herites (`--noir04`, `--gris01`…) aux jetons de la refonte, avec filet de mise au point |
| `laboutik/static/css/components.css` | Ecran d'attente NFC aligne : pictogramme en `--nfc` qui respire (recette `.card-wait` du prototype), bouton de simulation sur les jetons avec ses etats, spinner sur `--nfc` + repli `prefers-reduced-motion` |
| `laboutik/static/css/hx_managed_card.css` | `background-color: aquamarine` → `--surface-2` (seule couleur en dur du fichier) |
| `laboutik/static/css/addition.css` | 2 `font-family` jetonises (coherence) |

### Slop test / Slop test

58 portes, portee composant (les portes de diversification, de hero et de
nav/footer ne s'appliquent pas a un lot de composants). Sept corrections
apportees pendant la passe : `transition: all` remplace par des proprietes
nommees, 42 courbes par defaut remplacees par les courbes nommees, encre des
messages d'alerte passee du noir au clair (le noir tombait a ~2:1 sur `--info`),
italique retire d'un libelle d'action, filet de mise au point universel,
`overflow-wrap` sur les titres, etat desactive a trois canaux.

### A faire / To do

- `ventes.css` (5 `font-family`) et `sortie_de_caisse.css` (12) gardent leurs
  polices en dur : ces deux fichiers stylent les memes ecrans que la seconde
  moitie de `overlay.css` mais n'etaient pas dans le perimetre valide.
- `hx_managed_card` (ecran cashless gere, atteignable seulement depuis
  l'interface restaurant) **deborde en 360 px** : `#mc-actions` en `1fr 2fr`
  avec `margin-left: 32px` a cote d'un pave numerique de 240 px. Documente,
  pas corrige.
- Deux morceaux de code mort reperes, **laisses en place faute de feu vert** :
  `vk.css` (56 lignes, chargé par aucun template) et la regle
  `.check-carte-container` d'`overlay.css` (aucune occurrence dans les templates).

### Verification / Verification

Apercu statique hors depot : chaque popup rendue avec le markup reel de son
partial et le CSS reel du depot, en 900 px et en 360 px.
A controler sur la stack : la **fermeture** de chaque popup (le piege `.hide`),
le parcours de paiement complet, et le fait que le bas de l'ecran des moyens de
paiement soit atteignable en 360 px.
`pytest tests/pytest/test_paiement_complementaire.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_stock_negatif.py`
(ils assertent sur les `data-testid` que ce lot conserve).
