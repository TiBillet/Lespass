# App `pages` — Hub permanent

> 🟢 **REPRISE DE SESSION : lire `ETAT-REPRISE.md` en premier** — état complet,
> ce qui est fait, ce qui reste (notamment `infos-pratiques` à reproduire), pièges.

Constructeur de pages / landing pages par blocs préfabriqués, édité dans
l'admin Unfold. Point d'entrée unique pour toute personne (humain ou agent)
qui travaille sur l'app `pages`.

Décision stratégique : **app maison**, pas d'outil tiers (GrapesJS, Wagtail,
Ghost écartés — cf. SPEC.md). Concept fondateur : **StreamField** — une page =
une séquence ordonnée de blocs typés.

## Documents

- **SPEC.md** — Vision, décisions d'architecture verrouillées, modèles,
  admin, rendu, règles anti-IA-moche (Hallmark), et découpage par vagues.
- **CHANTIER-NN-*.md** — Specs actionables, une par chantier (contexte,
  design, fichiers, plan de tests, journal d'avancement).

## Chantiers

| # | Titre | Statut | Vague | Spec |
|---|-------|--------|-------|------|
| 01 | Socle : `Page` + `Bloc`, 5 blocs plats, admin + rendu tenant | En cours | 1 | [CHANTIER-01-socle-blocs-plats.md](./CHANTIER-01-socle-blocs-plats.md) |
| 02 | Support tenant public (admin public + cohabitation `seo`) | À faire (isolé) | 1.5 | _à créer_ |
| 03 | Blocs riches : galerie (M2M), carte+puces (JSON), FAQ, horaires | À faire | 2 | _à créer_ |
| 04 | Pont métier : programme événements + bouton billetterie | À faire | 3 | _à créer_ |
| 05 | API v2 pages : fabriquer un site via API (perm. clé + CRUD + catalogue) | Spec validée | 4 | [CHANTIER-05-api-v2-pages.md](./CHANTIER-05-api-v2-pages.md) |

## Décisions verrouillées (résumé — détail dans SPEC.md)

- **App dédiée `pages`**, en **`SHARED_APPS` ET `TENANT_APPS`** (dual-list,
  comme `wsocket`) → table isolée par schéma, **public inclus**, zéro fuite
  cross-tenant.
- **Édition** : `Bloc` en fiche standalone avec `conditional_fields` **natif**
  Unfold (gère le select `type_bloc`) ; `Page` avec inline léger (aperçu +
  drag-drop ordre). **Zéro JS maison.**
- **Navbar** plate : pages `publie=True` triées par `position`.
- **URLs** `/<slug>/` + liste de slugs réservés.
- **CSS** : classes sémantiques `.tb-bloc*` (markup neutre dans l'app),
  habillage par skin via CSS, conforme Hallmark par défaut.

## Source de réflexion

Atom Atomic `18e0520c-4b0b-423e-ba5b-fdfcc5c0708c` — section
« 📘 DOCUMENT DE TRAVAIL — App "Pages" maison TiBillet ». L'approche GrapesJS
décrite en première moitié de cet atom est **abandonnée** ; seule la section
maison fait foi.
