# Skin « miete » — le menu est fait de bulles / The "miete" skin — the menu is made of bubbles

**Date :** 2026-07-16
**Migration :** Non — **mais l'activation en demande une** (voir « Ce qui reste à faire »).

## Resume / Summary

**Quoi / What :** nouveau skin `miete` pour l'app `pages`, reconstruit depuis l'ADN
du site de La MIETE (tiers-lieu à Villeurbanne), récupéré sur Wayback Machine.
Geste signature : les entrées du menu principal sont des **bulles de pensée
vectorisées**, reprises des dessins du lieu. Aucun code Python, aucun fichier
partagé touché.
/ New `miete` skin for the `pages` app, rebuilt from the DNA of La MIETE's site
(archived on Wayback Machine). Signature move: the main menu entries are
**vectorised thought bubbles**, taken from the venue's own artwork. Zero Python,
no shared file touched.

**Pourquoi / Why :** un lieu dont l'ancien site est mort veut retrouver son
identité en arrivant sur TiBillet. L'identité de la MIETE, c'est **l'accessibilité**
(police Luciole partout, barre d'outils dédiée, « L'Accessibilité Universelle »
en entrée de menu). Le skin en fait donc le skin accessibilité-d'abord de
TiBillet, réutilisable par tout lieu ayant la même exigence.
/ A venue whose old site died wants its identity back on TiBillet. La MIETE's
identity IS accessibility, so this becomes TiBillet's accessibility-first skin,
reusable by any venue with the same requirement.

### Fichiers ajoutés / Added files

