# Relecture sécurité : filtre d'images de clean_html, corrections booking / Security review: clean_html image filter, booking fixes

**Date :** 2026-10-19
**Migration :** Oui — `booking/migrations/0008_resource_description_texte_d_aide.py` (texte d'aide seulement, aucune modification SQL).
`docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas booking`

## Resume / Summary
**Quoi / What :**
- **Sécurité** — `clean_html` lit l'adresse d'une image comme le navigateur la lira avant de refuser l'admin et la déconnexion. Les formes déguisées sont bloquées : `/%61dmin/`, `/./admin/`, `/%2e/admin/`, `../admin/`, `\admin/`, tabulation dans le chemin. Une image d'un texte riche public ne peut plus déclencher une action admin en GET (archiver, approuver) chez un admin connecté.
  / `clean_html` normalizes image paths before blocking admin/logout targets.
- Page ressource : la meta description n'est plus doublement échappée (`&` sortait `&amp;amp;`).
- Page Ressources : titre de l'onglet par défaut « Ressources » (comme le menu).
- Sélecteur de ressource et cartes : triés par nom de la ressource (plus par nom du produit).
- Cartes de ressource : le prix « À partir de … » s'affiche (il n'était jamais calculé). `data-testid` de la carte corrigé (`ressource-card-<pk>`, il était vide). En-tête de commentaire réécrit.
- `Resource.description` : libellé « Description » et texte d'aide exact (il parlait des adhésions).
- Spec `TECH_DOC/SESSIONS/EVENT_WIZARD/SPEC.md` §8.3 : décrit l'action de ligne `approuver_proposition`.
- Nouveaux tests : `tests/pytest/test_securite_textes_riches_et_personnalisation.py` (20 tests).

**Pourquoi / Why :** suite de la relecture sécurité et conformité djc des changements du jour. / Follow-up of the day's security and style review.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/utils.py` | `_attribute_filter` : décodage `%xx`, `\` → `/`, tabulations retirées, `..` refusé, normalisation du chemin |
| `booking/views.py` | Tri par `name` ; `price_min` des cartes (`list`) ; `meta_description_de_la_ressource` (`resource_page`) |
| `booking/templates/booking/views/resource.html` | Meta description lue dans le contexte |
| `booking/templates/booking/views/resources_list.html` | Titre par défaut « Ressources » |
| `pages/templates/cotton/V2/ressource_card.html` | En-tête de commentaire, `data-testid` par `pk`, classe JS morte retirée |
| `booking/models.py` + migration `0008` | Libellé et texte d'aide de `Resource.description` |
| `TECH_DOC/SESSIONS/EVENT_WIZARD/SPEC.md` | Action de ligne au lieu de l'action groupée |
| `tests/pytest/test_securite_textes_riches_et_personnalisation.py` | Nouveau : clean_html, XSS admin Resource, noms de menu échappés, textes d'intro, approbation refusée à un non-admin, alignement `_tableau` |
| `tests/pytest/test_seo_cache_fragments.py`, `test_event_proposal_admin.py` | Commentaires remis au présent |

---

## Comment tester (a la main) / Manual test

### Test 1 — images vers l'admin
1. Dans un texte riche de l'admin (description d'événement, de ressource…), insérer en mode source `<img src="/%61dmin/BaseBillet/event/">`.
2. Enregistrer : l'image n'a plus d'attribut `src`.
3. Une image ordinaire (`/media/...`, `https://...`) reste intacte.

### Test 2 — page Ressources
1. `/booking/` : titre de l'onglet « Ressources » (sans nom personnalisé), cartes triées par nom, « À partir de … € » sous chaque carte qui a un tarif en euros.
2. Page d'une ressource dont la description contient « & » : la balise `<meta name="description">` contient `&amp;` (une seule fois).

### Test 3 — admin Resource
1. La description s'appelle « Description », avec le nouveau texte d'aide.

### Verifs DB / Playwright
- `docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_securite_textes_riches_et_personnalisation.py -q` (20 verts ; vérifiés par mutation : sans le nettoyage de l'admin Resource ou sans le décodage `%xx`, 4 tests échouent).
- Périmètre élargi : 496 tests verts (booking, pages, newsletter, rapport comptable, exports, configuration).
