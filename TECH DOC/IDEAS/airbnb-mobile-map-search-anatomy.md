# Anatomie Design — Airbnb Search (Mobile + Desktop)

> Document de référence pour designers et développeurs.
> Déconstruction complète de l'interface de recherche Airbnb :
> composants, états, dimensions, gestes, tokens, transitions.


---

## Histoire d'inspiration

Tu ouvres Airbnb sur ton téléphone. Tu cherches Lyon. La carte apparaît, elle prend tout l'écran — c'est elle le personnage principal. Les rues de la Presqu'île, le Rhône, la Saône, les petits blocs de la Croix-Rousse. Et sur cette carte, des petites capsules blanches flottent : "89 €", "112 €", "67 €". Ce sont les pins. Chaque capsule est une annonce. Les plus petites, sans prix — des mini-ovales gris — c'est le second rang, les annonces moins susceptibles de t'intéresser. Airbnb les montre quand même pour que tu sentes la densité d'offre, mais elles ne crient pas.

En bas de l'écran, il y a une surface blanche. Pas tout à fait un écran, pas tout à fait un tiroir. C'est le bottom sheet. Il couvre peut-être la moitié basse de ton téléphone. En haut de cette surface blanche : une petite barre grise, horizontale, centrée. 36 pixels de large, 5 de haut. Discrète. C'est la poignée. Le drag handle. Elle te dit — sans un mot — "tu peux me tirer". C'est ce que Don Norman appelle un signifiant : un indice visuel qui communique une possibilité d'action. Tu n'as pas besoin de lire un tutoriel. Tu comprends.

Sous la poignée, tu vois deux ou trois cartes d'annonces. Une image quasi-carrée — ratio 20:19, un choix subtil, un poil plus large que haut — avec des coins arrondis à 12 pixels. En bas de l'image, une rangée de petits points blancs : les dot indicators du carrousel. Le point actif est blanc plein, les autres sont semi-transparents. Si l'annonce a plus de cinq photos, les points aux extrémités rétrécissent progressivement — de 6 pixels à 4, puis 2 — comme s'ils s'enfonçaient dans le brouillard. Ça te dit "il y en a encore" sans encombrer.

En haut à droite de chaque image, un cœur. Noir, avec un trait fin, transparent à l'intérieur. Si tu tapes dessus, il se remplit de rouge — le Rausch Red, `#ff385c`, nommé d'après la première adresse d'Airbnb à San Francisco — et il fait un petit rebond : il grandit, se rétracte, rebondit. 400 millisecondes. Ton iPhone vibre imperceptiblement sous ton pouce. Haptic feedback, impact léger.

---

Maintenant tu veux explorer la carte. Tu poses ton pouce sur la poignée et tu tires vers le bas. Le sheet descend. Pas brutalement — c'est une animation de ressort. Physique. Il y a de la masse, de l'amortissement. Le sheet ne s'arrête pas où tu le lâches. Il glisse jusqu'à un point d'ancrage : le peek state. Environ 120 pixels depuis le bas. Juste la poignée et le haut d'une image, coupée. Un teaser. La carte reprend 85% de l'écran. Tu peux explorer.

Tu fais glisser la carte vers le quartier de la Guillotière. Les pins bougent. Et là, un bouton apparaît — fondu enchaîné, 200 millisecondes — "Rechercher dans cette zone". C'est un pill blanc, texte noir, flottant au-dessus de la carte. Tu tapes. Les cartes en bas se transforment en squelettes gris avec un frisson lumineux qui les traverse — le shimmer effect — et deux secondes plus tard, les nouveaux résultats arrivent. Les pins se rafraîchissent sur la carte. Le bouton disparaît.

Tu tapes sur un pin "89 €". Il passe du blanc au noir, texte blanc, et grandit légèrement — `scale(1.08)`, 200 millisecondes. Le bottom sheet remonte. Pas au milieu, pas en haut. Il remonte en half state — 50% du viewport — et la liste scrolle automatiquement, doucement, jusqu'à la carte d'annonce correspondante. C'est ça le couplage bidirectionnel. Tu tapes un pin, la liste suit. Tu scrolles la liste, le pin s'illumine. Les deux représentations sont synchronisées. Comme deux musiciens qui s'écoutent.

---

Tu veux parcourir la liste. Tu tires la poignée vers le haut. Un flick rapide du pouce — ta vélocité dépasse 500 pixels par seconde — et le sheet ne s'arrête pas au half state, il saute directement en expanded state. 90% du viewport. La carte n'est plus qu'un liseré en haut de l'écran. La liste est maintenant scrollable. Tu fais défiler les annonces avec ton pouce.

Et c'est là que le moment technique le plus délicat se joue. Tu scrolles la liste vers le haut. Tu arrives en haut de la liste — `scrollTop === 0`. Tu continues à tirer vers le bas. Et à ce moment exact, quelque chose change. Le geste n'est plus "scroller la liste". Il devient "collapser le sheet". C'est le gesture handoff. Le transfert se fait sans saut, sans à-coup. Le scroll s'arrête, le sheet commence à descendre, dans le même mouvement continu. C'est invisible quand c'est bien fait. C'est catastrophique quand ça rate.

Le sheet retombe en half state. La carte réapparaît. Tu es de retour en mode exploration.

---

Maintenant, même scénario, mais sur ton ordinateur portable. Tout est différent.

Tu arrives sur la page de résultats. Pas de bottom sheet. Pas de poignée. L'écran est coupé en deux colonnes. À gauche, une grille de cartes d'annonces — deux colonnes, 18 résultats, séparés par 24 pixels de vide. À droite, la carte. Elle est collée dans sa colonne, `position: sticky`. Pendant que tu scrolles la liste à gauche, la carte ne bouge pas. Elle reste là, fidèle, avec ses pins.

La souris change tout. Tu n'as plus de pouce sur du verre. Tu as un curseur qui survole. Et le survol, le hover, n'existe pas sur mobile. C'est un sens supplémentaire.

Tu survoles une carte d'annonce à gauche. Sur la carte à droite, le pin correspondant passe instantanément au noir, grossit de 5%. Tu vois immédiatement où est l'annonce. Tu survoles un pin sur la carte. Après 200 millisecondes — un délai intentionnel pour éviter les faux positifs — un popover apparaît au-dessus du pin. Une mini-carte flottante : photo en 16:9, titre, note, prix. 300 pixels de large, coins arrondis à 12 pixels, ombre portée généreuse.