| Fichier / File | Rôle / Role |
|---|---|
| `pages/templates/pages/miete/design.md` | Le système verrouillé — il voyage avec le skin |
| `pages/templates/pages/miete/shell.html` | Squelette page complète (copie du socle + CSS skin + lien d'évitement) |
| `pages/templates/pages/miete/headless.html` | Squelette des réponses HTMX |
| `pages/templates/pages/miete/partials/navbar.html` | La nav en bulles |
| `pages/templates/pages/miete/partials/bulle.html` | Le SVG de la bulle (décoratif, sans texte) |
| `pages/templates/pages/miete/partials/footer.html` | Pied de page Ft3 en colonnes |
| `pages/static/miete/css/tokens.css` | Jetons + `@font-face` Luciole |
| `pages/static/miete/css/miete.css` | Mise en page du skin |

Tout le reste retombe sur `pages/classic/` via `gabarit_skin()`.

### Fichiers NON touchés (règle d'autonomie du contrat de skin)

`pages/models.py`, les migrations, `pages/classic/`, `commun/`, `tb-blocs.css`,
`laboutik/`, `kiosk/`. **Trois agents travaillaient en parallèle sur trois skins :
la choice + la migration sont groupées par le mainteneur, en une seule passe.**

## Ce qui a été décidé, et pourquoi

**La police est déjà là.** Luciole vit dans `BaseBillet/static/commun/font/luciole/`
(4 woff2, CC BY 4.0). Le skin n'embarque **aucune fonte** : il pointe sur le commun.

**Encre noire sur aplat coloré, jamais du blanc.** Le site d'origine met
`color:#FFFFFF` sur ses boutons vermillon : **3,62:1**, sous le seuil WCAG AA.
Ses **bulles dessinées**, elles, mettent du noir — et le noir sur ce vermillon
donne **5,70:1**. La règle du skin vient donc des dessins du lieu, pas de son CSS.
Les cinq teintes de bulles (relevées dans les `.png`, absentes du CSS) passent
toutes AA face au noir : jaune 14,71:1 · vert 9,53:1 · cyan 10,35:1 · rose 5,85:1 ·
vermillon 5,70:1.

**Le libellé est du vrai texte, jamais du dessin.** Les `.png` du lieu ont leur
libellé cuit dans le pixel : invisible pour un lecteur d'écran, et le bouton
« Augmenter le texte » du lieu ne le grossit pas. Ici le SVG est décoratif
(`aria-hidden`, `focusable="false"`) et le libellé est du HTML dimensionné en `em`.

**Aucun libellé n'est codé en dur.** Ils viennent tous de `main_nav`. La couleur
tourne par position via `{% cycle %}`. N'importe quel lieu peut porter ce skin.

**Le branchement au socle — trois leviers, et un seul ne suffisait pas.** Le skin
ne surchargeant que 5 gabarits, tout le reste (blocs CMS, agenda, événement,
adhésions, chrome) est rendu par `classic`. Trois mécanismes distincts, appris à
la mesure et pas au raisonnement :

1. **Les jetons du socle → `--skin-*` sur `:root`** (`tokens.css`).
   Le socle lit `--tb-accent: var(--skin-accent, …)` **sur `:root`**. La
   substitution utilise le `--skin-accent` *vu par `:root`*, puis la valeur
   **calculée** descend par héritage : un `--skin-*` posé sur un descendant
   (`.skin-miete`) **n'est jamais lu**. Vérifié au navigateur :
   `--skin-accent` sur `.skin-miete` → `--tb-accent` reste `#e61c51` (aucun effet) ;
   sur `:root` → la valeur est prise. **C'est `:root`, pas la classe de scope.**
2. **Les jetons SANS point d'entrée → `.skin-miete .tb-page`** (`miete.css`).
   `--tb-police-titre` (Georgia serif !), `--tb-rayon` (10px) et `--tb-transition`
   n'ont pas de `--skin-*`. Il faut les surcharger sur `.tb-page` lui-même, en
   spécificité (0,2,0) > (0,1,0) — l'élément le plus **proche** gagne pour une
   propriété personnalisée, pas le sélecteur le plus spécifique.
3. **Les boutons Bootstrap → le socle s'en charge.** `.btn-primary` /
   `.btn-outline-primary` sont rebranchés par le socle sur `--tb-fond` /
   `--tb-accent` : ils prennent nos `--skin-*` tout seuls, **y compris dans le
   chrome de `commun/`** (tunnels de réservation et d'adhésion, panneau de
   connexion) — que ce skin n'atteindrait pas s'il se scopait. Vérifié : 0
   occurrence de `#0d6efd` sur `/`, `/event/` et `/memberships/`.
   Ne restent que **deux écarts**, dans un `.btn-primary` volontairement non scopé
   (le chrome vit hors `.skin-miete`, et ce CSS n'est chargé que par ce skin) :
   - **Le sens du geste.** Le socle assombrit l'aplat au survol/actif
     (`color-mix` vers `black`), ce qui suppose une encre **claire**. La nôtre est
     **noire** : assombrir *réduit* le contraste. Mesuré avec notre vermillon —
     repos 5,70:1, survol 4,57:1, **actif 3,89:1 (sous AA)**. On éclaircit :
     survol 6,58:1, actif 7,32:1. Vérifié au navigateur sur les 5 boutons.
   - **La bordure noire 2px**, que la source de la MIETE pose sur ses boutons.
     Le socle aligne la bordure sur l'aplat (invisible, voulu chez lui).

**Les rôles de couleur ne sont pas interchangeables** (découplage `--tb-fond` du
socle, qui nous rend le vermillon de marque) :

| rôle | valeur | pourquoi |
|---|---|---|
| `--skin-accent` (encre + lien) | `#B83E18` | la marque échoue en texte : 3,69:1 sur blanc |
| `--skin-accent-vif` (geste) | `#E5562B` | le socle n'y pose jamais de texte |
| `--skin-fond` (aplat) | `#E5562B` | **la marque revient**, encre noire à 5,70:1 |

**L'encre suit la clarté du fond, ce n'est pas un dogme.** Les bulles imposent du
noir parce que le vermillon de *marque* est clair (L 63,7 %). Le jumeau assombri
(L 53,4 %) appelle du blanc. Même raisonnement, résultat inverse.

**Mode sombre** (`[data-bs-theme="dark"]`, bouton Thème de la navbar).
Le skin forçait un papier **blanc en dur** : en sombre, skin blanc + chrome noir,
et l'encre douce `#545454` à **2,11:1**. Corrigé par un bloc sombre dans
`tokens.css`. Trois décisions :
- `--tb-surface` / `--tb-texte` / `--tb-bordure` **ne sont pas surchargés** : le
  socle les branche sur les `--bs-*` de Bootstrap, thème-conscients — c'est ce qui
  donne le sombre gratuitement. Les figer, c'était précisément le bug.
- **Les bulles ne changent pas** : le contraste d'un libellé sur sa bulle ne
  dépend que du couple encre/teinte, jamais du fond de page. Mêmes chiffres dans
  les deux thèmes.
- **`--skin-fond` n'a pas de variante sombre**, à dessein : le bloc sombre du
  socle ne redéfinit pas `--tb-fond`, donc l'aplat de marque traverse les deux
  thèmes. C'est ce qu'on veut d'une couleur de marque.

**Limite connue** : en sombre, le contour noir désaligné devient invisible **hors**
du remplissage (1,36:1 sur `#212529`). La bulle reste lisible et reconnaissable —
seul son halo s'atténue. Dégradé, pas cassé, non corrigé.

**Contrastes vérifiés sur les TROIS surfaces, pas seulement le papier.** Une encre
calibrée sur `--bs-body-bg` peut échouer sur `--bs-tertiary-bg` (les pieds de page) :
en clair la tertiary est plus sombre, en sombre elle est plus claire. Croisement
complet, couleurs résolues **par le navigateur** (canvas 1×1, donc `oklch()` et
`var()` résolus en sRGB réel) :

| encre | body-bg | tertiary-bg | mon papier-2 |
|---|---|---|---|
| accent-lien (clair `#b83e18`) | 5,61 | 5,33 | **5,06** |
| encre douce (clair `#545454`) | 7,57 | 7,18 | 6,82 |
| accent-lien (sombre `#ff8a5b`) | 6,64 | 5,73 | 5,73 |
| encre douce (sombre `#d5d0d3`) | 10,13 | 8,75 | 8,75 |

Aucune sous 4,5:1. **La marge EST la robustesse** : une teinte calibrée pile à
4,5:1 sur une surface tombe sur la suivante.

**Deux pièges de copie — à relire après CHAQUE vague du socle.**

1. **`{# … #}` est MONO-LIGNE.** Le lexer de Django compile `tag_re` **sans**
   `re.DOTALL` : le `.` ne franchit pas le saut de ligne, donc un `{# … #}` sur
   deux lignes n'est jamais reconnu et **part tel quel dans la sortie**. Ça fuyait
   **5 fois** dans le HTML servi (une par bulle). Pas visible à l'écran ici — le
   texte était dans le `<svg>`, et du texte brut n'y est peint que dans un `<text>` —
   mais bien présent dans le DOM. Multi-lignes ⇒ `{% comment %}` obligatoire.
   Garde-fou : `tests/pytest/test_gabarits_commentaires.py`.
2. **Un shell copié est un instantané, et il périme.** `miete/shell.html` est une
   copie de `classic/shell.html`. Le socle y a ajouté `<link … tb-blocs.css>`
   **après** la copie ; le skin ne l'a pas suivi et a perdu, en silence,
   l'habillage de `.tb-etiquette` (défini uniquement dans ce fichier) — les
   étiquettes de l'agenda, de la carte d'événement et de la page événement
   retombaient en liens soulignés nus. **Un skin hérite du socle par le FALLBACK,
   jamais par les fichiers qu'il a copiés.** Corrigé.

---

## Comment tester (à la main) / Manual test

**Prérequis :** le skin n'est pas encore activable (choice absente, voir plus bas).
En attendant, les tests visuels passent par le bac à sable décrit en fin de fiche.

### Test 1 — activer le skin (après ajout de la choice par le mainteneur)
1. Admin du tenant → *Configuration du site* → *Thème graphique* → « MIETE ».
2. Ouvrir `https://lespass.tibillet.localhost/`.
3. Attendu : la nav affiche une bulle par entrée de menu, chacune d'une teinte
   différente, libellé noir au centre.

### Test 2 — le libellé est du VRAI texte (le cœur du chantier)
1. Sélectionner à la souris le texte d'une bulle → il se sélectionne.
   Si rien ne se sélectionne, le libellé est redevenu une image : régression.
2. Ctrl+F, chercher le libellé d'une bulle → le navigateur le trouve.
3. Inspecter la bulle → le `<svg>` porte `aria-hidden="true"`, le libellé est
   dans un `<span class="miete-bulle__libelle">`.

### Test 3 — le texte grossi fait grossir la bulle
1. Ctrl+**+** jusqu'à 200 %.
2. Attendu : la bulle grandit **entière**, dessin et libellé dans les mêmes
   proportions. Le texte ne doit jamais sortir du nuage.
3. Idem avec `about:preferences` → taille de police minimale (Firefox).

### Test 4 — clavier
1. Tab depuis le haut de la page → le **premier** arrêt est « Aller au contenu
   principal ». Entrée → le focus part sur le contenu, pas seulement la vue.
2. Tab sur une bulle → anneau de focus visible, net, **immédiat** (jamais d'animation).
3. La page courante : son libellé est **souligné** (pas seulement d'une autre couleur).

### Test 5 — contrastes forcés (le repli)
1. Windows : *Paramètres → Accessibilité → Thèmes de contraste* → activer.
   (Ou Chrome DevTools → Rendering → *Emulate CSS media feature forced-colors*.)
2. Attendu : les dessins **disparaissent**, le menu devient une liste de boutons
   bordés dans la palette de la personne. La page courante a une bordure épaisse.
3. Ce qu'il ne faut PAS voir : cinq aplats identiques et indistinguables.

### Test 6 — mouvement réduit
1. Activer « réduire les animations » dans l'OS.
2. Survoler une bulle : elle ne bouge plus, mais son libellé se souligne — on
   retire le mouvement, pas l'information.

### Test 7 — navigation HTMX (le piège)
1. Cliquer une bulle → la page change **sans rechargement**.
2. Attendu : la nav reste en bulles. Si elle repasse à la navbar du socle, c'est
   que `headless.html` n'est plus surchargé.

### Test 8 — le pont vers le socle (les pages CMS)
1. Ouvrir une page CMS du tenant (moteur de blocs).
2. Attendu : les titres de blocs sont en **Luciole**, pas en Georgia serif.
   Les boutons ont un rayon de **3px** (quasi-carré), pas 10px.
   L'accent est le vermillon, pas le bleu Bootstrap ni l'accent du socle.
3. DevTools → sélectionner `.tb-page` → onglet Computed → filtrer `--tb-` :
   `--tb-accent` doit valoir `oklch(53.4% 0.165 36.6)` et `--tb-police-titre`
   commencer par `'Luciole'`. Si c'est Georgia, le pont est cassé.
4. Sur `/event/`, les étiquettes doivent être **pastille + libellé en encre**
   (« ● Jazz »), pas des liens soulignés nus. Nues = `tb-blocs.css` n'est plus
   chargé par `miete/shell.html` (voir « pièges de copie »).
5. **Après toute vague du socle** : refaire ce test, ET comparer
   `diff <(grep -o '<link[^>]*>' pages/templates/pages/classic/shell.html) <(grep -o '<link[^>]*>' pages/templates/pages/miete/shell.html)`.
   Le shell est une copie : il ne suit pas le socle tout seul. Si le socle ajoute
   un jeton `--tb-*` sans point d'entrée `--skin-*`, le pont ne le connaît pas non
   plus et le skin héritera du défaut du socle.

### Test 9 — 320 px
1. DevTools → 320 px de large.
2. Attendu : les bulles s'empilent, **aucune barre de défilement horizontale**.

### Bac à sable visuel (sans activer le skin)
Reconstitue l'arbo de `collectstatic` et rend le skin dans Chrome — c'est ce qui
a servi à vérifier ce chantier (et à trouver deux bugs de débordement) :
```bash
W=~/.cache/miete-preview; R=$(pwd)
mkdir -p $W/miete/css $W/commun/font/luciole
cp $R/pages/static/miete/css/*.css $W/miete/css/
cp $R/BaseBillet/static/commun/font/luciole/*.woff2 $W/commun/font/luciole/
# puis une page qui charge miete/css/tokens.css + miete/css/miete.css
# et inclut le <svg> de partials/bulle.html dans un .skin-miete
google-chrome --headless=new --no-sandbox --screenshot=$W/rendu.png "file://$W/index.html"
```
> Chromium (snap) ne peut pas écrire la capture : utiliser `google-chrome`.

### Tests automatiques
`test_demarrer_skin.py` (3) + `test_gabarit_skin.py` + `test_handlers_erreur.py` (7) :
**10 passés**. Les 5 gabarits du skin compilent (`get_template`).

---

## Ce qui reste à faire / Remaining

1. **Activer le skin — mainteneur.** Ajouter la choice `("miete", "MIETE (…)")` à
   `pages.ConfigurationSite.skin` + la migration. Volontairement non fait :
   trois agents travaillaient en parallèle sur trois skins, et trois migrations
   concurrentes sur le même champ = graphe de migrations en conflit. À grouper.
2. **i18n.** Ce chantier ajoute des chaînes traduisibles (`Menu principal`,
   `Aller au contenu principal`, la mention Luciole). Le workflow i18n est à
   lancer par le mainteneur — `makemessages` n'a pas été lancé.
3. **La barre d'outils d'accessibilité — non tranché.** Le site d'origine en a
   une (Augmenter/Diminuer le texte, Niveaux de gris, Contraste négatif, Liens
   soulignés, Police lisible). Elle touche **toutes** les pages et demande des
   préférences persistées : ce n'est pas un skin, c'est un chantier à part.
   Deux de ses six boutons sont déjà sans objet ici : la « police lisible », c'est
   Luciole par défaut, et les liens sont soulignés par défaut.
4. **Le rythme reste un angle mort.** L'ADN a été extrait du HTML, pas d'une
   capture : la densité et l'asymétrie du site d'origine n'ont pas été lues.
   Une capture d'écran permettrait une passe de plus.
