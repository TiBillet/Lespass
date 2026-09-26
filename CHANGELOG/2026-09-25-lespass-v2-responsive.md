# Lespass (skin V2) : audit et corrections du responsive / Lespass (V2 skin): responsive audit and fixes

**Date :** 2026-09-25
**Migration :** Non

## Resume / Summary

**Quoi / What :** audit du site public du tenant `lespass` (skin V2) sur 15 pages, aux
largeurs 320, 375, 414, 768 et 1280 px, et dans les panneaux (réservation, adhésion,
connexion). Correction de tout ce qui sortait de l'écran, des cibles tactiles trop
petites, des champs qui font zoomer iOS, et des points de rupture. Correction d'une
erreur 500 sur `/event/embed/`.
/ Audit of the `lespass` public site (V2 skin): 15 pages at 5 widths plus the panels.
  Fixes for off-screen content, small touch targets, iOS-zoom inputs and breakpoints.
  Also fixes a 500 on `/event/embed/`.

**Pourquoi / Why :** `html` et `body` sont en `overflow-x: clip`. Un élément trop large
ne crée donc pas de barre de défilement : il est **coupé en silence**. Rien ne le
signalait, mais du contenu disparaissait :
- le pied de page était coupé à droite sur **toutes les pages** (104 px à 320 px, 49 px à 375 px) ;
- le bouton « Je veux réserver une ou plusieurs places » était coupé sur mobile et tablette ;
- les boutons des tunnels de réservation et d'adhésion étaient tronqués à 320 px ;
- sur `/contrib/`, le bouton « Voir plus de détail… » était coupé des deux côtés ;
- sur `/booking/<id>/resource/`, le sélecteur de ressource sortait de la carte ;
- sur `/federation/`, les titres des cartes s'écrivaient un mot par ligne ;
- le menu du lieu défilait en largeur sans aucun indice : « Agenda » et « Adhésions » restaient invisibles.

/ html/body clip overflow, so anything too wide was silently cut: footer on every page,
  booking CTA, tunnel buttons, contrib toggle, booking selector, federation cards, and a
  venue menu that scrolled with no visual hint.

Mesure avant / après (script Playwright, éléments visibles hors écran) :
- **avant :** 3 à 8 éléments coupés par page à 320, 375 et 414 px ;
- **après :** 0 sur les 15 pages et les 3 panneaux, aux 5 largeurs.

## Changements principaux / Main changes