Tu déplaces ta souris du pin vers le popover. La souris traverse le vide entre les deux. Le popover devrait disparaître — ta souris a quitté le pin. Mais non. Il reste. Pendant 300 millisecondes, il attend. C'est le grace period. Si ta souris entre dans le popover avant la fin du délai, il survit. Si elle n'arrive pas, il s'efface. Ce détail — 300 millisecondes de patience — c'est la différence entre une interface qui se sent naturelle et une qui se sent nerveuse.

Tu cliques sur le pin. Le popover se "fixe". Il ne disparaît plus au hover-out. Il est pinned. Et à gauche, la liste scrolle doucement — smooth scroll — jusqu'à la carte correspondante. Tu cliques sur le popover : page détail.

---

Il y a un toggle en haut de la carte : "Search as I move the map". Si tu le coches, chaque déplacement de carte relance automatiquement la recherche. Pas immédiatement — il y a un debounce de 400 millisecondes. La carte attend que tu arrêtes de bouger. Puis elle envoie la requête. Les skeletons apparaissent dans la liste. Les nouveaux résultats arrivent. Les pins changent.

Si tu décoches le toggle, le comportement redevient celui du mobile : un bouton "Search this area" apparaît manuellement. À toi de décider quand relancer.

---

En bas de la liste, pas d'infinite scroll comme sur mobile. Des numéros de page. 1, 2, 3... 15. Airbnb a choisi la pagination classique sur desktop. Ça donne un sentiment de progression. Ça permet de revenir en arrière. Et surtout, ça permet au moteur de ranking de segmenter les résultats en pages cohérentes — les 18 meilleures annonces d'abord, puis les 18 suivantes.

Tu cliques sur "Page 2". Les cards changent. Les pins changent. La liste remonte en haut. C'est un nouveau jeu de 18 résultats. Et toi, tu continues à chercher un appartement dans Lyon, en survolant des pins et en tirant des poignées, sans jamais avoir lu un seul tutoriel.

---

C'est ça, le travail de design. Rendre invisible ce qui est complexe. Trois snap points, un gesture handoff, un grace period de 300 millisecondes, des ombres à trois couches, un debounce de 400 millisecondes. L'utilisateur n'en sait rien. Il tire, il tape, il survole. Et ça marche.



## 1. Vue d'ensemble — Deux paradigmes selon le breakpoint

L'interface de recherche Airbnb adopte deux patterns structurels radicalement différents selon la largeur d'écran :

**Mobile (< 744px)** : pattern **Map + Bottom Sheet**. La carte occupe 100% du viewport. Une surface glissante (bottom sheet) se superpose depuis le bas. Les deux représentations — carte et liste — se disputent le même espace vertical. L'utilisateur bascule entre les deux en tirant la poignée.

**Desktop (≥ 1128px)** : pattern **Split Panel (Master-Detail)**. La liste de résultats occupe la colonne gauche (~58% de la largeur), la carte occupe la colonne droite (~42%), les deux sont visibles simultanément. Pas de bottom sheet, pas de drag handle.

**Breakpoint intermédiaire (744px–1127px)** : la liste occupe toute la largeur. Un bouton toggle "Show map" / "Show list" permet de basculer entre les deux vues (une seule visible à la fois). C'est un **view toggle**, pas un split.

**Termes design** : *responsive breakpoint*, *adaptive layout*, *layout shift*, *split view*, *master-detail*.

---

## 2. Architecture Mobile — Couches (Z-Index Stack)

L'écran mobile est un empilement de 4 couches sur l'axe z (profondeur). Chaque couche a son propre rôle et ses propres interactions. Le z-index croissant va du fond vers l'utilisateur.

### Couche 0 — Map Layer (fond)

**Ce que c'est** : la carte interactive plein écran (Airbnb utilise un rendu basé sur Mapbox GL). Elle occupe `width: 100vw; height: 100vh` — tout le viewport, y compris la zone derrière le bottom sheet.

**Gestes supportés** :
- **Pan** (un doigt, glisser) : déplace la carte.
- **Pinch-to-zoom** (deux doigts, écarter/rapprocher) : zoom in/out.
- **Double-tap** : zoom in progressif.
- **Rotation** (deux doigts, pivot) : fait pivoter la carte (si activé).

**Contenu affiché** : les **map pins** (marqueurs) géolocalisés représentant les annonces, le fond cartographique (rues, bâtiments, parcs), et les labels géographiques.

### Couche 1 — Map Controls (overlay flottant)

**Ce que c'est** : les contrôles de carte superposés. Positionnés en `position: absolute` par rapport au conteneur carte.

**Éléments** :
- **Bouton "Rechercher dans cette zone"** (*search-this-area CTA*) : apparaît **uniquement après un déplacement manuel de la carte** (pan ou zoom). Positionné en haut ou au centre de la carte. Fond blanc, texte noir, border-radius pill (`border-radius: 999px`), ombre portée légère. Disparaît après tap (la recherche est relancée) ou après 5–8 secondes sans interaction.
- **Bouton de recentrage** (*current location button*) : icône flèche de localisation, cercle blanc, positionné en bas à droite de la carte, au-dessus du bottom sheet.

### Couche 2 — Top Bar / Search Bar (sticky header)

**Ce que c'est** : la barre de recherche compacte fixée en haut de l'écran.

**Structure interne** : c'est un **bouton déguisé en champ de recherche** (un `<button>` ou `<a>`, pas un vrai `<input>`). Le tap dessus ouvre un écran de recherche en plein écran (navigation push ou modal plein écran).

**Contenu affiché** :
- **Icône loupe** (search icon) à gauche, `16×16px`, couleur `#222222`.
- **Ligne 1 (titre)** : nom de la destination ("Lyon"), police Cereal VF weight 600, taille ~14px, couleur `#222222`.
- **Ligne 2 (sous-titre)** : résumé des critères ("1–7 mai · 2 voyageurs"), police Cereal VF weight 400, taille ~12px, couleur `#6a6a6a`.
- **Icône filtres** (sliders icon) à droite, dans un cercle bordé (`border: 1px solid #c1c1c1; border-radius: 50%`), diamètre ~36px. Le tap ouvre le panneau de filtres (modal bottom sheet plein écran).

