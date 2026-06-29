# App `pages` — SPEC

> Document vivant. Synthèse de la session d'exploration (2026-06-28) et des
> décisions prises avec le mainteneur. Esprit commun numérique : on commence
> petit, on grandit par la demande réelle des gestionnaires.

## 1. Besoin

Les gestionnaires de lieux culturels veulent personnaliser leurs pages
(présentation du lieu, programme, liens, visuels) **sans développeur**, en
empilant des **blocs préfabriqués** édités dans l'admin Unfold. Le même
système doit pouvoir servir, à terme, la **landing publique TiBillet**
(`www.tibillet.localhost`, schéma `public`).

## 2. Décision stratégique : app maison

Écartés (cf. atom `18e0520c`) :
- **GrapesJS** : éditeur JS lourd, HTML opaque, hors ligne FALC/HTMX → abandonné.
- **Wagtail / django-cms** : admin séparé (× formation) ou conflit avec Unfold ;
  multi-site `django.contrib.sites` qui s'entrechoque avec django-tenants.
- **Ghost** : pas multi-tenant, memberships = doublon de Lespass/Fedow.

Retenu : **app Django maison `pages`**. Concept **StreamField** : une page est
une séquence ordonnée de blocs typés ; catalogue fermé de blocs → la page
reste toujours propre. Règle d'or : le StreamField sert au **contenu éditorial**,
jamais aux données critiques (SEO, dates, prix, IDs = champs de modèle).

## 3. Décisions d'architecture (verrouillées)

1. **App dédiée `pages`** en **`SHARED_APPS` + `TENANT_APPS`** (dual-list).
   - Pattern existant dans le projet : `wsocket` est dans les deux listes.
   - Conséquence : la table existe dans le schéma `public` ET dans chaque
     schéma tenant, **chaque schéma gardant sa propre copie isolée**.
   - SHARED-seul = pages partagées (bug) ; TENANT-seul = public sans pages ;
     **dual = public + isolation** ✅.
2. **`Bloc` édité en fiche standalone** avec `conditional_fields` **natif**
   Unfold (Alpine `x-show`). Vérifié en v0.87.0 : le natif gère les selects de
   chaînes (`type_bloc == 'HERO'`, `['HERO','CTA'].includes(type_bloc)`).
   - Le natif **ne marche pas en inline** (raison du JS custom existant pour
     les inlines `Price`). En éditant le bloc sur sa propre fiche, on utilise
     le natif → **zéro JS maison**.
3. **`Page`** porte un **inline léger** (`TabularInline`) : aperçu des blocs +
   `type_bloc`/`titre` + drag-drop d'ordre + lien « modifier » vers la fiche.
4. **Navbar** plate, globale au tenant : pages `publie=True` triées par
   `position` (inclusion tag `{% navbar_pages %}`).
5. **URLs** `/<slug>/` + **slugs réservés** (anti-collision avec routes existantes).
6. **CSS** : markup neutre `.tb-bloc*` dans l'app ; habillage par skin via CSS ;
   conforme **Hallmark** par défaut (cf. §7).

## 4. Modèles (`pages/models.py`)

### `Page`
| Champ | Type | Note |
|---|---|---|
| `uuid` | `UUIDField` PK | convention projet |
| `titre` | `CharField(200)` | libellé navbar |
| `slug` | `SlugField(200, unique=True)` | auto (`prepopulated_fields`), éditable, validé anti-réservés |
| `position` | `PositiveIntegerField(default=0)` | ordre navbar |
| `publie` | `BooleanField(default=False)` | hors-ligne tant que False |
| `meta_description` | `CharField(255, blank=True)` | SEO = donnée modèle |
| `created_at` / `updated_at` | `DateTimeField` auto | |

`Meta.ordering = ['position', 'titre']`.

### `Bloc` — modèle unique, champs plats (vague 1 : 0 JSON, 0 M2M)
- `uuid` PK · `page` FK→Page (`related_name="blocs"`, CASCADE) · `position` ·
  `type_bloc` (choices fermés : `HERO`, `PARAGRAPHE`, `IMAGE_TEXTE`, `CTA`, `TEMOIGNAGE`).
