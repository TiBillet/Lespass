# Migration Skins — État de reprise

**Dernière mise à jour :** 2026-07-04
**Statut : 🎉 MIGRATION TERMINÉE — les 8 chantiers sont faits (01→08).**
Le contrat de skin est publié : `CONTRAT-DE-SKIN.md` (v1.0, FIGÉ).
Reste côté mainteneur : commit + tests manuels des parcours fonctionnels
(fiche `A TESTER et DOCUMENTER/skins-chantiers-05-a-08-final.md`).
Assumé/documenté : les namespaces STATICS `static/reunion/…` et
`static/faire_festival/…` restent (seuls les templates ont migré).

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

## Décisions complémentaires VALIDÉES par le mainteneur le 2026-07-03 (ex-propositions P1-P5)

### P1 ✅ — Renommer `chrome/` → `commun/`
« Chrome » vient du jargon navigateur (*browser chrome* = tout ce qui entoure le
contenu : barres, menus). C'est opaque pour un non-anglophone — contraire au FALC.
Proposition : `BaseBillet/templates/commun/` avec un sens simple : **« partagé entre
tous les skins, non skinnable »**. Y regrouper le chrome du plan (modals, tunnels,
filtres) ET les partials déjà partagés de fait : `forms/contact.html`,
`forms/login.html`, `partials/toasts.html`, `loading.html`,
`views/event/partial/booking_form.html`.

### P2 ✅ — Dossier statics communs `BaseBillet/static/commun/`
Le check montre que la majorité de `static/reunion/` est **du commun déguisé** :
faire_festival charge `reunion/css/{bootstrap.min.5.3.3,bootstrap-icons.min,vars,
tibillet,swal}.css`, `reunion/js/{bootstrap.bundle,sweetalert2@11,theme-switcher,
language-switcher,membership-form,bs-counter}`, `reunion/img/{favicon,france_2030}.png`
(+ les polices via vars.css/tibillet.css). Il n'existe aucun dossier static commun
aujourd'hui. Proposition : déplacer ces fichiers vers `static/commun/` (CHANTIER-02),
mettre à jour les chemins dans les templates, relancer collectstatic.
Restent spécifiques reunion : qr-scanner, qrcode.min.js, booking-calculator.mjs,
form-spinner.mjs, htmx.min (chargé par reunion/base.html), media/ de démo.