**Dimensions** : hauteur totale ~56–64px (incluant padding vertical). La barre a un fond blanc, une ombre douce (`box-shadow: rgba(0,0,0,0.08) 0px 1px 2px`), et un `border-radius: 999px` (pill shape) sur la capsule centrale.

**Comportement sticky** : la barre reste visible au scroll de la liste (dans le bottom sheet en expanded state). Elle est positionnée sous la safe area iOS (encoche / Dynamic Island).

**Terme design** : *compact search bar*, *search pill*, *sticky header*, *action bar*.

### Couche 3 — Bottom Sheet (surface glissante)

C'est le composant central de l'expérience mobile. Il est détaillé dans la section suivante.

---

## 3. Le Bottom Sheet Mobile — Spécification complète

### 3.1 Définition et type

C'est un **non-modal persistent bottom sheet** :
- **Non-modal** : la carte derrière reste interactive. Pas de scrim (overlay sombre). L'utilisateur peut taper sur les pins même quand le sheet est visible.
- **Persistent** : le sheet ne peut jamais être complètement fermé. Il reste toujours au minimum en peek state. Il n'y a pas de geste pour le "dismisser" entièrement.

### 3.2 Surface visuelle

**Fond** : `background: #ffffff` (blanc pur).
**Coins** : `border-radius: 12px 12px 0 0` — arrondis uniquement en haut à gauche et en haut à droite. Les coins bas sont droits (le sheet touche le bord inférieur de l'écran).
**Ombre** : `box-shadow: rgba(0,0,0,0.10) 0px -2px 8px` — ombre projetée vers le haut (valeur y négative) pour créer une séparation visuelle avec la carte en dessous.
**Élévation** : le sheet est au-dessus de la carte (z-index supérieur), ce qui crée un **niveau d'élévation** au sens Material Design. L'ombre renforce cette perception de profondeur.

### 3.3 La Poignée (Drag Handle)

**Apparence exacte** :
- Forme : rectangle arrondi (capsule).
- Dimensions : `width: 36px; height: 5px`.
- Couleur : `background: #DDDDDD` (gris clair neutre).
- Coins : `border-radius: 2.5px` (demi-hauteur pour obtenir des extrémités parfaitement rondes).
- Positionnement : centré horizontalement (`margin: 0 auto`), à `8px` du bord supérieur de la surface du sheet.

**Zone de saisie tactile (hit target)** :
La barre visible ne fait que 36×5px — bien en dessous du minimum d'accessibilité de 44×44pt (Apple HIG) ou 48×48dp (Material Design). La zone réactive réelle est un rectangle invisible d'environ `width: 100%; height: 44px` centré sur la poignée. Tout le haut du sheet, y compris les quelques centimètres autour de la barre, est draggable.

**Rôle sémantique** :
- **Affordance visuelle** : la poignée est un **signifiant** (signifier, Don Norman) — elle communique visuellement que la surface est déplaçable. Sans elle, l'utilisateur ne saurait pas que le sheet est interactif.
- **Découvrabilité** (discoverability) : même un utilisateur novice comprend qu'on peut "tirer" cette barre grâce à la métaphore physique d'une poignée de tiroir.

**Accessibilité** : en VoiceOver/TalkBack, la poignée devrait avoir un `aria-label` de type "Redimensionner le panneau de résultats" et un rôle `slider` ou `adjustable`.

### 3.4 Les 3 Snap Points (Detents)

Le sheet s'ancre sur 3 positions prédéfinies. Chaque position est définie comme un **pourcentage de la hauteur du viewport** (ou une hauteur fixe en pixels sur certaines implémentations).

---

**SNAP POINT 1 — Peek State (état réduit)**

- **Hauteur** : ~120–160px depuis le bas de l'écran (soit environ 15–18% du viewport sur un iPhone standard 852px de haut).
- **Ce qui est visible** : la poignée + un espace de padding + exactement **la première card d'annonce tronquée** (on voit le haut de l'image, coupée). Le but est de montrer qu'il y a du contenu sous la poignée — c'est un **teaser** / **content peek**.
- **Carte visible** : ~82–85% du viewport. L'utilisateur a une vue quasi-complète de la carte avec tous les pins.
- **Interactivité carte** : 100% active (pan, zoom, tap sur pins). Le sheet ne gêne pas.
- **Interactivité liste** : pas de scroll possible. Le geste vertical dans le sheet contrôle uniquement le drag du sheet, pas le scroll de la liste.
- **Quand est-on dans cet état** : état par défaut après un déplacement de carte, ou après un flick vers le bas depuis le half state. C'est l'état "priorité carte".
- **Termes design** : *collapsed state*, *peek state*, *minimized detent*, *teaser state*.

---

**SNAP POINT 2 — Half State (état intermédiaire)**

- **Hauteur** : ~50% du viewport (environ 426px sur iPhone 852px).
- **Ce qui est visible** : la poignée + 2 à 3 listing cards complètes. La moitié supérieure de l'écran montre la carte avec les pins.
- **Carte visible** : ~50%. Suffisant pour voir les pins et maintenir un contexte géographique.
- **Interactivité carte** : active (mais la zone tactile est réduite à la moitié haute).
- **Interactivité liste** : le scroll vertical de la liste est **désactivé** ou **limité** — le geste vertical sur le contenu du sheet continue à contrôler le drag du sheet (pour passer en expanded ou retomber en peek). C'est un choix de **gesture prioritization** : le drag du sheet a priorité sur le scroll de la liste.
- **Quand est-on dans cet état** : état initial à l'arrivée sur l'écran de recherche. État intermédiaire entre exploration carte et exploration liste. Aussi l'état cible quand on tape sur un pin (le sheet remonte en half pour montrer la card correspondante).
- **Termes design** : *half-expanded state*, *mid detent*, *resting state*, *default state*.

---

**SNAP POINT 3 — Expanded State (état déployé)**

