# CHANTIER 01 — Socle : `Page` + `Bloc`, 5 blocs plats, admin + rendu tenant

**Vague** : 1 · **Statut** : En cours · **Démarré** : 2026-06-28

## Objectif

Valider l'architecture `type_bloc` + `conditional_fields` natif **avant** toute
complexité de stockage (JSON/M2M). Livrer 5 blocs à **champs plats** :
Hero simple · Paragraphe riche · Image+texte · CTA · Testimonial. Édition dans
Unfold, rendu public sur les tenants réguliers.

## Périmètre (vague 1)

- ✅ Modèles `Page` + `Bloc` (champs plats) en dual-list.
- ✅ Admin : `PageAdmin` + `BlocInline` (léger) + `BlocAdmin` (conditionnel natif).
- ✅ Rendu tenant `/<slug>/` + navbar plate + templates neutres + CSS Hallmark.
- ✅ Tests pytest + doc.
- ❌ Hors périmètre : JSONField, M2M, pont billetterie, support **public**
  (chantier 02), surcharges CSS par skin (à la demande).

## Étapes

| # | Étape | Statut |
|---|-------|--------|
| 0 | Créer l'app `pages` + câblage `settings.py` (dual-list) | ✅ Fait |
| 1 | Modèles `Page` + `Bloc` + migration | ✅ Fait |
| 2 | Admin (PageAdmin + BlocInline + BlocAdmin) + sidebar | ✅ Fait |
| 3 | Rendu tenant (vue + urls + navbar via `main_nav`) | ✅ Fait |
| 4 | Templates + CSS Hallmark | ✅ Fait |
| 5 | Tests pytest + CHANGELOG + fiche A TESTER | ✅ Fait |

**Ajout en cours de route (demande mainteneur)** : drapeau `est_accueil` sur
`Page` + hook dans `BaseBillet.views.index` → une page peut être servie sur la
racine `/`. Management command `creer_page_demo` (page d'accueil démo avec les 5
blocs). Navbar via `main_nav` (pas de tag séparé). Validé visuellement dans Chrome.

## Fichiers attendus

**Créés :**
- `pages/__init__.py`, `pages/apps.py`, `pages/models.py`, `pages/admin.py`,
  `pages/views.py`, `pages/urls.py`
- `pages/templatetags/__init__.py`, `pages/templatetags/pages_tags.py`
- `pages/templates/pages/page.html` + `pages/templates/pages/partials/bloc_{hero,paragraphe,image_texte,cta,temoignage}.html`
- `pages/static/pages/css/tb-blocs.css`
- `pages/migrations/0001_initial.py`
- `tests/pytest/test_pages_models.py`, `test_pages_admin.py`, `test_pages_public.py`
- `A TESTER et DOCUMENTER/pages-vague1.md`

**Modifiés :**
- `TiBillet/settings.py` (`'pages'` dans SHARED_APPS + TENANT_APPS)
- `TiBillet/urls_tenants.py` (include `pages.urls` après BaseBillet)
- `Administration/admin_tenant.py` (import admin pages + section sidebar)
- `BaseBillet/templates/<skin>/partials/...nav` (pose `{% navbar_pages %}`)
- `CHANGELOG.md`

## Plan de tests (pytest DB-only)

- Modèles : création Page/Bloc, slug unique, **slug réservé rejeté**, ordering
  blocs par `position`, `clean_html` sur `texte` (strip `<script>`).
- Admin : `BlocAdmin` change form charge, `conditional_fields` présents,
  permissions `TenantAdminPermissionWithRequest`.
- Vue publique : page publiée rend les blocs ordonnés ; non publiée → 404 anon,
  200 staff ; **routes existantes (`/event/`…) non masquées** par le catch-all.

## Journal d'avancement

- **2026-06-28** — Spec + plan validés par le mainteneur. Chantier ouvert.
- **2026-06-28** — Vague 1 implémentée et validée dans Chrome. App `pages` créée
  (dual-list), modèles + 2 migrations, admin Unfold (conditional_fields natif
  confirmé visuellement : bascule Hero↔Témoignage OK), rendu public, 5 templates
  de blocs + CSS Hallmark, page d'accueil démo sur `lespass` (racine `/` rendue
  par la page avec les 5 blocs). 11 tests pytest passent. Bug corrigé en cours :
  commentaires `{# #}` multi-lignes → `{% comment %}`. Route `/event/` non masquée
  (vérifié). Reste : chantier 02 (support tenant public : admin + cohabitation seo).
- **2026-06-28 (ajouts mainteneur)** —
  (a) `est_accueil` sur `Page` : une page peut être servie sur la racine `/`
      (hook dans `BaseBillet.views.index`) ; la page d'accueil apparaît dans la
      navbar (titre + icône maison, → `/`).
  (b) `module_pages` sur `Configuration` + carte dashboard (activer/désactiver
      l'app) ; sidebar « Site web », navbar, rendu et page d'accueil gatés dessus.
  (c) **Skin déplacé** de `Configuration.skin` vers le **singleton**
      `pages.ConfigurationSite` (admin « Site web → Configuration du site »).
      Migration de données (copie par tenant, `chantefrein` faire_festival
      préservé). `get_skin_courant()` centralise la lecture. **Bascule
      reunion↔faire_festival vérifiée dans Chrome via le singleton.**
  Piège django-tenants : la migration de copie/retrait vit côté `BaseBillet`
  (tenant-only) et dépend de `pages.0003` (dual-list) — une migration `pages`
  ne peut pas dépendre d'une migration `BaseBillet` (insatisfiable sur public).
- **2026-06-28 (admin inversé + home auto)** —
  (a) **Admin inversé** : le Bloc devient l'objet principal (sidebar « Blocs »),
      type d'abord → conditional_fields, page en select avec boutons +/✎,
      auto-position. PageAdmin = métadonnées seules (inline supprimée).
  (b) **Page d'accueil auto** (`pages/services.py::construire_page_accueil`) :
      reproduit la home (HERO image+titre+sous-titre+boutons + PARAGRAPHE
      description longue). Migration `BaseBillet.0222` (tenants existants) + hook
      `TenantCreateValidator.create_tenant` (nouveaux tenants). Idempotent.
  (c) HERO avec image = carte sur la photo (fidélité home legacy).
  (d) Vérifié Chrome : chantefrein (module ON, faire_festival) home auto ≈ home
      legacy de le-coeur-en-or (module OFF). Skin per-tenant OK.
  (e) Migration skin durcie (anti-écrasement si champ déjà retiré).