- Contenu : `titre`, `sous_titre`, `texte` (TextField WYSIWYG, **`clean_html`**),
  `image` (`StdImageField` + variations d'`Event`), `image_position` (GAUCHE/DROITE),
  `bouton_label`, `bouton_url`, `bouton2_label`, `bouton2_url`,
  `auteur_nom`, `auteur_role`, `auteur_photo` (`StdImageField`).
- `Meta.ordering = ['position']`.

### Matrice champ → type (pilote `conditional_fields`)
| Champ | HERO | PARAGRAPHE | IMAGE_TEXTE | CTA | TEMOIGNAGE |
|---|:-:|:-:|:-:|:-:|:-:|
| titre | ✓ | ✓ | ✓ | ✓ | |
| sous_titre | ✓ | | | ✓ | |
| texte | | ✓ | ✓ | ✓ | ✓ (citation) |
| image | ✓ (fond) | | ✓ (côté) | | |
| image_position | | | ✓ | | |
| bouton_label/url | ✓ | | ✓ | ✓ | |
| bouton2_label/url | ✓ | | | ✓ | |
| auteur_nom/role/photo | | | | | ✓ |

### Slugs réservés (schéma tenant)
Dérivés des routes `BaseBillet.urls` : `connexion, deconnexion,
emailconfirmation, infos-pratiques, le-faire-festival, event, memberships,
badge, federation, my_account, qrcodescanpay, qr, home, login,
specialadminaction` + `admin, api, static, media`.
(Le schéma public ajoutera les slugs `seo` : `lieux, evenements, recherche,
explorer` — traité en chantier 02.)

## 5. Admin (`pages/admin.py`, sur `staff_admin_site`)

- **`PageAdmin(ModelAdmin)`** : `compressed_fields`/`warn_unsaved_form=True`,
  `prepopulated_fields={"slug":("titre",)}`, `list_display=[titre, slug,
  display_publie, position, updated_at]`, `list_filter=[publie]`,
  `inlines=[BlocInline]`, `clean_slug` (réservés), 4 `has_*_permission` →
  `TenantAdminPermissionWithRequest`.
- **`BlocInline(TabularInline)`** : `fields=(type_bloc, titre)`,
  `ordering_field="position"` + `hide_ordering_field=True`, `show_change_link=True`,
  `extra=0`, 4 perms. **Aucun champ conditionnel → aucun JS.**
- **`BlocAdmin(ModelAdmin)`** : form `WysiwygWidget` sur `texte` ;
  `conditional_fields` natif (matrice §4) ; `save_model` → `sanitize_textfields`
  (clean_html). Enregistré (pour le lien « modifier ») mais **hors sidebar**.
- **Sidebar** : section dédiée « Pages » dans `get_sidebar_navigation`
  (`admin_tenant.py`), ungated en vague 1.

## 6. Rendu public (tenants, vague 1)

- Vue `pages.views.page_publique(request, slug)` : Page publiée sinon 404
  (preview staff autorisée) ; contexte via `get_context(request)` (réutilisé de
  `BaseBillet.views`) ; `pages/page.html` boucle `page.blocs.all()` →
  `{% include "pages/partials/bloc_<type>.html" %}`.
- URL : `path('', include('pages.urls'))` dans `urls_tenants.py` **après**
  l'include `BaseBillet.urls` ; `pages/urls.py` = `path('<slug:slug>/',
  page_publique, name='page_publique')`.
- Navbar : `{% navbar_pages %}` (inclusion tag `pages/templatetags/pages_tags.py`)
  dans le partial nav du skin.
- CSS `static/pages/css/tb-blocs.css`.

### Note schéma public (chantier 02)
Sur le schéma `public`, `Configuration` (TENANT_APP) **n'existe pas** → `get_context`
et le système de skins ne s'appliquent pas. Le rendu public passera par la base
`seo`, sans `Configuration`. C'est pourquoi le support public est un chantier
**isolé** après le socle tenant.

## 7. Règles anti-IA-moche (Hallmark) — câblées dans le CSS/templates par défaut

Principe : **variété structurelle**, pas seulement visuelle (éviter que tous les
sites des tenants se ressemblent). Tells bannis dans le CSS par défaut :
1. Pas de dégradé violet→rose en hero (une seule teinte d'accent).
2. Pairer deux polices (affichage + corps), jamais une seule.
3. Casser la symétrie (pas de tout-centré section après section).
4. Vraies icônes (bootstrap-icons), pas d'emoji-badge.
5. Boutons fond plein ou contour, pas de pilule en dégradé.
6. Pas de fausse chrome redessinée.
7. Pas de tag-gauche / titre-droite (eyebrow empilé vertical, ou OFF).

Discipline : jamais de chiffres inventés (le témoignage n'affiche que la saisie) ;
8 états interactifs (default/hover/focus-visible/active/disabled/loading/error/
success) ; responsive 320/375/414/768 (`overflow-x:clip`, `minmax(0,1fr)`,
`overflow-wrap:anywhere`) ; animer `transform`/`opacity` only + `prefers-reduced-motion`.

## 8. Découpage par vagues

- **Vague 1** (chantier 01) — socle mono-modèle, champs **plats** : Hero simple,
  Paragraphe riche, Image+texte, CTA, Testimonial. Admin + rendu tenant + tests.
- **Vague 1.5** (chantier 02) — support tenant public (admin public + cohabitation `seo`).
- **Vague 2** (chantier 03) — JSONField + M2M : galerie, carte+puces, FAQ, horaires.
- **Vague 3** (chantier 04) — pont métier : programme événements (API TiBillet) +
  bouton billetterie lié à un événement.

## 9. Contraintes transverses

- i18n : libellés `_()` source **FR** ; makemessages/compilemessages = mainteneur.
- a11y + `data-testid` partout.
- CHANGELOG.md + fiche `A TESTER et DOCUMENTER/`.
- **Aucune opération git** par l'assistant.