- **Hauteur** : ~85–92% du viewport. Le sheet laisse visible uniquement la search bar en haut + un liseré de carte (~60–80px en haut).
- **Ce qui est visible** : la poignée + la liste complète, scrollable.
- **Carte visible** : ~8–15%. Quasi-invisible. L'utilisateur ne peut plus interagir significativement avec la carte.
- **Interactivité carte** : quasi-nulle (zone trop petite pour un pan efficace).
- **Interactivité liste** : **le scroll vertical de la liste est actif**. C'est le seul snap point où la liste est scrollable. Le geste vertical contrôle le scroll de la liste, SAUF quand `scrollTop === 0` et que le geste est vers le bas (voir section "Gesture Handoff").
- **Quand est-on dans cet état** : après un flick vers le haut depuis le half state. C'est l'état "priorité liste" — l'utilisateur a choisi de parcourir les résultats plutôt que la carte.
- **Termes design** : *expanded state*, *full detent*, *maximized state*, *list-priority state*.

---

### 3.5 Transitions entre Snap Points

**Type d'animation** : **spring animation** (animation physique de ressort), pas un easing CSS classique (ease-in-out). La spring est paramétrée par :
- **stiffness** (rigidité) : contrôle la vitesse de retour vers le snap point (~300–500 dans les implémentations React Native / Reanimated).
- **damping** (amortissement) : contrôle le rebond. Une valeur haute (~80) donne un mouvement fluide sans oscillation. Une valeur basse donnerait un effet "bouncy".
- **mass** (masse) : généralement 1. Affecte l'inertie perçue.

**Velocity-based snapping** :
Le sheet ne va pas toujours au snap point le plus proche de la position actuelle. La **vélocité du geste au moment du relâchement** (onEnd) est prise en compte :
- Vélocité élevée vers le haut → snap au point supérieur, même si la position actuelle est plus proche du point inférieur.
- Vélocité élevée vers le bas → snap au point inférieur.
- Vélocité faible → snap au point le plus proche en distance.

**Seuils typiques** :
- Si `|velocityY| > 500 px/s` → snap dans la direction du geste (ignorer la proximité).
- Si `|velocityY| ≤ 500 px/s` → snap au point le plus proche.

**Over-drag resistance (rubber-band effect)** :
Quand le sheet est tiré au-delà du snap point max (vers le haut) ou min (vers le bas au-delà du peek), un **amortissement logarithmique** freine le mouvement. Formule typique : `overdragPosition = Math.pow(overdragAmount, 0.7)`. Plus on tire, plus la résistance augmente. Au relâchement, le sheet revient au snap point via une spring animation.

### 3.6 Gesture Handoff (résolution de conflit scroll ↔ drag)

C'est le problème technique le plus délicat du pattern. Quand le sheet est en expanded state, comment distinguer "l'utilisateur veut scroller la liste" de "l'utilisateur veut collapser le sheet" ?

**Règle implémentée** :

```
SI le sheet est en expanded state
  ET la liste est en scrollTop === 0 (tout en haut)
  ET le geste est un drag vers le BAS
ALORS → le geste contrôle le drag du sheet (collapse vers half ou peek)

SI le sheet est en expanded state
  ET la liste est scrollée (scrollTop > 0)
  ET le geste est un drag vers le BAS
ALORS → le geste scrolle la liste vers le haut (remonter dans la liste)

SI le sheet est en expanded state
  ET le geste est un drag vers le HAUT
ALORS → le geste scrolle la liste vers le bas (descendre dans la liste)

SI le sheet N'EST PAS en expanded state
ALORS → tout geste vertical = drag du sheet (pas de scroll de liste)
```

**Terme design** : *nested scroll coordination*, *gesture disambiguation*, *gesture handoff*, *scroll-to-drag transition*.

**Détail subtil** : lors du passage de "scroll de liste" à "drag de sheet" (quand scrollTop atteint 0 en scrollant vers le haut), il ne doit PAS y avoir de saut visuel. Le sheet doit commencer à descendre depuis exactement la position expanded, pas depuis une position arbitraire. Cela nécessite un **seamless gesture transfer** où le contexte du geste (position, vélocité) est transmis du scroll handler au drag handler sans interruption.

---

## 4. Les Map Pins — Spécification complète

### 4.1 Regular Pins (pins prix)

**Forme** : ovale horizontal (pill shape).
**Dimensions** : variable selon le prix affiché. Hauteur ~28–32px, largeur dynamique selon le texte (~50–80px).
**Style par défaut (default state)** :
- `background: #ffffff`
- `color: #222222` (texte du prix en Cereal VF weight 600, taille ~12px)
- `border-radius: 999px`
- `box-shadow: rgba(0,0,0,0.04) 0px 0px 0px 1px, rgba(0,0,0,0.18) 0px 2px 4px`
- `padding: 4px 8px`

**Style sélectionné (selected state — après tap)** :
- `background: #222222` (fond noir)
- `color: #ffffff` (texte blanc)
- `transform: scale(1.08)` (agrandissement léger)
- Transition : `transition: all 200ms ease-out`

**Style survolé (hover state — desktop uniquement)** :
- `background: #222222`
- `color: #ffffff`
- `transform: scale(1.05)`
- Apparition du **popover card** (voir section desktop).

**Style "visited"** : les pins dont l'annonce a déjà été consultée passent en gris atténué — `color: #6a6a6a`, ombre réduite. Cela aide l'utilisateur à distinguer les annonces déjà vues.

### 4.2 Mini-pins

