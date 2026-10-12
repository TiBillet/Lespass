# CHANTIER 09 — Canonical sans paramètres, noindex des copies, fiches fédérées

Origine : audit de l'accueil V2 du 2026-10-12
([AUDIT-ACCUEIL-V2/RECAP.md](./AUDIT-ACCUEIL-V2/RECAP.md), constats 2 et 4 ;
détail dans `plateforme.md` C1, C3, M5).

## Problèmes

1. **Canonical et `og:url` recopient la query string.** Les trois shells
   (`pages/templates/pages/{V2,classic,faire_festival}/shell.html`) utilisent
   `request.build_absolute_uri` (chemin ET paramètres). `/?utm_source=x`,
   `/event/?tag=y` se déclarent chacune canoniques : chaque lien tracké crée un
   doublon indexable. Les pages CMS surchargent déjà le bloc `canonical`
   (`page.html`), pas l'accueil par défaut ni l'agenda.
2. **Copies indexables.** `/event/embed/`, `/memberships/embed/` (mode `embed`)
   et `?skin_preview=<skin>` (aperçu d'un skin) sont servis en `index, follow`.
3. **Fiches événement fédérées dupliquées.** `EventMVT.retrieve`
   (`BaseBillet/views.py`) va chercher un événement inconnu chez les lieux
   fédérés et le rend sur le domaine du lieu qui l'affiche : 200, `index`,
   canonical sur lui-même. Le JSON-LD Event (`jsonld_event`) y annonce comme
   organisateur et comme lieu… le lieu qui affiche la page.

## Corrections

| # | Fichier | Changement |
|---|---|---|
| 1 | 3 × `shell.html` | `canonical` et `og:url` = `https://<host><chemin>`, sans paramètres. `og:url` passe par un bloc `og_url` pour qu'une page puisse le surcharger avec la même valeur que le canonical. `twitter:url` suit le chemin. |
| 2 | 3 × `shell.html` | `meta robots` = `noindex, nofollow` si `noindex_seo` (existant) **ou** `embed` **ou** `skin_preview`. |
| 3 | 3 × `vues/evenement.html` | Copie fédérée (`event_in_this_tenant` faux) : `canonical` et `og:url` = `event.full_url` (adresse sur le lieu d'origine, déjà stockée), `meta robots` = `noindex, follow`. |
| 4 | `pages/templatetags/pages_tags.py` (`jsonld_event`) | Pas de JSON-LD Event sur une copie fédérée (l'original le porte) ; sur l'original, `url` sans paramètres. |

Pas de migration, pas de vue modifiée : `embed`, `skin_preview`,
`event_in_this_tenant` et `event.full_url` existent déjà dans le contexte.

## Hors périmètre (noté)
- `?page=N` de l'agenda pointe aussi vers `/event/` : acceptable, les fiches
  sont découvertes par le sitemap.
- `?skin_preview=` reste accessible sans droit (plateforme.md M5) : le `noindex`
  couvre le SEO ; restreindre aux admins est une décision à part.

## Journal
- 2026-10-12 : spec écrite et implémentée. 10 tests (`tests/pytest/test_seo_canonical_doublons.py`),
  vérifiés par mutation ; tests voisins verts (`test_pages`, `test_seo_indexing`,
  `test_skin_preview_partiels`, fiches événement : 467 tests). Le commentaire du
  canonical passe en `{# #}` (n'est plus envoyé au navigateur).
  Reste : déployer, puis vérifier en prod (CHANGELOG/2026-10-12-seo-canonical-doublons.md).
