# SEO des pages Ressources et Bénévolat / SEO of the Resources and Volunteering pages

**Date :** 2026-10-27
**Migration :** Non

## Resume / Summary
**Quoi / What :** les 4 pages `/booking/`, `/booking/<pk>/resource/`, `/booking/benevolat/` et
`/booking/benevolat/<slug>/` partagent enfin LEURS infos (titre, description, image) sur les
réseaux sociaux. Données structurées : fil d'Ariane (BreadcrumbList) sur les 4 pages. Pas de
Product sur une ressource : son tarif est horaire, souvent multiple, et invisible avant le clic
sur un créneau. Le sitemap déclare les 2 pages liste, chaque ressource et chaque planning publié
qui a un besoin à venir.
/ The 4 booking pages now share their own title, description and image. BreadcrumbList on all 4,
no Product (hourly, multiple, hidden prices). The sitemap lists both list pages, every resource
and every published planning with an upcoming need.

**Pourquoi / Why :** les blocs `og_*` et `twitter_*` n'étaient pas surchargés : toutes ces pages
partageaient « Accueil | lieu », la description du lieu et son image. Les données structurées
rendent les pages éligibles au résultat enrichi Google « fil d'Ariane ».
/ The og/twitter blocks fell back to the home ones. Structured data makes the pages eligible
for Google rich results.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `booking/templates/booking/views/resource.html` | blocs og/twitter (image de la ressource), meta description = nom si pas de description, fil d'Ariane |
| `booking/templates/booking/views/resources_list.html` | blocs og/twitter (alt = nom de la ressource illustrée), fil d'Ariane, h1 « Ressources » (comme le `<title>`) |
| `booking/templates/booking/benevolat/liste.html` | meta description, blocs og/twitter, fil d'Ariane |
| `booking/templates/booking/benevolat/planning.html` | meta description (présentation du planning), blocs og/twitter, fil d'Ariane |
| `booking/views.py` | `texte_brut_d_un_texte_riche` (pas de mots collés entre paragraphes) ; `list` : description de partage + image de la 1re ressource illustrée |
| `booking/views_benevolat.py` | `list` et `retrieve` : description de partage ; `retrieve` : `plusieurs_plannings_a_venir` pour le fil d'Ariane |
| `booking/benevolat.py` | `plannings_publies_avec_des_besoins_a_venir` (sitemap + fil d'Ariane) |
| `pages/templatetags/pages_tags.py` | nouvelle balise `jsonld_fil_ariane` (maillon de la liste omis quand elle redirige) |
| `pages/templates/cotton/V2/ressource_card.html` | lien « Réserver » + nom masqué pour les lecteurs d'écran |
| `booking/sitemap.py` (neuf) | `RessourceSitemap` (chaque ressource, module booking allumé) et `PlanningSitemap` (chaque planning publié avec un besoin à venir, module bénévolat allumé) |
| `BaseBillet/sitemap.py` | `booking-list` et `benevolat-liste` (à partir de 2 éléments, sinon la vue redirige) |
| `TiBillet/urls_tenants.py` | sections `ressources` et `plannings` du sitemap |
| `tests/pytest/test_seo_booking_benevolat.py` (neuf) | 12 tests |
| `tests/pytest/test_seo_maillage_sitemaps.py`, `test_sitemap_sections_vides.py` | isolement des nouvelles sections booking |

Aucune nouvelle chaîne traduisible : les libellés réutilisent des msgid existants.

---

## Comment tester (a la main) / Manual test

### Test 1 — carte de partage d'une ressource
1. Admin > Ressources : mettre une image sur une ressource.
2. Ouvrir sa page, afficher le code source (Ctrl+U).
3. `og:title` = « nom de la ressource | lieu », `og:image` = `….social_card.jpg` de la ressource.
4. Sans image : `og:image` = l'image du lieu.

### Test 2 — planning de bénévoles
1. Ouvrir `/booking/benevolat/<slug>/`.
2. `description`, `og:description` et `twitter:description` = début de la présentation du planning.
3. `og:title` = « nom du planning | lieu ».

### Test 3 — résultats enrichis
1. En prod, passer une page ressource et une page planning dans https://search.google.com/test/rich-results
2. Attendu : « Fil d'Ariane » détecté, sans erreur.
3. Avec une seule ressource (ou un seul planning à venir) : le fil n'a que 2 maillons (Accueil > la page).

### Test 4 — sitemap
1. `https://<lieu>/sitemap.xml` : `/booking/`, `/booking/benevolat/`, chaque `/booking/<pk>/resource/` et chaque `/booking/benevolat/<slug>/` publié.
2. Un planning désactivé (« Actif » décoché), ou sans aucun besoin à venir, n'y est pas.
3. Avec une seule ressource : `/booking/` n'y est pas (la page redirige vers la ressource).

### Verifs automatiques
- `make test ARGS="tests/pytest/test_seo_booking_benevolat.py"`