### P3 ✅ — Règle d'autonomie des skins
Un skin ne référence QUE : (a) ses propres fichiers `pages/<skin>/…`, (b) le fallback
`pages/classic/…`, (c) le partagé `commun/…` (templates et statics). **Jamais un autre
skin.** Aujourd'hui faire_festival référence `reunion/` à 7 endroits (templates) +
17 endroits (statics) — c'est ça qui bloque la suppression de l'arbo reunion au
CHANTIER-08. On ne « supprime » donc pas `reunion/partials/…` : on **déplace vers
commun/** ce qui est partagé, vers `pages/classic/` ce qui est du socle skinnable.

### P4 ✅ — Pattern offcanvas unifié (méthode)
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

### P5 ✅ — Emails : hors skin, confirmé par le code
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
   trompeur (« send_welcome_email »). *(6-7-8 corrigés le 03/07 sur `main`.)*
9. **`seo.SEOCache` : course sur `update_or_create` sans contrainte unique**
   (`seo/tasks.py:282`) : deux exécutions concurrentes de `rebuild_seo_aggregates`
   (beat au démarrage + commande manuelle `refresh_seo_cache`) créent des doublons
   `(cache_type, tenant=None)` → tous les rebuilds suivants crashent en
   `MultipleObjectsReturned` (constaté au flush du 03/07 : 12 doublons, nettoyés à
   la main). **✅ CORRIGÉ le 03/07** : 2 `UniqueConstraint` partielles (PG13 ne
   supporte pas NULLS NOT DISTINCT) + migration de dédoublonnage
   (`seo/migrations/0005`). Vérifié par 2 refresh concurrents : 0 doublon.
Lacunes tests : aucun test parent-brouillon/enfant-publié, aucun test breadcrumb en
skin faire_festival, aucun test « accueil comme parent » via API.

## Prochaine étape
1. **CHANTIER-01 — EN COURS** (spec : `CHANTIER-01-RESOLVER-SHELL.md`) — resolver
   unifié `pages.services.gabarit_skin()` (ajout dans le `services.py` existant) +
   porter `reunion/base.html` → `pages/classic/shell.html` (+ faire_festival).
   Brancher `base_template` dessus. *Sécurité : iso-rendu tous tenants (snapshots
   curl avant/après).*
2. **CHANTIER-02 — TERMINÉ (lots A, B, C1 le 03/07 ; C2 le 04/07)** (`CHANTIER-02-EXTRACTION-COMMUN.md`) —
   Lot C2 : blocs `offcanvas_globaux` (contact+connexion en fin de body, retirés
   de la navbar) et `offcanvas` (tunnels de vue) dans classic/{shell,headless} ;
   exception ff-contact (CSS scopé) documentée dans le shell ff. Déplacement DOM
   pur vérifié par snapshots. —
   Lot B : 6 templates déplacés (dont `picture.html`, partagé avec crowds, ajouté au
   périmètre) — le skin faire_festival ne référence PLUS AUCUN template reunion.
   Lot C1 : 5 offcanvas extraits vers `commun/offcanvas/` (contact, connexion,
   adhesion_tunnel, reservation, filtres_agenda) + formulaire recherche →
   `commun/formulaires/recherche_evenements.html` + CSS largeur factorisé
   `.offcanvas-tunnel` dans tibillet.css (4 <style> inline supprimés). Unification
   des doublons reunion/ff : canonique = structure reunion + spinner ff dans le
   corps du tunnel d'adhésion ; titre 'Subscribe' (conditionnel mort
   `product.validate_button_text` retiré — product hors scope à cet endroit).
   **Lot C1 VÉRIFIÉ le 04/07** : 353 pytest + 64 E2E verts (0 échec), et parcours
   Chrome réels — les 5 offcanvas ouverts sur les 2 skins, vente Stripe CB 4242
   (adhésion 10 €), recharge tirelire en ligne (10 €), vente par QR code
   qrcodescanpay (5 € débités de la tirelire). NB : un run E2E précédent avait
   21 échecs → cause = runserver ASGI suspendu (tâche Channels tuée par le
   watchdog), redémarré via byobu ; aucun rapport avec les templates. —
   extraction du commun (templates + statics + offcanvas, cf. P1-P4) en 4 lots :
   A statics → `static/commun/`, B templates partagés → `commun/`, C1 extraction
   des 5 offcanvas → `commun/offcanvas/` (iso-bytes), C2 blocs dans les shells
   (iso-visuel). **Le point dur (60-70 % du risque).**
   NB seed : `demo_data_v2` branche désormais `charger_demo_faire_festival`
   (chantefrein) → chaque flush fournit les 2 skins de démo.

3. **CHANTIER-03 — TERMINÉ (04/07)** (`CHANTIER-03-AGENDA-EVENEMENT.md`) —
   agenda + détail événement → `pages/<skin>/vues/` (2 skins), 5 sites EventMVT
   sur `gabarit_skin()`, méthode `embed` corrigée (suit le skin du tenant),
   premiers blocs du contrat FIGÉS (agenda_*, evenement_*, carte_evenement),
   recherche → `commun/agenda/filtres.html`. Snapshots 0 diff, E2E verts.

4. **CHANTIER-04 — TERMINÉ (04/07)** (`CHANTIER-04-ADHESIONS.md`) — adhésions →
   `pages/<skin>/vues/adhesions.html` (2 skins), `embed` corrigé, 5 partiels
   HTMX du tunnel → `commun/adhesion/` (piège 9.8 respecté : partiels purs
   intacts), blocs FIGÉS adhesions_*. payment_*/formbricks restent pour le C6.

Puis CHANTIER-05 (accueil/infos/réseau),
06 (pages fonctionnelles → héritent du shell ; déplacer les templates email mal
rangés ; wizard/formbricks/reservation_ok), 07 (doc contrat + `demarrer_skin`),
08 (nettoyage `get_skin_template` + vieilles arbos).

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
- **`{# … #}` ne supporte PAS le multi-ligne** en Django : un `{#` non refermé sur
  la même ligne est rendu comme du TEXTE dans la page. Tout commentaire de plus
  d'une ligne = `{% comment %}…{% endcomment %}` (piège rencontré au lot C2,
  fuite de commentaires dans le HTML détectée par les snapshots).
- Le panneau contact de faire_festival vit DANS `.skin-faire-festival` (CSS du
  skin scopé sous cette classe) — le sortir changerait son look. Exception
  documentée dans le bloc `offcanvas_globaux` du shell ff.
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