1. **Pied de page.** Grille mobile en `minmax(0, 1fr)`. Un `1fr` nu prenait la largeur
   du plus long bouton. `.btn.btn--grad` retrouve `white-space: normal` (`.btn`, déclaré
   plus bas, l'écrasait). Marges réduites sous 30rem.
2. **Bouton « Réserver ».** Taille fluide (`clamp`) et retour à la ligne autorisé.
3. **Boutons sous 30rem.** `.btn` passe à la ligne au lieu d'être coupé. Cela couvre les
   tunnels, les boutons Bootstrap de `/contrib/`, et le pied du panneau. `<bs-counter>`
   peut rétrécir (« billet(s) » n'est plus coupé).
4. **Barre du haut.** Marges réduites sous 30rem. Sous 22.5rem, l'ancre
   « Connexion / Mon espace » est resserrée : le libellé tient en entier à 320 px
   (mesuré). Les points de suspension restent un filet de sécurité.
5. **Textes longs.** Nom du lieu, adresse web, e-mail, méta des cartes et tableaux du
   compte : `overflow-wrap: anywhere` et `min-width: 0`. La mini-carte du compte est
   bornée à la largeur de son cadre.
6. **Menu du lieu (M1) : sélecteur dépliant sous 48rem.** À 375 px, le ruban
   défilant d'origine ne montrait que 2 entrées sur 6 du menu de Lespass, sans
   indice. Sous 48rem, le menu en ligne est masqué. Il est remplacé par un
   `<details class="place-nav-mobile">`, sans JavaScript :
   - la ligne repliée fait 48 px et affiche « Menu · <page active> » ;
   - un toucher (ou Entrée au clavier) déplie toutes les entrées dans la carte du lieu ;
   - les sous-pages apparaissent en retrait, sans menu déroulant.

   Il utilise les mêmes données (`main_nav`) et la même règle de page active que
   le menu en ligne. Après un clic, HTMX remplace le `<body>` : la nouvelle page
   arrive avec le menu fermé. À partir de 768 px, rien ne change.

   Six options ont été comparées en maquettes mesurées : ruban défilant, rangées,
   liste verticale, sélecteur dépliant, priorité + « Plus », feuille du bas.
   Le sélecteur est retenu parce que le menu d'un lieu est libre (longueur et
   sous-pages choisies dans l'admin) : c'est la seule option qui tient sur une
   ligne dans tous les cas, sans script.
   Variante possible plus tard : des rangées quand `main_nav|length` vaut 4 ou moins.
7. **Cibles tactiles.** En `pointer: coarse`, 44 px minimum pour :
   - les liens du menu du lieu et du pied de page ;
   - les `.tag-pill`, les `.btn` et les `.dropdown-item` ;
   - la croix `.btn-close`.

   À la souris, rien ne change.
8. **Champs sous 16 px (zoom iOS).** Recherche de l'agenda, recherche de l'explorer et
   sélecteur de réservation passent à 16 px.
9. **Double gouttière.** Une `.container` imbriquée dans `main.container` ne rajoute plus
   de marge. Pages concernées : panier, 404, 500, QR code.
10. **Texte riche du lieu (`.event-prose`).** Coupure des mots longs. Vidéos, tableaux
    et code bornés à la colonne, tableaux larges défilants. Les listes retrouvent leurs puces.
11. **Boutons des blocs CMS.** `.tb-bloc__bouton` passe à la ligne sous 30rem (libellé
    saisi dans l'admin).
12. **`/federation/`.** Sous 30rem, le logo passe au-dessus, le titre prend toute la
    largeur, et badges et distance passent à la ligne.
13. **`/booking/<id>/resource/`.** Le sélecteur peut rétrécir. `.mobile-day` est borné
    à la largeur du conteneur.
14. **Hygiène :**
    - points de rupture de `V2.css` en rem, alignés sur `tb-blocs.css` (voir tableau ci-dessous) ;
    - `minmax(0, 1fr)` partout où un `1fr` nu restait ;
    - `flex-wrap` sur les pieds de cartes (événement, offre, initiative) ;
    - `dvh` avec repli `vh` (body, carte de `/federation/`), `.min-vh-100` retiré du `<body>` ;
    - tunnel en `100%` au lieu de `100vw` ;
    - texte minimum 12 px (pastilles de date, « FRANCE 2030 », créneaux, badges de l'explorer) ;
    - plancher de hauteur pour le carrousel (`max(33vh, 12rem)`), trop bas en paysage.
15. **Bug `/event/embed/` (500).** `embed()` ne posait pas `event_count`. Or
    `{% blocktrans count %}` exige un nombre. La vue remplit maintenant le même contexte
    que `list()` : `event_count`, `all_dates`, `all_tags`, `all_thematiques`. Les
    filtres par tag s'affichent donc aussi dans l'embed.

### Points de rupture / Breakpoints

| Avant | Après | Remarque |
|---|---|---|
| `max-width: 480px` | `30rem` | identique |
| `max-width: 720px` | `47.99rem` (767.84 px) | comme le `767.98px` de Bootstrap ; 721 à 767 px passent en mise en page mobile, 768 px (tablette portrait) garde sa grille à 2 colonnes |
| `max-width: 900px` | `62rem` (992 px) | aligné sur Bootstrap lg ; pied de page et bandeau d'accueil sur une colonne jusqu'à 992 px |
| `max-width: 1100px` | `68.75rem` | identique, seule l'unité change |
| `991.98px` / `992px` (explorer) | `61.99rem` / `62rem` | **exactement** le seuil de `explorer.js` (`innerWidth >= 992`) |
| tb-blocs `768px` | `48rem` | identique |

V2 reste pensé « ordinateur d'abord » (requêtes `max-width`). Une réécriture
« mobile d'abord » n'a pas été faite : elle toucherait tout le fichier, pour un gain
visible nul.

### Choix qui s'écartent de l'audit / Deliberate deviations

- **Panneaux latéraux larges de 400 px (C1 de l'analyse statique) :** pas de
  correction. Bootstrap 5.3 pose déjà `max-width: 100%` sur `.offcanvas`, c'était une
  fausse alerte, vérifiée en navigateur.
- **Libellé « Je veux réserver une ou plusieurs places » :** pas raccourci, pour ne pas
  toucher aux traductions. Correction en CSS seulement.
- **`{% block old_filter %}` dans `V2/vues/agenda.html` :** code mort, mais il contient
  les noms de blocs figés du contrat de skin (`agenda_carrousel`, `agenda_filtres`).
  Laissé en place : sa suppression est une décision d'architecture.
- **`<img>` sans `width`/`height` :** pas de correction. `commun/partials/picture.html`
  les pose déjà, sauf quand le fichier original manque (cas des données de dev). Les
  logos de l'explorer et des cartes de service sont dans des boîtes à taille fixe, donc
  sans décalage de mise en page.
- **Badges (`.badge`, `.tag-pill`) en `nowrap` :** laissés tels quels. Aucun débordement
  mesuré.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `pages/static/V2/css/V2.css` | Bloc « MOBILE ÉTROIT » en fin de fichier ; pied de page, bouton Réserver, sélecteur de menu mobile (`.place-nav-mobile`, remplace le ruban défilant), texte riche, champs 16 px, points de rupture, `minmax`, `flex-wrap`, `dvh` |
| `pages/templates/pages/V2/tenant_header.html` | Bloc `<details class="place-nav-mobile">` après le menu en ligne (même boucle `main_nav`) |
| `pages/static/pages/css/tb-blocs.css` | `.tb-bloc__bouton` peut passer à la ligne sous 30rem ; `768px` → `48rem` |
| `seo/static/seo/explorer.css` | Cartes lieu sous 30rem ; recherche 16 px ; `dvh` ; seuil aligné sur `explorer.js` ; badges 12 px |
| `booking/templates/booking/views/resource.html` | Sélecteur `min-width: 0` + 16 px ; `.mobile-day` borné ; textes 12 px |
| `BaseBillet/static/commun/css/tibillet.css` | `.offcanvas-tunnel` : `100vw` → `100%` |
| `pages/templates/pages/V2/shell.html` | `min-vh-100` retiré du `<body>` (remplacé par `min-height: 100dvh` dans V2.css) |
| `pages/templates/pages/V2/partials/carrousel_evenements.html` | Hauteur max `max(33vh, 12rem)` |
| `pages/templates/pages/V2/vues/evenement.html` | Hauteur max du carrousel `max(25vh, 10rem)` |
| `BaseBillet/views.py` | `EventMVT.embed()` : `event_count` et listes de filtres (corrige la 500) |
| `tests/pytest/test_pages.py` | Test `test_agenda_embed_rend_le_compteur_sans_erreur` |

Fichiers partagés par **tous** les skins : `tibillet.css`, `tb-blocs.css`,
`explorer.css`, `resource.html`, `views.py`. Les changements y sont neutres ou
bénéfiques pour `classic` et `faire_festival`.

### Migration
- **Migration necessaire / Migration required:** Non
- **Traductions :** aucune chaîne ajoutée ni modifiée.

## Tests a realiser / How to test

### Automatiques (passés le 2026-09-25)
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pages.py tests/pytest/test_gabarit_skin.py tests/pytest/test_gabarits_commentaires.py tests/pytest/test_membership_gabarits_attributs.py tests/pytest/test_admin_couleurs_gabarits.py -q
docker exec lespass_django poetry run pytest tests/pytest/test_event_create.py tests/pytest/test_events_list.py tests/pytest/test_event_retrieve.py -q
```

### Test 1 : pied de page (DevTools, 320 × 640 puis 375 × 667)
1. Ouvrir n'importe quelle page de https://lespass.tibillet.localhost/.
2. Descendre en bas : les trois boutons (don, créer un espace, contribuer) tiennent dans
   l'écran. « Créez un espace TiBillet pour votre collectif » passe sur deux lignes.

### Test 2 : page événement réservable
1. Ouvrir un événement avec réservation, à 320 px puis 768 px.
2. Le bouton noir « Je veux réserver une ou plusieurs places » est entier (3 lignes à 320 px).
3. L'ouvrir : dans le panneau, « billet(s) » est lisible à droite du compteur. Les
   boutons du bas passent à la ligne, sans icône qui sorte à gauche.

### Test 3 : menu du lieu à 375 px
1. Sur `/memberships/`, la carte du lieu affiche une ligne « Menu · Adhésions ».
2. La toucher : les 6 entrées se déplient dans la carte, et « Adhésions » est en gras.
3. Toucher « Agenda » : la page Agenda s'ouvre, le menu est refermé et affiche « Menu · Agenda ».
4. Au clavier (Tab puis Entrée), le menu s'ouvre et se ferme. L'anneau de focus est visible.
5. Sur la fiche d'un événement (page absente du menu), la ligne n'affiche que « Menu ».
6. Avec une page qui a des sous-pages (admin des pages) : elles apparaissent en retrait
   sous leur parent. **Non vérifié en navigateur** : Lespass n'a pas de sous-pages en dev.
7. À 768 px et plus : le menu en ligne habituel, sans changement.

### Test 4 : barre du haut à 320 px
1. Déconnecté : « Connexion » est écrit en entier, le bouton panier est entier.
2. Connecté : « Mon espace » est écrit en entier.

### Test 5 : pages hors skin à 320 px
1. `/contrib/` : « Voir plus de détail et les actions en cours » est entier (sur deux lignes).
2. `/booking/1/resource/` : le sélecteur de ressource reste dans la carte.
3. `/federation/` : dans chaque carte, le logo est en haut, le titre sur une ligne,
   badges et distance en dessous.

### Test 6 : agenda embarqué
1. Ouvrir `/event/embed/` : la page s'affiche (plus de 500), avec le compteur
   « N événements à venir » et les filtres par tag.

### Test 7 : cibles tactiles (DevTools, mode appareil tactile)
1. Les liens du menu du lieu, du pied de page, les filtres et la croix des panneaux
   font au moins 44 px de haut.
2. Même page à la souris (mode bureau) : la densité d'origine est gardée.

### Test 8 : entre 721 et 992 px (tablette)
1. À 740 px, la grille d'événements est sur une colonne (seuil 47.99rem, avant 720 px).
   À 768 px, elle reste sur 2 colonnes, comme avant.
2. Entre 900 et 992 px, le pied de page et le bandeau d'accueil passent sur une colonne
   (seuil 62rem, avant 900 px).
3. Valider que ce rendu tablette convient.

### Test 9 : à faire sur appareil réel (non vérifié ici)
- iPhone : pas de zoom en touchant la recherche de l'agenda et celle de `/federation/`.
- Carte de `/federation/` en vue carte : la hauteur suit la barre d'adresse (`dvh`).

---

## Correctif : en-tête du lieu et retour au lieu sur les pages « Mon espace » / Fix: venue header and back-to-venue link on account pages

**Quoi / What:** Sur toutes les pages `/my_account/*` (accueil ET sous-pages), l'en-tête du lieu
(`.place-header`) est masqué et le lien « ← nom du lieu » de la barre utilisateur est affiché.
Avant, le test comparait le chemin exact `/my_account/` : les sous-pages gardaient l'en-tête
et n'avaient pas le lien. / Prefix test on `/my_account/` instead of an exact match.

**Pourquoi / Why:** Les sous-pages du compte doivent se comporter comme son accueil.

| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/shell.html` | `request.path\|slice:":12" != "/my_account/"` |
| `pages/templates/pages/V2/headless.html` | Même test (réponses HTMX) |
| `pages/templates/pages/V2/partials/navbar.html` | Lien retour lieu : même test inversé + commentaire à jour |

**Migration :** Non.

### Test
1. Connecté, ouvrir `/my_account/balance/`, `/my_account/membership/`, `/my_account/preferences/`.
2. Pas d'en-tête du lieu ; le lien « ← nom du lieu » est dans la barre du haut, à côté de « Mon espace ».
3. Y arriver aussi par clic HTMX depuis `/my_account/` (rendu `headless.html`) : même résultat.
4. Sur `/` ou `/event/` : l'en-tête du lieu est là, le lien retour n'y est pas.