**Forme** : petit ovale sans texte.
**Dimensions** : ~20×10px (nettement plus petit qu'un regular pin).
**Style** : `background: #ffffff; border-radius: 999px; box-shadow: rgba(0,0,0,0.18) 0px 1px 2px`.
**Comportement** : au hover (desktop), le mini-pin s'agrandit et révèle le prix — il se transforme temporairement en regular pin. Au tap (mobile), même comportement.
**Ratio de clic** : environ **8× inférieur** aux regular pins (donnée Airbnb Engineering, KDD'24).
**Rôle UX** : ils servent à indiquer la **densité d'offre** dans une zone sans surcharger visuellement la carte. C'est un compromis entre exhaustivité de l'information et lisibilité cartographique.

### 4.3 Clustering

À faible niveau de zoom (vue large), les pins proches sont regroupés en **clusters** :
- **Forme** : cercle.
- **Contenu** : un nombre (ex: "12") indiquant combien d'annonces sont regroupées.
- **Style** : similaire à un regular pin mais circulaire.
- **Comportement** : au tap ou au zoom in, le cluster éclate progressivement en pins individuels. L'animation est un **explode / scatter** — les pins se séparent depuis le centre du cluster vers leurs positions respectives.

---

## 5. La Listing Card — Spécification complète

### 5.1 Structure (du haut vers le bas)

**Image Carousel (conteneur images)** :
- **Ratio d'aspect** : `aspect-ratio: 20/19` (quasi carré, légèrement plus large que haut) sur mobile. Sur desktop, plutôt `aspect-ratio: 4/3` ou `3/2` (plus paysage).
- **Border-radius** : `border-radius: 12px` sur l'image (coins arrondis uniformes).
- **Object-fit** : `object-fit: cover` — l'image remplit le conteneur en rognant les bords si nécessaire.
- **Navigation mobile** : swipe horizontal. Snap à l'image la plus proche (`scroll-snap-type: x mandatory; scroll-snap-align: center`).
- **Navigation desktop** : flèches au hover.
- **Flèches de navigation (desktop uniquement)** : cercles blancs semi-transparents (`background: rgba(255,255,255,0.9); width: 32px; height: 32px; border-radius: 50%; box-shadow: rgba(0,0,0,0.08) 0px 1px 2px`) positionnés en `position: absolute; top: 50%; transform: translateY(-50%)` sur les côtés gauche (`left: 8px`) et droit (`right: 8px`). Contiennent un chevron SVG noir ~10px. Apparaissent **uniquement au hover** de l'image (`opacity: 0` → `opacity: 1` avec `transition: opacity 200ms ease`). La flèche gauche est masquée sur la première image, la flèche droite sur la dernière.
- **Dot Indicators (pagination par points)** : rangée de points centrée en bas de l'image, à ~8px du bord inférieur. Point actif : blanc plein (`background: #ffffff`). Points inactifs : blanc semi-transparent (`background: rgba(255,255,255,0.6)`). Dimensions par point : `width: 6px; height: 6px; border-radius: 50%`, espacement `gap: 4px` entre chaque. Si plus de 5 images, les dots éloignés rétrécissent progressivement (pattern **diminishing dots** — les dots aux extrémités passent de 6px à 4px puis 2px, créant un effet de fade-out spatial qui indique qu'il y a plus de contenu).

**Wishlist Button (cœur)** :
- Position : `position: absolute; top: 12px; right: 12px` par rapport au conteneur image.
- Icône : cœur SVG, trait noir avec remplissage transparent (état non-favori) ou remplissage `#ff385c` Rausch Red (état favori).
- Pas de fond visible, mais une ombre portée sur l'icône (`filter: drop-shadow(rgba(0,0,0,0.5) 0px 2px 4px)`) pour la lisibilité sur n'importe quel fond photo.
- Dimensions icône : ~24×24px. Hit target : ~44×44px.
- Animation au tap (ajout favori) : séquence rapide `scale(1) → scale(1.2) → scale(0.9) → scale(1)`, durée totale ~400ms, courbe `ease-out`. Haptic feedback (iOS, impact léger).

**Badge "Guest favorite"** (optionnel) :
- Position : `position: absolute; top: 12px; left: 12px`.
- Style : `background: #ffffff; color: #222222; font-size: 12px; font-weight: 600; padding: 4px 8px; border-radius: 14px; box-shadow: rgba(0,0,0,0.08) 0px 1px 2px`.

**Zone texte (sous l'image)** :
- **Padding** : `padding: 8px 0 0 0` (espace entre image et texte).
- **Ligne 1 — Titre et note** : `display: flex; justify-content: space-between; align-items: baseline`.
  - Gauche : nom de l'annonce ou localisation (ex: "Lyon 2e Arrondissement, France"). Cereal VF weight 600, `font-size: 15px`, couleur `#222222`. Tronqué à 1 ligne : `text-overflow: ellipsis; white-space: nowrap; overflow: hidden`.
  - Droite : note moyenne avec icône étoile noire (`#222222`) + note en Cereal VF weight 400, `font-size: 15px`. Ex: "★ 4.92".
- **Ligne 2 — Sous-titre** : type de logement, distance ou description courte. Cereal VF weight 400, `font-size: 14px`, couleur `#6a6a6a`. Tronqué à 1 ligne.
- **Ligne 3 — Dates** (optionnel) : "1–7 mai". Même style que ligne 2.
- **Ligne 4 — Prix** : "**89 € par nuit**". Nombre en Cereal VF weight 600, "par nuit" en weight 400. `font-size: 15px`, couleur `#222222`. Si le prix total est affiché en dessous, il porte un `text-decoration: underline`.

**Espacement entre cards** : `margin-bottom: 24px` (mobile, liste verticale) ou `gap: 24px` (desktop, CSS Grid). Aucun séparateur visuel — le negative space fait office de séparateur.

### 5.2 États interactifs de la card

| État | Déclencheur | Changement sur la card | Changement sur la carte |
|---|---|---|---|
| **Default** | — | Style normal | Pin en default state |
| **Hover** (desktop) | `mouseenter` | `cursor: pointer`, aucun autre changement visuel sur la card | Pin passe en selected (fond noir, `scale(1.05)`) |
| **Active** | `touchstart` / `mousedown` | `opacity: 0.95` transitoire | — |
| **Visited** | Retour depuis page détail | Titre : `color: #6a6a6a` | Pin : style visited (grisé) |

---

## 6. Couplage Carte ↔ Liste (Map-Bound Results)

### 6.1 Mécanisme de requête

Quand l'utilisateur déplace la carte, les résultats de la liste sont recalculés pour ne montrer que les annonces dans la zone visible. L'URL de la requête API contient les paramètres de **bounding box** :
- `ne_lat` / `ne_lng` : coordonnées du coin **nord-est** du viewport carte.
- `sw_lat` / `sw_lng` : coordonnées du coin **sud-ouest** du viewport carte.
- `zoom_level` : niveau de zoom actuel (affecte le nombre de résultats et le clustering).

Exemple réel (tiré de l'URL fournie) :
```
ne_lat=45.736148046169646
ne_lng=4.869130263158695
sw_lat=45.712658139606134
sw_lng=4.846134754327437
zoom_level=14.60678250688613
```

### 6.2 Deux modes de déclenchement

**Mode manuel (mobile + desktop opt-out)** : après un déplacement de carte, un bouton **"Search this area"** apparaît (fade-in, ~200ms). L'utilisateur tape pour relancer la requête. Le bouton disparaît après tap ou après 5–8s d'inactivité.

**Mode automatique (desktop opt-in)** : checkbox **"Search as I move the map"** en haut du panneau carte. Quand cochée, chaque déplacement relance la requête après un **debounce de ~300–500ms**. Quand la carte s'immobilise, le debounce expire et la requête part.

### 6.3 Cross-highlighting bidirectionnel

| Direction | Mobile | Desktop |
|---|---|---|
| **Liste → Carte** | Card visible au centre → pin highlighted | Hover sur card → pin en selected state |
| **Carte → Liste** | Tap pin → sheet remonte en half, scroll vers card | Click pin → popover fixé + smooth scroll vers card |

**Terme design** : *cross-highlighting*, *linked highlighting*, *two-way binding*, *coordinated views*.

---

## 7. Micro-interactions et Feedback sensoriel

### 7.1 Haptic Feedback (iOS)

| Événement | Type haptic | Style |
|---|---|---|
| Sheet atteint un snap point | `UIImpactFeedbackGenerator` | `.medium` |
| Wishlist toggle | `UIImpactFeedbackGenerator` | `.light` |
| Long press pin/card | `UIImpactFeedbackGenerator` | `.rigid` |

### 7.2 Skeleton Loading

Pendant le rechargement des résultats :
- Images → rectangles gris `#EEEEEE` avec `border-radius: 12px` et même `aspect-ratio`.
- Texte → barres grises arrondies `height: 12px; border-radius: 4px; background: #EEEEEE`.
- **Shimmer effect** : gradient animé `linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)` parcourant les skeletons en boucle, `animation: shimmer 1.5s infinite`.

### 7.3 Animations de pins

- **Apparition** : `scale(0) → scale(1.1) → scale(1)` avec **stagger delay** ~30ms entre pins (effet cascade).
- **Transition selected** : `transition: background-color 150ms ease, transform 150ms ease`.
- **Cluster explode** : pins se séparent depuis le centre vers leurs positions géographiques.

---

## 8. Vue Desktop — Split Panel

### 8.1 Layout global

```
┌──────────────────────────────────────────────────────────────┐
│  HEADER GLOBAL (logo + nav)                          ~64px  │
├──────────────────────────────────────────────────────────────┤
│  SEARCH BAR (pill, pleine largeur)                   ~64px  │
├──────────────────────────────────────────────────────────────┤
│  CATEGORY BAR (pills scrollables)                    ~76px  │
├──────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┬───────────────────────────────┐    │
│  │                      │                               │    │
│  │   RESULTS PANEL      │      MAP PANEL                │    │
│  │   (scroll Y indép.)  │      (position: sticky)       │    │
│  │   ~58% largeur       │      ~42% largeur             │    │
│  │                      │      top: ~204px              │    │
│  │   grille 2 colonnes  │      height: calc(100vh       │    │
│  │   gap: 24px          │        - 204px)               │    │
│  │   18 résultats/page  │                               │    │
│  │                      │                               │    │
│  │   pagination en bas  │                               │    │
│  └──────────────────────┴───────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 Header global (~64px)

Logo Airbnb (`#ff385c`) à gauche. Navigation droite : lien "Airbnb your home", globe (langue), menu hamburger circulaire avec avatar (cercle `border: 1px solid #c1c1c1; border-radius: 50%`).

### 8.3 Search Bar desktop (~64px)

Structure en **3 segments cliquables** dans une pill blanche `border-radius: 999px; box-shadow: rgba(0,0,0,0.08) 0px 1px 2px; border: 1px solid #DDDDDD` :

| Segment | Contenu | Largeur |
|---|---|---|
| "Where" (lieu) | Label gris + valeur saisie | ~34% |
| "Check in" / "Check out" | Deux sous-segments dates | ~22% chacun |
| "Who" (voyageurs) | Label + nombre + bouton recherche rouge | ~22% |

Les segments sont séparés par un `border-right: 1px solid #EEEEEE`. Au hover sur un segment : `background: #f2f2f2` (fond gris léger). Au click : ouverture d'un **popover de recherche** (dropdown élargi) qui prend toute la largeur de la search bar, avec les champs de saisie réels.

Le bouton recherche est un cercle rouge : `background: #ff385c; border-radius: 50%; width: 48px; height: 48px` contenant une icône loupe blanche. Au hover : `background: #e00b41` (Deep Rausch).

### 8.4 Category Bar (~76px)

Rangée horizontale de **chips illustrés** scrollables :
- Chaque chip : icône monochrome `24×24px` + label texte en dessous (`font-size: 12px; font-weight: 400; color: #222222`).
- Espacement : `gap: ~32px` entre chips.
- Item actif : `border-bottom: 2px solid #222222; font-weight: 600; opacity: 1`. Items inactifs : `opacity: 0.7`.
- Scroll horizontal avec **flèches circulaires blanches** (`width: 32px; height: 32px; border-radius: 50%; background: #ffffff; border: 1px solid #c1c1c1; box-shadow: rgba(0,0,0,0.08) 0px 1px 2px`) aux extrémités gauche/droite. Apparaissent au hover.
- Hauteur totale : ~76px incluant padding.

### 8.5 Results Panel (colonne gauche, ~58%)

**Grille** : CSS Grid, 2 colonnes en split view, 3 colonnes si carte masquée. `gap: 24px`. `padding: 0 24px`.
**Pagination** : 18 résultats par page (donnée Airbnb Engineering). Navigation en bas : « Précédent · 1 · 2 · 3 · ... · 15 · Suivant ». Style : cercles numérotés, page active en `background: #222222; color: #ffffff; border-radius: 50%`.
**Header compteur** : "Plus de 1 000 logements" — Cereal VF weight 400, `font-size: 14px`, `color: #222222`.
**Toggle prix total** : switch en bas de la grille. "Afficher le prix total (taxes et frais compris)".

### 8.6 Map Panel (colonne droite, ~42%)

**Positionnement** : `position: sticky; top: 204px; height: calc(100vh - 204px)`. Reste fixe pendant le scroll de la liste.
**Contenu** : carte interactive plein panneau. Mêmes pins que mobile.
**Overlay en haut à gauche** : checkbox "Search as I move the map" — `background: #ffffff; border-radius: 8px; padding: 8px 12px; box-shadow: rgba(0,0,0,0.12) 0px 2px 8px`.
**Overlay en bas à droite** : boutons zoom +/− empilés verticalement.

### 8.7 Map Popover (desktop uniquement)

Au hover ou click sur un pin, un **popover card** apparaît :

**Dimensions** : `width: ~300px; border-radius: 12px; box-shadow: rgba(0,0,0,0.12) 0px 6px 16px; background: #ffffff`.

**Structure** :
- Image miniature : `aspect-ratio: 16/9` (~300×170px), `border-radius: 12px 12px 0 0`, carrousel avec dots.
- Bouton fermer (×) : `position: absolute; top: 8px; right: 8px; width: 24px; height: 24px; background: rgba(0,0,0,0.5); border-radius: 50%; color: #ffffff`.
- Zone texte (sous l'image, `padding: 12px`) : titre (weight 600, 14px), note + avis (weight 400, 12px), prix (weight 600, 14px).
- Flèche de pointage CSS : triangle `8×8px` orienté vers le pin, positionné dynamiquement.

**Positionnement intelligent (edge-aware / flip behavior)** :
- Défaut : au-dessus du pin, flèche pointant vers le bas.
- Pin trop près du haut → bascule en dessous (flèche vers le haut).
- Pin trop à droite → décalage horizontal vers la gauche.

**Cycle d'interaction (hover-intent with grace period)** :

```
1. mouseenter pin        → timer 200ms avant apparition popover
2. 200ms écoulés         → popover apparaît (fade-in + scale)
3. mouseleave pin        → timer 300ms avant disparition
4. mouseenter popover    → timer 300ms annulé, popover reste
5. mouseleave popover    → timer 300ms, puis disparition
6. click pin             → popover "pinned" (persiste, ignore hover)
7. click ailleurs ou ×   → popover fermé, retour mode hover
```

Ce pattern empêche le popover de disparaître quand la souris traverse le vide entre le pin et le popover. Le **grace period de 300ms** est critique pour une expérience fluide.

---

## 9. Tokens du Design System Airbnb (DLS)

### 9.1 Typographie

| Usage | Weight | Taille | Couleur | Letter-spacing |
|---|---|---|---|---|
| Heading H1 | 700 | 26–32px | `#222222` | -0.44px |
| Heading H2 | 700 | 22px | `#222222` | -0.18px |
| Titre card | 600 | 15px | `#222222` | normal |
| Sous-titre card | 400 | 14px | `#6a6a6a` | normal |
| Prix | 600 | 15px | `#222222` | normal |
| Pin prix | 600 | 12px | `#222222` | normal |
| Search bar titre | 600 | 14px | `#222222` | normal |
| Search bar sous-titre | 400 | 12px | `#6a6a6a` | normal |
| Category chip (inactif) | 400 | 12px | `#222222` | normal |
| Category chip (actif) | 600 | 12px | `#222222` | normal |
| Badge | 600 | 12px | `#222222` | normal |

Police : **Airbnb Cereal VF** (variable font). Fallbacks : Circular, -apple-system, system-ui, Roboto, Helvetica Neue. OpenType feature `"salt"` (stylistic alternates) sur certains captions.

### 9.2 Couleurs

| Token | Hex | Usage |
|---|---|---|
| `--palette-bg-primary-core` | `#ff385c` | CTA principal, cœur favori rempli |
| `--palette-bg-tertiary-core` | `#e00b41` | CTA pressed/hover |
| `--palette-text-primary` | `#222222` | Texte principal, icônes |
| `--palette-text-secondary` | `#6a6a6a` | Texte secondaire |
| `--palette-text-focused` | `#3f3f3f` | Texte focus |
| `--palette-text-primary-error` | `#c13515` | Erreur |
| `--palette-border` | `#c1c1c1` | Bordures |
| `--palette-surface-secondary` | `#f2f2f2` | Fonds secondaires, hover |
| `--palette-surface-primary` | `#ffffff` | Fond principal |
| `--palette-bg-primary-luxe` | `#460479` | Tier Luxe |
| `--palette-bg-primary-plus` | `#92174d` | Tier Plus |
| `--palette-text-link-disabled` | `#929292` | Liens désactivés |
| `--palette-text-material-disabled` | `rgba(0,0,0,0.24)` | Texte désactivé |

### 9.3 Ombres

| Contexte | CSS `box-shadow` |
|---|---|
| Card listing (default) | `rgba(0,0,0,0.02) 0px 0px 0px 1px, rgba(0,0,0,0.04) 0px 2px 6px, rgba(0,0,0,0.10) 0px 4px 8px` |
| Card listing (hover) | `rgba(0,0,0,0.08) 0px 4px 12px` |
| Search bar | `rgba(0,0,0,0.08) 0px 1px 2px` |
| Map pin | `rgba(0,0,0,0.04) 0px 0px 0px 1px, rgba(0,0,0,0.18) 0px 2px 4px` |
| Map popover | `rgba(0,0,0,0.12) 0px 6px 16px` |
| Bottom sheet (vers le haut) | `rgba(0,0,0,0.10) 0px -2px 8px` |
| Bouton flèche carousel | `rgba(0,0,0,0.08) 0px 1px 2px` |
| FAB "Search this area" | `rgba(0,0,0,0.12) 0px 2px 8px` |

### 9.4 Border-radius

| Élément | Radius |
|---|---|
| Image de card | `12px` |
| Bottom sheet (haut) | `12px 12px 0 0` |
| Popover carte | `12px` |
| Boutons CTA | `8px` |
| Badge | `14px` |
| Search bar (pill) | `999px` |
| Pin de carte | `999px` |
| Pill de catégorie | `999px` |
| Bouton circulaire | `50%` |
| Drag handle | `2.5px` |

### 9.5 Espacements

| Contexte | Valeur |
|---|---|
| Gap grille desktop | `24px` |
| Marge entre cards mobile | `24px` vertical |
| Padding texte sous image | `8px 0 0 0` |
| Padding search bar | `8px 16px` |
| Padding category bar horizontal | `0 24px` |
| Padding top bottom sheet (au-dessus du handle) | `8px` |
| Padding entre handle et contenu | `16px` |
| Gap dot indicators | `4px` |
| Taille dot indicator | `6px` |
| Position wishlist button | `top: 12px; right: 12px` |
| Position badge | `top: 12px; left: 12px` |
| Position flèches carousel | `top: 50%; left: 8px` / `right: 8px` |

---

## 10. Tables d'interactions complètes

### 10.1 Mobile

| Geste | Zone | Action | Animation / Détail |
|---|---|---|---|
| Pan vertical ↕ | Drag handle | Drag du sheet entre snap points | Spring: stiffness ~400, damping ~80 |
| Flick up ↑ | Drag handle | Snap au point supérieur | Si velocityY > 500px/s : saute un snap |
| Flick down ↓ | Drag handle | Snap au point inférieur | Idem en inverse |
| Scroll vertical ↕ | Liste (expanded) | Scroll de la liste | Seulement si sheet en expanded |
| Drag down depuis scrollTop=0 | Liste (expanded) | Gesture handoff → collapse sheet | Seamless transfer, pas de saut |
| Swipe horizontal ↔ | Image card | Carrousel image suivante/précédente | scroll-snap-type: x mandatory |
| Tap | Pin carte | Sélection + scroll liste vers card | Sheet → half si était en peek |
| Tap | Card liste | Navigation push → page détail | Transition standard iOS/Android |
| Tap | "Rechercher ici" | Relance requête bounding box | Skeleton loading + pin refresh |
| Tap | Search bar compacte | Écran recherche plein écran | Navigation push/modal |
| Tap | Icône filtres | Panneau filtres (modal sheet) | Full-screen modal bottom sheet |
| Tap | Cœur wishlist | Toggle favori | scale bounce + haptic .light |
| Pan ↔ | Zone carte | Déplace la carte | Fait apparaître "Search this area" |
| Pinch ↔ | Zone carte | Zoom | Clustering adaptatif |
| Double-tap | Zone carte | Zoom in | Centre sur point tapé |

### 10.2 Desktop

| Interaction | Zone | Action | Animation / Détail |
|---|---|---|---|
| Hover | Card liste | Cross-highlight pin | Pin → fond noir, scale 1.05, 150ms |
| Hover | Pin carte | Popover card | Apparition après 200ms, fade+scale |
| Hover → popover | Pin puis popover | Popover reste | Grace period 300ms |
| Click | Pin carte | Popover pinned + scroll liste | Smooth scroll, popover persiste |
| Click | Card liste | Page détail | Nouvel onglet ou push |
| Click | Popover card | Page détail | Idem |
| Hover | Image card | Flèches ← → apparaissent | opacity 0→1, 200ms ease |
| Click | Flèche ← → | Image précédente/suivante | Slide horizontal |
| Scroll wheel | Results panel | Scroll liste | Indépendant de la carte |
| Pan (click+drag) | Map panel | Déplace la carte | Debounce 300-500ms si auto-search |
| Scroll wheel | Map panel | Zoom carte | Sur zone carte uniquement |
| Click | Checkbox auto-search | Toggle recherche auto | État persisté |
| Click | "Search this area" | Relance recherche | Si auto-search désactivé |
| Click | Pagination (numéro) | Charge page suivante | Pins mis à jour, scroll to top |

---

## 11. Comparaison structurelle Mobile vs Desktop

| Dimension | Mobile | Desktop |
|---|---|---|
| Pattern layout | Z-stack (couches verticales) | Split panel (colonnes horizontales) |
| Pattern carte/liste | Bottom sheet (dispute l'espace) | Dual panel (coexistence) |
| Drag handle | Oui (36×5px, affordance critique) | Non |
| Snap points | 3 (peek / half / expanded) | 0 |
| Scroll liste | Expanded state uniquement | Toujours actif |
| Hover | N'existe pas | Omniprésent |
| Popover pin | Non | Oui (300px, edge-aware) |
| Cross-highlight | Tap | Hover + click |
| Navigation images | Swipe | Flèches hover |
| Grille résultats | 1 colonne | 2 col (split) / 3 col (full) |
| Recherche carte | Bouton "Search this area" | Checkbox auto-search + bouton |
| Pagination | Infinite scroll | Pages (18 résultats) |
| Feedback sensoriel | Haptic (taptic engine) | Curseur + visuels |
| Carte | Derrière le sheet (z-index) | Sticky sidebar (position: sticky) |

---

## 12. Flux Utilisateur détaillés

### 12.1 Mobile — Exploration carte puis liste

1. **Arrivée** → carte plein écran + bottom sheet en **half state** (~50%). 2–3 cards visibles.
2. **Pan de la carte** vers un quartier → bouton "Rechercher dans cette zone" apparaît (fade-in 200ms).
3. **Tap bouton** → skeleton loading, requête API (bounding box), pins rafraîchis. Bouton disparaît.
4. **Drag poignée vers le bas** → sheet descend en **peek state**. Carte ~85% visible.
5. **Tap pin "89 €"** → pin passe en selected (noir). Sheet remonte en **half state**. Liste scrolle vers la card "89 €".
6. **Drag poignée vers le haut** → sheet en **expanded state**. Liste scrollable.
7. **Scroll liste** → pins correspondants highlighted au passage.
8. **Tap card** → push navigation vers page détail.
9. **Back** → retour à la recherche, sheet en expanded, même scroll position.
10. **Drag down depuis scrollTop=0** → gesture handoff → sheet collapse vers half.

### 12.2 Desktop — Exploration split view

1. **Arrivée** → split view : grille 2 colonnes (18 cards) à gauche, carte à droite (18 regular pins + N mini-pins).
2. **Hover card** → pin correspondant passe en selected (noir, scale up).
3. **Hover pin** → popover card après 200ms (image + titre + prix + note).
4. **Souris du pin vers le popover** → grace period 300ms maintient le popover.
5. **Click popover** → navigation vers page détail.
6. **Pan carte** avec auto-search → debounce 400ms → requête → cards rechargées (skeleton), pins mis à jour.
7. **Désactive auto-search** → pan → bouton "Search this area" apparaît.
8. **Click bouton** → reload résultats.
9. **Click pin** → popover pinned + smooth scroll liste vers card.
10. **Click "Page 2"** → 18 nouveaux résultats, pins changent, scroll to top.

---

*Document de référence — brief design, handoff dev, competitive audit, base de design system.*
