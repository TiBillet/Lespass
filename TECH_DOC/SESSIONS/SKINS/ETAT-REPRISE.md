# Migration Skins — État de reprise

**Dernière mise à jour :** 2026-07-03 (gros check complet du plan contre le code)
**Statut :** PLAN écrit — **aucun code**. En attente du go pour démarrer.

## Où on en est
- Le plan complet est écrit : `PLAN-MIGRATION-SKINS.md`.
- Option retenue : **B — migration complète** de tout le templating public vers
  `pages/<skin>/`, avec doc facile à lire et blocs bien identifiés.
- Les 3 décisions structurantes sont **verrouillées** (voir ci-dessous).
- **2026-07-03 : gros check effectué.** Toutes les références de code du plan sont
  exactes (lignes 107/124/167/2316/2679 de `BaseBillet/views.py`, `pages/views.py:57`).
  Le plan est implémentable tel quel. Écarts d'inventaire et propositions ci-dessous.

## Décisions prises (verrouillées)
1. **Skin par défaut = `reunion`** — inchangé. `pages/reunion/` n'existe pas → fallback
   `pages/classic/`. Le contenu `reunion/views/*` actuel **devient** le socle
   `pages/classic/`. Zéro migration de données.
2. **Nommage des blocs = FIXE**, documenté une seule fois au CHANTIER-07, versionné.
   Renommer après = casser les skins tiers → interdit.
   *(Extension proposée au check du 03/07 : les **ids des offcanvas** et de leurs corps
   cibles HTMX — `#loginPanel`, `#subscribePanel`, `#offcanvas-membership`… — font
   partie du même contrat : Bootstrap et HTMX y réfèrent en dur.)*
