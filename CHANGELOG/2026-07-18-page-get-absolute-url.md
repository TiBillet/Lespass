# `Page.get_absolute_url()` — source unique de l'adresse d'une page / Single source of a page's URL

**Date :** 2026-07-18
**Migration :** Non

## Resume / Summary

**Quoi / What :** ajout de `Page.get_absolute_url()` dans l'app `pages`, et bascule des
**9 endroits** qui reconstruisaient l'adresse d'une page a la main. La regle « la page
d'accueil est servie sur la racine `/`, les autres sur `/<slug>/` » ne vit plus qu'a un
seul endroit.
/ Added `Page.get_absolute_url()` and switched the **9 places** that rebuilt a page's
address by hand. The rule "the home page is served on `/`, others on `/<slug>/`" now
lives in one place only.

**Pourquoi / Why :** la meme regle etait dupliquee dans le sitemap, la navbar, l'admin,
l'API v2, le JSON-LD et trois gabarits — avec le cas `est_accueil` reecrit a chaque fois.
C'est le lot A du CHANTIER 07 (`TECH_DOC/SESSIONS/PAGES/`), prerequis a la refonte du
moteur : sans cette centralisation, tout changement de forme d'URL demanderait neuf
corrections coordonnees.
/ The same rule was duplicated across the sitemap, navbar, admin, v2 API, JSON-LD and
three templates. This is lot A of CHANTIER 07, a prerequisite for the engine rework.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `pages/models.py` | Ajout de `Page.get_absolute_url()` + import `reverse` |
| `pages/sitemap.py` | `location()` delegue ; **suppression de code mort** (le `if obj.est_accueil` etait inatteignable, `items()` filtre deja `est_accueil=False`) ; import `reverse` devenu inutile retire |
| `pages/admin.py` | `display_voir` delegue |
| `api_v2/serializers.py` | `url` et `isPartOf.url` de `PageSchemaSerializer` delegues |
| `BaseBillet/views.py` | Navbar : URL de la page **et** URL des sous-pages du dropdown |
| `pages/templatetags/pages_tags.py` | `BreadcrumbList` JSON-LD : maillon parent |
| `pages/templates/pages/classic/page.html` | Fil d'Ariane visible |
| `pages/templates/pages/faire_festival/page.html` | Fil d'Ariane visible (skin festival) |
| `pages/templates/pages/classic/partials/bloc_liste_sous_pages.html` | Cartes de sous-pages (`href` + `hx-get`) |
| `pages/management/commands/charger_site_codecommun.py` | Commentaire : seul endroit qui ne peut PAS deleguer (voir ci-dessous) |
| `tests/pytest/test_pages.py` | 2 tests ajoutes (page normale, page d'accueil) |

### Le cas qui ne peut pas deleguer / The one case that cannot delegate

`charger_site_codecommun.py:440` construit encore `f"/{slug}/"` : a ce moment de la
commande on ne tient qu'une entree du manifeste (un `dict`), la `Page` n'existe pas
encore en base. Le lien est ensuite **fige dans le texte du bloc**. Consequence : si la
forme des URLs change un jour, cette commande devra etre adaptee **et rejouee**. Un
commentaire le signale sur place.
/ This one builds the address from a manifest dict before the Page exists; the link is
then frozen in the block text. Documented in place.

---

## Comment tester (a la main) / Manual test

### Test 1 — la page d'accueil pointe bien sur la racine

1. Aller sur `https://la-maison-des-communs.tibillet.localhost/`
2. Dans la navbar, l'entree de la page d'accueil doit pointer sur `/` (pas sur
   `/accueil/`). Verifier au survol ou par clic droit > copier l'adresse du lien.
3. L'icone de cette entree doit rester la maison (`house-door`).

### Test 2 — fil d'Ariane d'une sous-page

1. Ouvrir une sous-page (une page ayant un parent) du tenant.
2. Le fil d'Ariane affiche `Accueil › <parent> › <page courante>`.
3. Le lien du parent doit mener a `/<slug-du-parent>/` et fonctionner.
4. Si le parent est un brouillon (`publie=False`), le maillon parent **ne doit pas**
   apparaitre (comportement inchange).

### Test 3 — bloc « Liste des sous-pages »

1. Ouvrir une page portant un bloc `LISTE_SOUS_PAGES`.
2. Les cartes doivent pointer vers les bonnes adresses, et la navigation HTMX
   (`hx-get`) doit fonctionner sans rechargement complet.

### Test 4 — sitemap

```bash
curl -s https://la-maison-des-communs.tibillet.localhost/sitemap.xml?section=pages | head -30
```

Les pages publiees non-noindex sont listees en `/<slug>/`. La page d'accueil **reste
absente** de cette section (elle est deja listee comme `/` par `StaticViewSitemap`) —
comportement inchange.

### Test 5 — API v2

```bash
curl -s -H "Authorization: Api-Key <cle>" \
  https://la-maison-des-communs.tibillet.localhost/api/v2/pages/ | jq '.[0] | {url, isPartOf}'
```

Le champ `url` vaut `/` pour la page d'accueil, `/<slug>/` sinon. `isPartOf.url` suit la
meme regle.

### Verifs automatiques / Automated checks

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_pages.py \
  /DjangoFiles/tests/pytest/test_pages_api.py -q
```