3. **Chrome non-skinnable par template** — pas de slots dans les modals/tunnels. Ils
   restent des includes partagés dans BaseBillet. Retouche visuelle d'un skin =
   **CSS global** uniquement (classes sémantiques). Décision réévaluable plus tard,
   mais **hors de ce chantier** (éviter d'alourdir le refacto).

## Propositions à valider par le mainteneur (check 2026-07-03)

### P1 — Renommer `chrome/` → `commun/`
« Chrome » vient du jargon navigateur (*browser chrome* = tout ce qui entoure le
contenu : barres, menus). C'est opaque pour un non-anglophone — contraire au FALC.
Proposition : `BaseBillet/templates/commun/` avec un sens simple : **« partagé entre
tous les skins, non skinnable »**. Y regrouper le chrome du plan (modals, tunnels,
filtres) ET les partials déjà partagés de fait : `forms/contact.html`,
`forms/login.html`, `partials/toasts.html`, `loading.html`,
`views/event/partial/booking_form.html`.

### P2 — Dossier statics communs `BaseBillet/static/commun/`
Le check montre que la majorité de `static/reunion/` est **du commun déguisé** :
faire_festival charge `reunion/css/{bootstrap.min.5.3.3,bootstrap-icons.min,vars,
tibillet,swal}.css`, `reunion/js/{bootstrap.bundle,sweetalert2@11,theme-switcher,
language-switcher,membership-form,bs-counter}`, `reunion/img/{favicon,france_2030}.png`
(+ les polices via vars.css/tibillet.css). Il n'existe aucun dossier static commun
aujourd'hui. Proposition : déplacer ces fichiers vers `static/commun/` (CHANTIER-02),
mettre à jour les chemins dans les templates, relancer collectstatic.
Restent spécifiques reunion : qr-scanner, qrcode.min.js, booking-calculator.mjs,
form-spinner.mjs, htmx.min (chargé par reunion/base.html), media/ de démo.

### P3 — Règle d'autonomie des skins
Un skin ne référence QUE : (a) ses propres fichiers `pages/<skin>/…`, (b) le fallback
`pages/classic/…`, (c) le partagé `commun/…` (templates et statics). **Jamais un autre
skin.** Aujourd'hui faire_festival référence `reunion/` à 7 endroits (templates) +
17 endroits (statics) — c'est ça qui bloque la suppression de l'arbo reunion au
CHANTIER-08. On ne « supprime » donc pas `reunion/partials/…` : on **déplace vers
commun/** ce qui est partagé, vers `pages/classic/` ce qui est du socle skinnable.

### P4 — Pattern offcanvas unifié (méthode)
Constat : 8 offcanvas publics, 0 modal. Incohérences relevées :
- Emplacement DOM : reunion définit `#loginPanel`/`#contactPanel` **dans le partial
  navbar** ; faire_festival les définit **dans base.html** + a déjà un
  `{% block offcanvas %}` (`faire_festival/base.html:238`) pour les tunnels de vue.
  → le pattern cible existe déjà côté faire_festival, c'est LUI le modèle du shell.
- CSS largeur (`--bs-offcanvas-width: 100vw` / `800px`) dupliqué inline dans ≥ 4
  fichiers (subscribePanel ×2, bookingPanel ×2).
- Classes/structure non uniformes (`offcanvas-start offcanvas` vs
  `offcanvas offcanvas-start text-bg-light`).
Méthode proposée (CHANTIER-02) :
1. Chaque offcanvas = un include `commun/offcanvas/<nom>.html`, coque normalisée
   (classes, header, bouton close, corps avec id stable cible HTMX).
2. Le shell expose deux blocs : `offcanvas_globaux` (login, contact — inclus par le
   shell lui-même) et `offcanvas` (rempli par les vues : booking, subscribe…), tous
   deux en fin de `<body>`.
3. CSS largeur factorisé dans `tibillet.css` (ex. classe `.offcanvas-tunnel`),
   suppression des `<style>` inline dupliqués.
4. Les ids restent EXACTEMENT ceux d'aujourd'hui (contrat, cf. décision 2 étendue).
Inventaire complet des 8 offcanvas (définitions, déclencheurs, cibles HTMX) : voir
rapport de session du 03/07 — `#contactPanel`, `#loginPanel`, `#subscribePanel`
(+corps `#offcanvas-membership`), `#bookingPanel`, `#filterPanel`, `#ticketPanel`
(+corps `#ticketPanelBody`), `#refundPanel`.

### P5 — Emails : hors skin, confirmé par le code
Les 3 templates email rangés sous `reunion/` (`views/qrcode_scan_pay/email/
payment_success_{user,admin}.html`, `views/tenant/emails/welcome_email.html`) font
tous `{% extends 'emails/base.html' %}` — **zéro dépendance au skin** (styles inline,
logo via variable `image_url`). Ils sont juste mal rangés. Action (CHANTIER-06 ou 08) :
les déplacer vers `BaseBillet/templates/emails/` + mettre à jour les 2 chemins dans
`BaseBillet/tasks.py:1988` et `:2026`. Les emails ne seront **pas** skinnables.

## Écarts d'inventaire à reporter au PLAN §2.2 (check 2026-07-03)
- **Méthodes `embed`** : l'agenda (`views.py:2322-2327`) et les adhésions
  (`views.py:2687-2693`) ont une méthode `embed` qui rend `reunion/views/…/list.html`
  **en dur**, doublon non skin-aware des vues skin-aware. Piège CHANTIER-03/04 :
  migrer `list` sans traiter `embed` casse les iframes.
- `views/event/reservation_ok.html` rendu en dur (`views.py:2531`).
- 4 partials account en dur : `reunion/partials/account/{card_table,token_table,
  transaction_history,badge_switch}.html`.
- 2 templates email dans `tasks.py` (voir P5) — hors `views.py`, faciles à rater.
- `pages/services.py` **existe déjà** (`grouper_blocs`, `construire_page_accueil`) :
  `gabarit_skin()` s'y **ajoute**, on ne crée pas le fichier.
- Le tunnel de réservation reunion est déjà dans un partial séparé
  (`reunion/views/event/partial/booking.html`, inclus par `retrieve.html:150`) —
  une partie de l'extraction CHANTIER-02 est déjà amorcée.

## Bugs découverts pendant le check (INDÉPENDANTS de la migration — à corriger à part)
Hiérarchie parent/enfant de `pages.Page` (audit complet 03/07) :
1. **Navbar — parent brouillon, enfant publié** (`BaseBillet/views.py:278-312`) :
   l'enfant publié disparaît totalement de la navbar (mais reste accessible et dans
   le sitemap) → page orpheline.
2. **Skin faire_festival — `pages/faire_festival/page.html` n'émet NI fil d'Ariane NI
   JSON-LD** (il réécrit `main` sans reprendre `extra_meta`/breadcrumb de classic).
   Perte SEO. *Leçon pour le contrat de skin : recommander `{% extends classic %}` +
   override de blocs plutôt que la réécriture complète d'un fichier.*
3. **Breadcrumb → parent brouillon** : `pages_tags.py:66` et `classic/page.html:46`
   pointent vers `/parent-slug/` sans tester `parent.publie` → lien 404.
4. **Règle « accueil ≠ parent » non appliquée hors formulaire** : elle n'existe que
   dans `limit_choices_to` ; `Page.clean()` ne la vérifie pas → contournable via
   api_v2 (`isPartOf`) et en cochant `est_accueil` sur une page qui a des enfants.
5. **Seeders sans `full_clean()`** : `charger_site_lespass.py:102-105`,
   `charger_demo_faire_festival.py:98` — la garantie « 1 seul niveau » n'est pas
   structurelle (pas de contrainte DB).
Autres (hors pages) :
6. `#ticketPanel` : bouton close avec `data-bs-dismiss="ticketPanel"` au lieu de
   `"offcanvas"` (`reunion/views/account/reservations.html:22`) — ne ferme pas.
7. `send_welcome_email` (`tasks.py:1691`) : jamais appelée + template
   `emails/welcome/welcome_email.html` **inexistant** (erreur avalée par try/except).
8. `membership_renewal_reminder` (`tasks.py:1769-1772`) : `return` DANS la boucle
   `for membership` → seul le premier adhérent reçoit la relance. Log copié-collé
   trompeur (« send_welcome_email »).
Lacunes tests : aucun test parent-brouillon/enfant-publié, aucun test breadcrumb en
skin faire_festival, aucun test « accueil comme parent » via API.

## Prochaine étape (au go)
1. **CHANTIER-01** — resolver unifié `pages.services.gabarit_skin()` (ajout dans le
   `services.py` existant) + porter `reunion/base.html` → `pages/classic/shell.html`
   (+ faire_festival). Brancher `base_template` dessus. *Sécurité : iso-rendu tous
   tenants.*
2. **CHANTIER-02** — extraction du chrome/commun (modals/offcanvas/filtres + statics
   communs, cf. P1-P4) vers `BaseBillet/templates/commun/` et `static/commun/`.
   **Le point dur (60-70 % du risque)** — à faire tôt, testable seul, zéro changement
   visible.

Puis CHANTIER-03 (agenda + détail événement — **inclut les méthodes `embed`**),
04 (adhésions — idem), 05 (accueil/infos/réseau), 06 (pages fonctionnelles → héritent
du shell ; déplacer les templates email mal rangés), 07 (doc contrat + `demarrer_skin`),
08 (nettoyage `get_skin_template` + vieilles arbos, possible seulement après P3).

## Pièges / rappels
- **Ne JAMAIS casser le skin `reunion`** (défaut, le plus utilisé). Tests Playwright
  agenda / adhésions / **tunnel de paiement** obligatoires avant de merger chaque chantier.
- **`tibillet.css` est chargé par les DEUX skins** (`faire_festival/base.html:77`) — un
  changement `.navbar`/global touche reunion ET faire_festival.
- **faire_festival n'est PAS autonome** : 7 includes de templates `reunion/…` +
  17 `{% static 'reunion/…' %}` (inventaire en P2/P3). Tout déplacement d'un fichier
  reunion doit vérifier les références croisées des deux côtés.
- Le champ `skin` vit sur `pages.ConfigurationSite` (singleton), lu par
  `get_skin_courant()` (`BaseBillet/views.py:107`). Défaut `"reunion"`, 2 choices.
- Deux systèmes **coexistent** pendant la migration (`get_skin_template` ancien +
  `gabarit_skin` nouveau) — pas de big-bang.
- Un template de vue surchargé intégralement par un skin peut « perdre » des blocs
  invisibles (SEO/JSON-LD) sans que rien ne casse visuellement — cf. bug n°2. Le
  contrat de skin devra pousser l'`extends` + override plutôt que la copie.
- Ne pas faire d'opération git ni de makemessages (mainteneur).

## Fichiers de référence (pour situer le code)
- `BaseBillet/views.py:107` `get_skin_courant`, `:124` `get_skin_template`, `:167`
  `get_context` (`base_template`), `:275-312` construction navbar (+ sous-pages),
  `:2256` agenda `list` (`:2316` render), `:2322` agenda `embed`, `:2657` adhésions
  `list` (`:2679` render), `:2687` adhésions `embed`.
- `pages/views.py:22` `rendre_page` (le render liste-de-templates est à `:57-59`).
- `pages/services.py` — existant : `grouper_blocs`, `construire_page_accueil`.
- Templates : `BaseBillet/templates/{reunion,faire_festival}/…` (à migrer),
  `pages/templates/pages/{classic,faire_festival}/…` (cible).
- Offcanvas : navbar reunion `partials/navbar.html:104-135` (contact+login),
  ff `base.html:201-238` (contact+login+block offcanvas), booking
  `reunion/views/event/partial/booking.html:75`, subscribe
  `reunion/views/membership/list.html:34`, filtres
  `reunion/views/event/partial/search.html:59`.
