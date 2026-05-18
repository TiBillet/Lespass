# Changelog / Journal des modifications

## SEO Chantier 05 : carte explorer ROOT — 1 marker par PostalAddress / SEO Chantier 05: 1 marker per PostalAddress on ROOT explorer map

**Date :** 2026-05-17
**Migration :** Non (juste une nouvelle valeur dans CharField choices)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Refonte de la carte `/explorer/` du tenant ROOT. Avant :
1 marker par tenant (positionne sur Configuration.postal_address). Apres :
1 marker par PostalAddress active, avec popup riche listant le nom du lieu,
l'adresse, le tenant + un lien, et les 5 prochains events futurs.

**Pourquoi / Why :** Suite a l'import de 327 PostalAddress geolocalisees
(via outil nominatim-review), les tenants comme l'Universite Populaire de
Villeurbanne (24 lieux d'evenements differents) etaient invisibles. La carte
ROOT devient une vraie cartographie des lieux du reseau, pas juste des sieges.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/models.py` | +constante `SEOCache.AGGREGATE_POINTS` |
| `seo/services.py` | +`get_postal_addresses_for_tenants`, +`build_aggregate_points`, refacto `build_explorer_data_for_tenants` (retourne `{points, tenants}`) |
| `seo/tasks.py` | +Etape 6 dans `refresh_seo_cache` (ecriture `AGGREGATE_POINTS`) |
| `seo/views.py` | `explorer()` itere sur `explorer_data["tenants"]` pour federation JSON-LD |
| `seo/templates/seo/partials/explorer_widget.html` | Commentaires mis a jour |
| `seo/static/seo/explorer.js` | Boucle sur `state.data.points` (1 marker par PA), popup riche avec `events_futurs`, `state.markers` indexes par `pa_id` |
| `seo/static/seo/explorer.css` | +styles popup riche (.explorer-popup-address, -tenant, -logo, -events-list, -events-more) |
| `tests/pytest/test_seo_aggregate_points.py` | +6 tests unitaires (mocks, sans DB) |
| `tests/playwright/tests/35-explorer-markers-per-pa.spec.ts` | +2 tests E2E (structure JSON + markers visibles) |
| `TECH_DOC/SESSIONS/SEO/CHANTIER-05-explorer-markers-per-pa.md` | Spec |
| `TECH_DOC/SESSIONS/SEO/PLAN-05-explorer-markers-per-pa.md` | Plan d'implementation |

### Decisions cles / Key decisions
- **1 marker par PA** : popup riche listant tout (vs. markers superposes)
- **Filtre "tenant vivant"** : PA incluse si tenant a >=1 event futur OU >=1 produit publie
- **Cache dedie** `AGGREGATE_POINTS` : zero impact sur `AGGREGATE_LIEUX` (utilise par les autres vues `/lieu/<slug>/`, `/lieux/`, recherche)
- **Top 5 events** par popup + `events_futurs_count_total` pour afficher "+ N autres"

### Compatibilite / Compatibility
- `AGGREGATE_LIEUX` reste maintenu en parallele -> vues `/lieu/<slug>/`, `/lieux/`, recherche ROOT, JSON-LD federation continuent de fonctionner comme avant.
- **Activation** : prochain cycle Celery Beat de `refresh_seo_cache` (4h max), ou manuel :
  ```bash
  docker exec lespass_django poetry run python manage.py shell -c \
    "from seo.tasks import refresh_seo_cache; refresh_seo_cache()"
  ```


## SEO Chantier 01 : desindexer les instances DEV / DEMO / TEST / SEO Chantier 01: deindex DEV / DEMO / TEST instances

**Date :** 2026-05-17
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Les instances de dev / demo / test (filaos.re, devtib.fr)
etaient publiquement indexees sur Google et Bing alors qu'elles ne
devraient pas l'etre. Mise en place d'une regle metier simple :
`noindex, nofollow` (via `robots.txt` ET `<meta name="robots">`) quand
au moins un flag d'environnement est a `1` :
- `DEBUG=1` ou `TEST=1` ou `DEMO=1` ou `STRIPE_TEST=1`.

**Pourquoi / Why :** Aligne le projet sur le **Google AI Optimization
Guide** publie le 15 mai 2026 (cf. `TECH_DOC/SESSIONS/SEO/SPEC.md` et
Atomic atom `491b2fe3-049c-4b2d-86bf-ae2fc41b6b31`). Les instances dev
qui apparaissent dans la SERP volent la place du tenant principal sur
les requetes "TiBillet" et brouillent la marque. Une regle
supplementaire sur le host (DOMAIN / ADDITIONAL_DOMAINS) a ete
envisagee puis ecartee : redondante en pratique avec les 4 flags +
Django bloque deja les hosts inconnus via `ALLOWED_HOSTS`.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/seo_indexing.py` | NOUVEAU. Helper `should_noindex(request) -> bool` (regle metier complete, FALC bilingue) + context processor `noindex_context` |
| `TiBillet/settings.py` | +1 ligne dans `TEMPLATES.OPTIONS.context_processors` (`'TiBillet.seo_indexing.noindex_context'`) |
| `seo/views_common.py::robots_txt` | Branche sur `should_noindex(request)` : si True, sert `Disallow: /`. Sinon : `Allow: /` + sitemap |
| `BaseBillet/views_robots.py::robots_txt` | Meme logique cote tenant. Supprime imports inutiles (`connection`, `get_current_site`) |
| `seo/templates/seo/base.html` | Block `meta_robots` etend la logique : `noindex_seo` -> `noindex, nofollow`, sinon `index, follow` |
| `BaseBillet/templates/reunion/base.html` | Idem |
| `BaseBillet/templates/faire_festival/base.html` | Idem |
| `BaseBillet/templates/htmx/base.html` | NOUVEAU bloc `meta_robots` (n'en avait pas) + commentaire FALC bilingue |
| `tests/pytest/test_seo_indexing.py` | NOUVEAU. 5 tests unitaires : 4 flags d'env + 1 cas indexable |
| `TECH_DOC/SESSIONS/SEO/INDEX.md` | NOUVEAU. Hub du chantier SEO sur plusieurs sessions |
| `TECH_DOC/SESSIONS/SEO/SPEC.md` | NOUVEAU. Vision globale, principes Google 2026, etat actuel, anti-patterns |
| `TECH_DOC/SESSIONS/SEO/CHANTIER-01-noindex-dev.md` | NOUVEAU. Spec actionable de ce chantier |
| `A TESTER et DOCUMENTER/seo-noindex-dev.md` | NOUVEAU. Scenarios de test manuel |

### Migrations

- **Migration necessaire / Migration required :** Non

### Tests

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo_indexing.py --api-key dummy -v
# 5 passed in 0.27s
```

### Note importante

Pour faire desindexer effectivement filaos.re et devtib.fr (deja
presents dans la SERP), il faut **en plus** soumettre une demande
de suppression via Google Search Console + Bing Webmaster apres le
deploiement. Sinon Google peut mettre plusieurs semaines a les
oublier tout seul.

---

## Session marathon onboard + landing : hotfix prod + UX + i18n / Onboard marathon: prod hotfix + UX + i18n

**Date :** 2026-05-17
**Migration :** Oui (2 migrations)
**Contributeurs / Contributors :** JonasFW13 (Jonas) + Claude Opus 4.7

**Quoi / What :** Session multi-axes regroupant un hotfix prod critique
(PostalAddress lat/lng overflow sur les longitudes hors [-99, +99]),
plusieurs bugs UX du wizard onboarding (perte de session après login,
mailer en anglais non traduit, prénom/nom non répercutés sur l'user, long
description / logo non transférés au tenant, polling infini après erreur),
le polish de la landing root (4 nouvelles fonctionnalités + section
roadmap accordéon, JSON-LD WebSite + searchbox SERP, og:locale) et la
réécriture des deux templates email (OTP + ready) avec le wording riche
du flow legacy `/tenant/new/` adapté au contexte wizard.

**Pourquoi / Why :** Avant push prod. Sentry a remonté l'overflow lat/long
(création tenant cassée pour Asie / Pacifique / Amériques). Les autres
bugs étaient bloquants ou dégradants UX. La landing root manquait des
fonctionnalités différenciantes (open-data, AGPLv3, fédération) et n'avait
pas de roadmap visible pour engager la communauté.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | `PostalAddress.latitude/longitude` 18/16 → 9/6 (overflow longitude hors [-99, +99]) |
| `BaseBillet/migrations/0207_fix_postaladdress_latlng_precision.py` | NOUVEAU |
| `MetaBillet/models.py` | + champ `language` sur `WaitingConfiguration` (CharField max 10) |
| `MetaBillet/migrations/0016_add_wc_language.py` | NOUVEAU |
| `onboard/views.py::_finalize_otp_success` | + `_set_session_wc()` après login (perte session avec SESSION_SAVE_EVERY_REQUEST=True) ; + report `wc.first_name/last_name` sur user (si user n'a pas déjà ces champs) |
| `onboard/views.py` POST identity | + capture `get_language()` dans `wc.language` |
| `onboard/tasks.py::onboard_otp_mailer` | + `translation.override(wc.language)` autour du sujet + render templates |
| `onboard/tasks.py::onboard_ready_mailer` | idem + nouveau context var `instance_url` |
| `onboard/tasks.py::create_tenant_from_draft` | NOUVEAU bloc "3ter" transfert `wc.long_description` + `wc.logo` vers `Configuration.long_description` + `Configuration.img` (try/except sans re-raise pour préserver l'idempotence Celery, cf. piège #23) |
| `onboard/templates/onboard/steps/06_launch.html` | Fix polling infini : retrait `hx-trigger="load, every 2s"` du parent `#status` (le swap innerHTML ne touche pas les attributs du parent, donc le polling continuait après status_error) |
| `onboard/templates/onboard/emails/ready.html` | Réécrit avec wording riche du legacy `welcome_email.html` adapté au contexte post-création (bouton "ACCÉDER À MON ESPACE", liste "Informations importantes", section "Voici ce que vous pouvez faire", signature équipe coopérative) |
| `onboard/templates/onboard/emails/ready.txt` | Version texte cohérente |
| `onboard/templates/onboard/emails/otp_code.html` | Réécrit dans le style général (table imbriquée, palette `#009058`, Arial) ; capsule vert clair encadrée avec code PIN en `Courier New 36px` letter-spacing 12px |
| `onboard/templates/onboard/emails/otp_code.txt` | Réécrit |
| `seo/templates/seo/landing.html` | Philo réécrite (Code Commun + Ostrom) ; + 4 nouvelles cartes Fonctionnalités (Données ouvertes, Logiciel libre AGPLv3, Agenda participatif, Référencement et SEO) ; + nouvelle section roadmap `<details>` natif "Futur de TiBillet" (Newsletter, Réseaux sociaux, Fédiverse, Cascade) ; + `<h2 visually-hidden>` pour hiérarchie SEO |
| `seo/templates/seo/base.html` | + `<meta property="og:locale">` mappé `fr_FR` / `en_US` |
| `seo/views.py::landing` | Split JSON-LD en 2 blocs : Organization (`json_ld_org`) + WebSite/SearchAction (`json_ld`) pour éligibilité sitelinks searchbox SERP Google |
| `seo/static/seo/seo.css` | + section "ROADMAP / FUTURE" (~85 lignes) — accordéon stylé, chevron rotate, palette orange pour "futur" vs vert pour "actuel", `prefers-reduced-motion` respecté |

### Migrations

- **Migration nécessaire / Migration required :** Oui
- `BaseBillet/migrations/0207_fix_postaladdress_latlng_precision.py` — 2 AlterField sur PostalAddress (latitude, longitude) de DecimalField(18,16) à DecimalField(9,6). Compatible avec les données existantes (précision tronquée si > 6 décimales, aucune perte de range).
- `MetaBillet/migrations/0016_add_wc_language.py` — AddField `language` CharField(max_length=10, blank=True, default="") sur WaitingConfiguration.
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`

### Pièges documentés / Pitfalls documented

Voir `tests/PIEGES.md` section "Onboarding wizard (session 2026-05-17)" :
- DecimalField lat/lng : max_digits - decimal_places ≥ 3 obligatoire
- Polling HTMX : ne JAMAIS doubler `hx-trigger="every Xs"` sur parent + child
- `login()` peut perdre les clés de session avec `SESSION_SAVE_EVERY_REQUEST=True`
- `cron_morning` create_waiting_tenant fragile : `raise` global peut laisser le pool dans un état hybride
- gettext dans tasks Celery sans LocaleMiddleware → fallback `LANGUAGE_CODE`
- `wc.create_tenant()` ne transfère PAS automatiquement long_description, logo, ni first_name/last_name

---

## Widget de saisie d'adresse géolocalisée / Geolocated address input widget

**Date :** 2026-05-15
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What:** nouveau widget Django+Leaflet+leaflet-geosearch réutilisable
pour saisir une adresse (search live, marqueur draggable, géocodage inverse).
Refonte de la step 03_place du wizard onboard pour l'utiliser.
**Architecture full client** : recherche live ET reverse geocode appellent
Nominatim direct depuis le navigateur (pas de proxy serveur).

**Pourquoi / Why:** UX précédente (saisie en 4 champs séparés + géocodage HTMX
au change) trop friction. Pattern GPS standard (suggestions live + drag) plus
intuitif et réutilisable dans d'autres formulaires (Event admin, etc.).

**Décision architecturale 2026-05-15** : la spec initiale proposait une approche
"Hybride" (search client + reverse via endpoint serveur `/widgets/geocode-reverse/`
avec cache Redis). Bascule en **full client** après découverte d'un problème
multi-tenant routing : la route `BaseBillet/urls.py` n'est inclus que dans
`urls_tenants.py`, pas dans `urls_public.py` → 404 sur ROOT (où tourne le
wizard onboard). Plutôt que dupliquer l'URL dans 2 fichiers, on a supprimé
l'endpoint serveur et on appelle Nominatim direct (CORS open, déjà fait par
leaflet-geosearch pour le forward). Trade-off : pas de cache mutualisé, mais
acceptable pour notre volume.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `templates/widgets/widget_carte_adresse.html` | NOUVEAU — widget réutilisable |
| `static/widgets/widget_carte_adresse.js` | NOUVEAU — init IIFE multi-widget, fetch Nominatim direct |
| `static/widgets/widget_carte_adresse.css` | NOUVEAU — surcharges palette TiBillet |
| `BaseBillet/form_fields.py` | NOUVEAU — `AdresseGeolocaliseeField` helper (validation serveur) |
| `TiBillet/settings.py` | + `BASE_DIR / "templates"` dans TEMPLATES dirs, + `BASE_DIR / "static"` dans STATICFILES_DIRS |
| `onboard/templates/onboard/steps/03_place.html` | utilise le widget |
| `onboard/serializers.py` | `OnboardPlaceSerializer` : nouveaux champs `place_*` |
| `onboard/views.py` | mapping persistance + suppression action `geocode` |
| `onboard/urls.py` | suppression route geocode |
| `onboard/templates/onboard/partials/map_widget.html` | SUPPRIMÉ |
| `onboard/templates/onboard/partials/geocode_result.html` | SUPPRIMÉ |
| `tests/pytest/test_widget_form_field_geo.py` | NOUVEAU (6 tests `AdresseGeolocaliseeField`) |
| `onboard/tests/test_step_place.py` | adapté + suppression test endpoint geocode |

### Migration
- **Migration nécessaire / Migration required:** Non
- Pas de modification de schéma DB.

### Breaking changes
- Endpoint `POST /onboard/geocode/` supprimé. Aucun consommateur externe (uniquement utilisé en interne par l'ex-step 03_place).

## Chantier landing #04 — Filtre "lieu vivant" + UX "Voir tous" → explorer

**Date :** 2026-05-14
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Le cache SEO listait tous les tenants ayant un domaine, sans
verifier s'il y avait quelque chose a voir/acheter chez eux. En prod
avec 375 tenants, le marquee, `/lieux/`, la carte explorer et le
sitemap pointaient vers des dizaines de pages quasi-vides — bruit UX
et crawl budget gaspille pour Google + bots LLM.

1. **Filtre "lieu vivant"** sur `AGGREGATE_LIEUX` et `SITEMAP_INDEX` :
   un tenant n'apparait que s'il a un domaine ET (au moins 1 event
   futur publie OU au moins 1 produit BILLET/FREERES/ADHESION publie).
   Implementation : `seo/services.py::get_active_tenants_with_counts()`
   ramene `event_count` + `product_count` par tenant en 1 seule requete
   SQL (UNION ALL avec sous-selects scalaires). `seo/tasks.py` applique
   le filtre `lieu_est_vivant` avant de remplir `lieux` et
   `sitemap_tenants`. `TENANT_SUMMARY` / `TENANT_EVENTS` (caches
   per-tenant) restent inchanges.
2. **Chiffres cles supprimes** : "X lieux", "Y events" sur la landing
   — vanity metrics SaaS qui jurent avec le ton commun cooperatif. Bloc
   `stats-row` retire du template. `GLOBAL_COUNTS` n'est plus genere
   (suppression de `get_global_event_count()` dans `seo/services.py` et
   du bloc de generation dans `tasks.py`). Constante
   `SEOCache.GLOBAL_COUNTS` laissee dans `choices` pour eviter une
   migration de schema sur du code mort.
3. **UX "Voir tous"** : les 2 boutons sous les marquees pointent
   maintenant vers `/explorer/` (carte + filtres, vue interactive)
   plutot que `/lieux/` et `/evenements/`. Ces deux pages restent
   indexables pour le SEO/ranking mais ne sont plus mises en avant
   dans la navigation humaine.

**EN :** SEO cache listed every tenant with a domain, no check if there
was anything to see/buy there. In prod with 375 tenants, the marquee,
`/lieux/`, the explorer map and the sitemap pointed to dozens of
near-empty pages — UX noise and wasted crawl budget for Google + LLM
bots. Added an "alive venue" filter, removed vanity counters on the
landing, redirected "See all" buttons to `/explorer/` for humans.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/services.py` | `get_active_tenants_with_event_count()` → `get_active_tenants_with_counts()` (+ `product_count`). `get_global_event_count()` supprime. Constante `CATEGORIES_PRODUIT_LIEU_VIVANT = ("B","F","A")`. |
| `seo/tasks.py` | Filtre `lieu_est_vivant` sur `aggregate_lieux` + `sitemap_tenants`. Suppression du bloc `GLOBAL_COUNTS`. Log final reflete `lieux_vivants` au lieu de `lieux totaux`. |
| `seo/views.py` | `landing()` : suppression de `lieux_count`, `events_count`, lecture `GLOBAL_COUNTS`. |
| `seo/templates/seo/landing.html` | Bloc `stats-row` retire. 2 boutons "Voir tous" → `/explorer/`. |

### Migration / Migration
- **Migration necessaire / Migration required :** Non.
- Anciennes entrees `SEOCache(cache_type='global_counts')` deviennent du
  data mort, ignorees a la lecture. Nettoyage automatique au prochain
  refresh ? Non — la step 6 ne supprime que les entrees rattachees a un
  tenant disparu, pas les entrees globales obsoletes. Pas grave : 1 ligne.

## Chantier landing #03 — Marquee scalable + textes V2 + icone cashless + flush cache

**Date :** 2026-05-14
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**Quoi / What :** Quatre fixes sur la landing root `/` qui se voyaient
en prod avec 375 tenants ou apres un `flush`.

1. **Marquee "Nos lieux vivants" scalable** : la duree d'animation etait
   figee a 30s dans le CSS. Avec 6 lieux, vitesse ~41 px/sec (lisible).
   Avec 375 lieux, vitesse ~2580 px/sec (illisible, eclair). Fix :
   - `seo/views.py::landing()` calcule `marquee_lieux_duration_sec` pour
     viser ~40 px/sec constants.
   - Liste melangee aleatoirement (`random.shuffle`) a chaque chargement
     pour valoriser tous les lieux du reseau equitablement.
   - Plafonnee a 30 lieux pour ne pas alourdir le DOM (doublee par le
     `{% for copy in "ab" %}`).
   - `seo/static/seo/seo.css` consomme la duree via la CSS variable
     `--marquee-duration` (fallback 30s pour les autres pages).

2. **Textes V2 portes sur la landing** : hero title "Adhesion,
   billetterie, caisse enregistreuse et outils libres et federes"
   (etait "Lieux culturels, billetterie, outils libres et federes").
   Philosophie etoffee (encaisser au bar, boite a outils complete avec
   cashless/caisse/monnaie locale/budget contributif, "une seule carte
   pour plusieurs lieux"). Subheading features "Une solution complete"
   (au lieu de "Une boite a outils"). Source : prototype V2
   `../lespass-main/seo/templates/seo/landing.html`.

3. **Icone cashless invisible** : `bi-contactless` n'existe pas dans
   Bootstrap Icons 1.11.3. La feature card etait sans icone visible
   (width 0, `content: none`). Remplace par `bi-credit-card-2-front`
   (carte bancaire avec puce).

4. **Cache SEO ne se recharge pas apres `flush.sh` / `flush_dev.sh`** :
   la landing root affichait "0 lieux 0 events" tant que Celery beat
   n'avait pas tourne (toutes les 4h). Ajout de
   `python manage.py refresh_seo_cache` en fin de chaque script de flush.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `seo/views.py` | `landing()` : `random.shuffle`, cap 30 lieux, calcul `marquee_lieux_duration_sec` |
| `seo/templates/seo/landing.html` | Hero V2, philosophie V2, subheading V2, `bi-contactless` → `bi-credit-card-2-front`, `style="--marquee-duration: ...s"` sur la track |
| `seo/static/seo/seo.css` | `.marquee-content` lit `var(--marquee-duration, 30s)` |
| `flush.sh` | Ajout `manage.py refresh_seo_cache` apres collectstatic |
| `flush_dev.sh` | Ajout etape 6/6 `manage.py refresh_seo_cache` |

### Migration / Migration
- **Migration necessaire / Migration required :** Non
- Pas de nouvelle chaine `_()` ajoutee — les `{% translate %}` du hero
  V2 ("Adhesion", "billetterie,", "caisse enregistreuse") n'avaient pas
  d'entree dans les `.po`. **makemessages + compilemessages reportes**
  (le francais s'affiche correctement comme fallback).

## Chantier SEO #02 — Review critique + 10 fixes prod / Critical review + 10 prod fixes

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Review critique de la session SEO/FEDERATION par un agent + navigation
Chrome MCP. Score initial 79/100, 10 fixes appliques pour atteindre la qualite
prod :

1. **Critical XSS JSON-LD** : helper `json_for_html()` qui translate `<>&` en
   sequences unicode `< > &`. Empeche qu'un admin tenant qui met
   `</script>` dans son nom de configuration casse le HTML des pages de ses
   voisins (qui consomment le SEOCache).
2. **`<h1>` ajoutes** sur `/federation/` tenant et `/explorer/` public (etaient
   absents, 21+ H3 seulement). Visually-hidden, n'affecte pas l'UI.
3. **Open Graph + Twitter tags** : override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` sur le wrapper `/federation/`
   (etaient au fallback "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** dans settings.py : canonical URLs et JSON-LD
   contiennent maintenant `https://` (etaient en `http://` car Traefik forwarde
   en HTTP au container Django).
5. **N+1 cache landing** : `event_count` lu directement de `AGGREGATE_LIEUX`
   au lieu de 20 appels `get_seo_cache(TENANT_SUMMARY, ...)`.
6. **`_('Local network')`** : navbar label maintenant traduisible (etait
   hardcode).
7. **XML escape sitemap_index** : `xml.sax.saxutils.escape` sur les URLs et
   timestamps (defense en profondeur).
8. **BreadcrumbList shape** : `"item": {"@id": ..., "name": ...}` (forme
   recommandee Google Rich Results, au lieu du string brut qui passe les tests
   mais genere des warnings).
9. **`config.organisation or tenant.name`** : fallback si organisation vide.
10. **`CSS.escape()`** : remplace l'echappement regex maison dans explorer.js,
    avec fallback pour vieux navigateurs.

**EN :** Critical review of the SEO/FEDERATION session by an agent + Chrome MCP
navigation. Initial score 79/100, 10 fixes applied to reach prod quality:

1. **Critical XSS JSON-LD**: `json_for_html()` helper translating `<>&` to
   `< > &` unicode sequences. Prevents a tenant admin who puts
   `</script>` in their configuration name from breaking the HTML of neighbor
   pages (which consume SEOCache).
2. **`<h1>` added** on tenant `/federation/` and public `/explorer/` (were
   missing, 21+ H3 only). Visually-hidden, doesn't affect UI.
3. **Open Graph + Twitter tags**: override `og_title`, `twitter_title`,
   `og_description`, `twitter_description` on the `/federation/` wrapper
   (defaulted to "Accueil | <tenant>").
4. **`SECURE_PROXY_SSL_HEADER`** in settings.py: canonical URLs and JSON-LD
   now contain `https://` (were `http://` because Traefik forwards HTTP to
   the Django container).
5. **N+1 cache landing**: `event_count` read directly from `AGGREGATE_LIEUX`
   instead of 20 `get_seo_cache(TENANT_SUMMARY, ...)` calls.
6. **`_('Local network')`**: navbar label now translatable (was hardcoded).
7. **XML escape sitemap_index**: `xml.sax.saxutils.escape` on URLs and
   timestamps (defense in depth).
8. **BreadcrumbList shape**: `"item": {"@id": ..., "name": ...}` (Google Rich
   Results recommended shape, instead of raw string that passes tests but
   generates warnings).
9. **`config.organisation or tenant.name`**: fallback when organisation empty.
10. **`CSS.escape()`**: replaces homemade regex escaping in explorer.js, with
    fallback for legacy browsers.

**Validation** : tous les fixes verifies via curl + Chrome MCP. Helper
`json_for_html()` teste avec input malicieux (`Foo</script><script>alert(1)`)
→ tous les caracteres dangereux echappes.

---

## Chantier SEO #01 — Decouverte LLM/Google du reseau federe / LLM and Google discovery of the federated network

**Date :** 2026-05-13
**Migration :** Oui (`seo/0002_alter_seocache_cache_type.py`)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Trois axes pour rendre le reseau TiBillet visible aux LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) et a Google.

1. **Voisins bidirectionnels** : la carte d'un tenant affiche les voisins
   declarations dans les 2 sens. Si X federate avec moi mais que je n'ai pas
   declare X dans mes `FederatedPlace`, X apparait quand meme. Pre-calcul
   cross-schema dans le Celery task `refresh_seo_cache`, stockage en
   `SEOCache.FEDERATION_INCOMING`. La navbar "Reseau local" est desormais
   pilotee uniquement par `config.module_federation`.

2. **JSON-LD federation** : nouvelle helper
   `seo.views_common.build_json_ld_federation()` qui produit un schema.org/
   Organization + `subOrganization` + `memberOf`. Injecte sur `/federation/`
   tenant (racine = tenant, subOrg = voisins federes, memberOf = reseau
   TiBillet) et sur `/explorer/` public (racine = TiBillet, subOrg = tous les
   tenants). Les crawlers no-JS recoivent immediatement la structure du
   reseau sans avoir besoin d'executer Leaflet. Fix collateral : `meta_robots`
   devient un `{% block %}` dans `seo/base.html`.

3. **Quick wins SEO** :
   - `/humans.txt` sur le ROOT public (manquait avant)
   - `/federation/` ajoute au `StaticViewSitemap` tenant
   - Helper `build_json_ld_breadcrumb()` + BreadcrumbList sur `/federation/`

**EN :** Three axes to make the TiBillet network visible to LLMs (GPTBot,
ClaudeBot, PerplexityBot, CommonCrawl) and Google.

1. **Bidirectional neighbors**: a tenant's map shows neighbors declared in
   both directions. If X federates with me but I haven't declared X in my
   `FederatedPlace`, X still appears. Cross-schema pre-computation in the
   `refresh_seo_cache` Celery task, stored in `SEOCache.FEDERATION_INCOMING`.
   The "Local network" navbar is now driven solely by `config.module_federation`.

2. **Federation JSON-LD**: new helper
   `seo.views_common.build_json_ld_federation()` produces a schema.org/
   Organization + `subOrganization` + `memberOf`. Injected on `/federation/`
   tenant (root = tenant, subOrg = federated neighbors, memberOf = TiBillet
   network) and on `/explorer/` public (root = TiBillet, subOrg = all
   tenants). No-JS crawlers immediately receive the network structure without
   executing Leaflet. Collateral fix: `meta_robots` becomes a `{% block %}`
   in `seo/base.html`.

3. **SEO quick wins**:
   - `/humans.txt` on public ROOT (was missing)
   - `/federation/` added to tenant `StaticViewSitemap`
   - `build_json_ld_breadcrumb()` helper + BreadcrumbList on `/federation/`

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---

## Chantier FEDERATION #01 — Explorer in-tenant + refactor JS prod / In-tenant explorer + production-grade JS refactor

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** `/federation/` (Réseau local) sur chaque tenant rend maintenant l'explorer
(carte Leaflet + filtres) avec uniquement le tenant courant + ses FederatedPlace.
Le code de la carte est consolidé en source unique dans `seo/` (JS + CSS + widget
HTML + data builder), partagé avec le public `/explorer/`. Le JS a été refactoré
pour la prod : IIFE encapsulé (zéro pollution `window`), event delegation (zéro
`onclick=` inline), i18n via `data-i18n-*`, garde-fous défensifs (try/catch JSON,
DOM presence), Leaflet vendoré (plus de CDN externe unpkg.com), event Leaflet
`animationend` au lieu de `setTimeout(...,400)`. Marker visuel "Vous êtes ici"
pour le tenant courant.

**EN :** `/federation/` (Local network) on each tenant now renders the explorer
(Leaflet map + filters) limited to the current tenant + its FederatedPlace.
Map code is consolidated as a single source under `seo/` (JS + CSS + widget HTML +
data builder), shared with the public `/explorer/`. The JS has been refactored
for production: encapsulated IIFE (zero `window` pollution), event delegation
(zero inline `onclick=`), i18n via `data-i18n-*`, defensive guards (try/catch
JSON, DOM presence), vendored Leaflet (no external unpkg.com CDN), Leaflet
`animationend` event instead of `setTimeout(...,400)`. Visual "You are here"
marker for the current tenant.

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---

## Chantier M-To-V2 #02 — Port app `seo/` allegee (landing ROOT lieux + events) / Port lightweight `seo/` app

**Date :** 2026-05-13
**Migration :** Oui (`seo/0001_initial.py` sur le schema public)
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** Portage de l'app `seo` de V2 (lespass-main) vers V1 en version allegee.
On agrege uniquement les **lieux + evenements** du reseau (pas d'adhesions, pas
d'initiatives crowdfunding, pas de monnaies fedow_core). La landing ROOT remplace
l'ancienne redirection MetaBillet vers tibillet.org. Cache 2 niveaux (Memcached
L1 + DB L2) rafraichi toutes les 4h par Celery Beat. 7 routes : `/`, `/lieux/`,
`/evenements/`, `/recherche/`, `/explorer/`, `/robots.txt`, `/sitemap.xml`.

**EN :** Port of the V2 `seo` app to V1 in a lightweight version. Aggregates only
**venues + events** (no memberships, no crowdfunding initiatives, no fedow_core
currencies). The ROOT landing replaces the previous MetaBillet redirect to
tibillet.org. 2-tier cache (Memcached L1 + DB L2) refreshed every 4h by Celery
Beat. 7 routes: `/`, `/lieux/`, `/evenements/`, `/recherche/`, `/explorer/`,
`/robots.txt`, `/sitemap.xml`.

**Fichiers crees :** voir `TECH DOC/SESSIONS/M-To-V2/02-app-seo.md`
**Fichiers modifies :** `TiBillet/settings.py`, `TiBillet/urls_public.py`, `TiBillet/celery.py`

---

## v1.8 — Modules Groupware + refacto admin + proxies Product / Groupware modules + admin refactor + Product proxies

**Date :** 2026-05-13
**Migration :** Oui (`0204_configuration_module_adhesion_and_more`, `0205_futproduct_membershipproduct_posproduct_and_more`)
**Contributeurs / Contributors :** NothRen (Antoine), JonasFW13 (Jonas)

---

### Vue d'ensemble / Overview

**FR :**
Premiere etape d'integration de la V2 (mono-repo TiBillet/Lespass + LaBoutik + Fedow)
dans la V1 actuelle. On introduit la notion de **Groupware** (activation modulaire par
tenant) et on prepare l'admin pour accueillir les nouveaux types de produits (POS, fut)
sans casser la compatibilite. Refacto majeur de `admin_tenant.py` (~1000 lignes
deplacees) en modules separes. Ajout de proxy models pour separer les vues admin par
type de produit. Fix bug timezone sur les filtres datetime de l'admin (#384).

**EN :**
First step of integrating the V2 mono-repo (TiBillet/Lespass + LaBoutik + Fedow)
into the current V1. Introduces the **Groupware** concept (per-tenant modular activation)
and prepares admin for upcoming product types (POS, keg) without breaking compatibility.
Major refactor of `admin_tenant.py` (~1000 lines moved) into separate modules. Adds proxy
models to split admin views by product type. Fixes timezone bug on admin datetime filters (#384).

---

### 1. Modules Groupware : activation par tenant / Groupware modules: per-tenant activation

**FR :**
Ajout de **9 booleens** `module_*` sur `Configuration` pour activer/desactiver des
sections fonctionnelles par tenant. Les modules deja en production sont actives par
defaut (`module_billetterie`, `module_adhesion`, `module_crowdfunding`,
`module_federation`). Les modules V2 a venir sont desactives par defaut
(`module_monnaie_locale`, `module_caisse`, `module_inventaire`, `module_tireuse`,
`module_booking`).

**Dashboard admin** : nouvelles cartes avec switches HTMX et modal de confirmation.
Apres bascule, `HX-Refresh` recharge la page pour mettre a jour la sidebar.
**Sidebar dynamique** : `get_sidebar_navigation(request)` (callable string) construit
la navigation selon les modules actifs.
**NavBar publique** : les liens `/memberships/`, `/event/`, `/federation/`, `/contrib/`
n'apparaissent dans la barre publique que si le module correspondant est actif (cf.
`BaseBillet/views.py:get_context()`).

**Dependance** : `module_caisse` necessite `module_monnaie_locale`. Validation cote
serveur dans `module_toggle()` qui renvoie un message d'erreur via `django.messages` si
on tente de violer cette regle.

**EN :**
Adds **9 module_* booleans** on `Configuration` to enable/disable functional sections
per tenant. Currently-live modules default to True; upcoming V2 modules default to False.
Admin dashboard gets module cards with HTMX switches and a confirmation modal.
Sidebar is now dynamic (`get_sidebar_navigation` callable). Public navbar links only
show if the matching module is active. `module_caisse` requires `module_monnaie_locale`.

---

### 2. Refacto `admin_tenant.py` : split en modules / `admin_tenant.py` refactor: split into modules

**FR :**
`Administration/admin_tenant.py` faisait ~3000 lignes. On extrait :

- `Administration/admin/site.py` — `StaffAdminSite` + `sanitize_textfields` (utilitaire XSS).
- `Administration/admin/dashboard.py` — `get_sidebar_navigation`, `dashboard_callback`,
  `MODULE_FIELDS`, `_build_modules_context`, `adhesion_badge_callback`, `environment_callback`.
- `Administration/admin/products.py` — `ProductAdmin`, `TicketProductAdmin`,
  `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`,
  `ProductFormFieldInline`, palettes/icones POS (commente, pour V2), validation.
- `Administration/admin/prices.py` — `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm`.

`admin_tenant.py` re-exporte les noms publics (`get_sidebar_navigation`, etc.) via
`from Administration.admin.dashboard import ...` pour ne rien casser cote `settings.py`
qui pointe encore sur `Administration.admin_tenant.get_sidebar_navigation`.

**EN :**
Splits the ~3000-line `admin_tenant.py` into 4 modules under `Administration/admin/`.
Public names re-exported from the original module to keep `settings.py` references valid.

---

### 3. Proxy models Product : 4 vues admin filtrees / Product proxy models: 4 filtered admin views

**FR :**
Sans toucher a la table `BaseBillet_product`, on cree **4 proxy models** :
- `TicketProduct` — filtre `categorie_article IN ('B', 'F')` (Billet, FreeRes).
- `MembershipProduct` — filtre `categorie_article = 'A'` (Adhesion).
- `POSProduct` — filtre `methode_caisse IS NOT NULL` (V2, admin commente).
- `FutProduct` — filtre `categorie_article = 'U'` (V2, admin commente).

Chaque proxy a son propre `ModelAdmin` avec un formulaire restreint et un `get_queryset`
filtre. La sidebar affiche separement "Ticket products" (section Billetterie) et
"Membership products" (section Adhesions). Le `ProductAdmin` original reste enregistre
pour preserver les autocomplete `EventAdmin` et les URLs existantes.

`MembershipProductAdmin` recupere `ProductFormFieldInline` (formulaires dynamiques pour
adhesions). `TicketProductAdmin` ne l'a pas (champs dynamiques inutiles pour la billetterie).

**EN :**
Adds 4 proxy models filtered by product type. Each has its own admin with a restricted
form and filtered queryset. Original `ProductAdmin` is kept to preserve existing URLs
and autocomplete behavior in `EventAdmin`.

---

### 4. Champs conditionnels dans les inlines / Conditional fields in inlines

**FR :**
Unfold supporte `conditional_fields` au niveau ModelAdmin mais **pas** au niveau inline.
Pour le besoin "afficher `iteration` seulement si `recurring_payment` coche" sur l'inline
`MembershipPriceInline`, on ajoute un systeme generique :

- Chaque `Inline` declare un dict `inline_conditional_fields = {"champ": "expression"}`.
- `MembershipProductAdmin.changeform_view()` collecte ces dicts et les injecte en JSON
  via `extra_context["inline_conditional_rules"]`.
- Template `admin/product/inline_conditional_fields.html` rend le JSON dans
  `<script id="inline-conditional-rules" type="application/json">`.
- JS `Administration/static/admin/js/inline_conditional_fields.js` lit le JSON, ecoute
  les `change`/`input` sur les sources, applique cascade (source cachee = condition fausse),
  anime apparition/disparition, observe les nouvelles lignes inline (MutationObserver).

Expressions supportees : `champ == true`, `champ == false`, `champ > N`.

**EN :**
Generic conditional-field system for Django admin inlines (Unfold doesn't support
`conditional_fields` on inlines). Each inline declares `inline_conditional_fields`,
the changeform view collects them and injects JSON, JS reads the JSON, listens on
sources, handles cascade, animates show/hide, observes new inline rows.

---

### 5. Fix bug timezone sur les filtres datetime admin (#384) / Fix timezone bug on admin datetime filters (#384)

**FR :**
`RangeDateTimeFilter` (Unfold) parsait les bornes saisies dans le filtre admin sans
tenir compte de la timezone du tenant, ce qui entrainait des decalages d'une heure sur
les filtrages d'historique. Nouveau filtre `RangeDateTimeFilterWithTimeZone` qui :

1. Recupere la timezone du tenant via `Configuration.get_solo().get_tzinfo()`.
2. Localise les `datetime` parses avec `new_timezone.localize(...)` avant le filtrage.
3. Retourne `None` proprement en cas d'erreur de parsing.

Applique sur `LigneArticleAdmin` et `LigneArticlePosAdmin`.

**EN :**
Fixes one-hour offset in admin datetime range filters by localizing parsed datetimes
with the tenant's timezone (`Configuration.get_solo().get_tzinfo()`).

---

### 6. Fix divers / Miscellaneous fixes

**FR :**
- **Subscription duration** (commit 32e035e2, NothRen) : interdit la creation d'un
  `Price` avec `recurring_payment=True` mais `subscription_type=NA`. Validation cote
  serveur dans `MembershipPriceInlineForm.clean_subscription_type()`.
- **`SyntaxWarning: "is" with a literal`** (commit 5ddeb7ca, JonasFW13) : remplace
  `field_name is "module_caisse"` par `field_name == "module_caisse"` dans
  `module_toggle()`. Le `is` ne doit pas etre utilise pour comparer des strings.
- **`poids` → "Display order"** (commit 0cce7f1b, NothRen) : renomme le `verbose_name`
  pour clarifier le sens metier ("ordre d'affichage", plus petit = en premier). La colonne
  DB reste `poids`.
- **Doc technique V1-to-V2 + Stripe Checkout fix** (commit 1a3f2c0f, JonasFW13) :
  ajout de `TECH DOC/SESSIONS/M-To-V2/INDEX.md` et
  `Administration/Unfold_docs/stripe-checkout-account-business-name.md`.

**EN :**
- Subscription duration validation: `recurring_payment=True` requires `subscription_type != NA`.
- Replaces `is` with `==` for string comparison (PEP 8).
- Renames `poids` verbose_name to "Display order" for clarity.
- Adds technical migration docs.

---

### 7. NavBar publique conditionnelle / Conditional public navbar

**FR :**
Dans `BaseBillet/views.py:get_context()`, les liens publics `/memberships/`, `/event/`,
`/federation/` et `/contrib/` n'apparaissent dans `main_nav` que si le module correspondant
est actif. Avant : ces liens etaient toujours visibles, meme si la fonctionnalite etait
desactivee (404 a la cle).

**EN :**
Public navbar links are now conditional on the matching module flag.

---

### 8. `DATETIME_INPUT_FORMATS` ajoute aux settings / `DATETIME_INPUT_FORMATS` added to settings

**FR :**
Ajout de plusieurs formats de saisie datetime (FR `dd/mm/yyyy hh:mm`, ISO
`yyyy-mm-dd hh:mm:ss`, etc.) pour que les formulaires admin acceptent les variantes
courantes lors du parsing manuel des dates.

**EN :**
Adds several datetime input formats (FR and ISO variants) for admin form parsing.

---

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | +9 champs `module_*` sur `Configuration`, +4 proxy models (`TicketProduct`, `MembershipProduct`, `POSProduct`, `FutProduct`), +`RECHARGE_CASHLESS_FED` et `FUT` dans `CATEGORIE_ARTICLE_CHOICES`, renommage `poids` verbose_name |
| `BaseBillet/migrations/0204_configuration_module_adhesion_and_more.py` | Migration des 9 booleens `module_*` |
| `BaseBillet/migrations/0205_futproduct_membershipproduct_posproduct_and_more.py` | Migration des 4 proxy models |
| `BaseBillet/views.py` | NavBar publique conditionnelle aux modules dans `get_context()` |
| `Administration/admin_tenant.py` | Refacto majeur (~1000 lignes deplacees), re-export des symboles publics, ajout `module_toggle_modal` / `module_toggle`, dependance `module_caisse` ↔ `module_monnaie_locale`, nouveau `RangeDateTimeFilterWithTimeZone` |
| `Administration/admin/__init__.py` | Nouveau (package) |
| `Administration/admin/site.py` | Nouveau : `StaffAdminSite`, `sanitize_textfields` |
| `Administration/admin/dashboard.py` | Nouveau : `get_sidebar_navigation` (sidebar dynamique), `dashboard_callback`, `MODULE_FIELDS`, `_build_modules_context` |
| `Administration/admin/products.py` | Nouveau : `ProductAdmin` + proxy admins `TicketProductAdmin` / `MembershipProductAdmin`, inlines `BasePriceInline`/`TicketPriceInline`/`MembershipPriceInline`, `ProductFormFieldInline`, code POS commente pour V2 |
| `Administration/admin/prices.py` | Nouveau : `PriceAdmin`, `PromotionalCodeAdmin`, `PriceChangeForm` |
| `Administration/templates/admin/index.html` | `+include "admin/dashboard.html"` (cartes modules) |
| `Administration/templates/admin/dashboard.html` | Nouveau : grille de cartes modules avec switches HTMX |
| `Administration/templates/admin/dashboard_module_modal.html` | Nouveau : modal de confirmation pour bascule module |
| `Administration/templates/admin/product/inline_conditional_fields.html` | Nouveau : injection JSON des regles conditionnelles |
| `Administration/static/admin/js/inline_conditional_fields.js` | Nouveau : 400 lignes JS, gestion cascade + animation + MutationObserver |
| `Administration/static/admin/css/price_inline.css` | Nouveau : style des titres `StackedInline` (scope `#prices-group`) |
| `TiBillet/settings.py` | `SIDEBAR.navigation` → callable string, ancien dump renomme `SIDEBAR-TEMP-OLD` (a supprimer plus tard), `+DATETIME_INPUT_FORMATS` |
| `PaiementStripe/views.py` | Branche `elif 'account or business name'` (fix v1.7.18, deja documente) |
| `VERSION` | `VERSION=1.8`, `MIGRATE=1` |
| `locale/fr/LC_MESSAGES/django.{po,mo}` | +1500 lignes (modules, proxies, validations) |
| `locale/en/LC_MESSAGES/django.{po,mo}` | +1500 lignes |
| `TECH DOC/SESSIONS/M-To-V2/INDEX.md` | Nouveau : doc technique V1-to-V2 |
| `Administration/Unfold_docs/stripe-checkout-account-business-name.md` | Nouveau : explication + fix Stripe Checkout |

### Migration
- **Migration necessaire / Migration required:** Oui — `MIGRATE=1` dans `VERSION`.
- Commande : `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
- Les nouveaux booleens ont des `default` : aucun risque sur les tenants existants. Les
  modules deja en production (`billetterie`, `adhesion`, `crowdfunding`, `federation`)
  sont actives par defaut.

### Compatibilite / Compatibility
- **Coexistence V1/V2** : carte "Caisse V2" du dashboard est grisee si `server_cashless`
  est configure (= ancien tenant en V1). Les modules V2 (`monnaie_locale`, `caisse`,
  `inventaire`, `tireuse`, `booking`) restent desactives.
- **`SIDEBAR-TEMP-OLD`** dans `settings.py` : ancien dump conserve commente pour reference,
  a supprimer apres une periode de stabilisation.
- **Code POS/Fut/Categorie** dans `Administration/admin/products.py` : commente bloc par
  bloc (`FROM V2 : TODO`), reactive quand on integre l'app `laboutik` et `inventaire`.

### i18n
- ~1500 lignes ajoutees/modifiees dans `locale/{fr,en}/LC_MESSAGES/django.po`.
- `compilemessages` deja execute (les `.mo` sont a jour dans le commit).

---

## v1.7.18 — Fix 500 sur compte Stripe Connect sans nom commercial / Fix 500 on Stripe Connect account missing business name

**Date :** 2026-05-12
**Migration :** Non

---

### Gestion gracieuse de `account or business name` (Stripe Checkout) / Graceful handling of `account or business name` (Stripe Checkout)

**FR :**
Quand un tenant tente de creer une session Stripe Checkout (adhesion, reservation) alors
que son compte Stripe Connect n'a pas de nom commercial configure, Stripe leve
`InvalidRequestError: In order to use Checkout, you must set an account or business name`.

Avant : l'erreur tombait dans le fallback `else` de `_checkout_session()` qui retentait
betement avec `force=True` sur les line_items (corrige rien) → l'exception bubblait jusqu'a
la vue → **500** pour l'utilisateur final.

Apres : le cas est detecte explicitement, on logge le `schema_name` du tenant concerne pour
que l'admin sache ou intervenir, et on leve `serializers.ValidationError` avec un message
generique. Le `MembershipMVT.create()` (et autres ViewSets qui consomment `is_valid()` sans
`raise_exception=True`) recoit l'erreur dans `.errors`, l'affiche via `django.messages`, et
redirige proprement vers le `Referer`.

**EN :**
When a tenant tries to create a Stripe Checkout session while its Connect account is
missing a business name, Stripe raises `InvalidRequestError`. The error used to fall into
the `else` fallback that retried with `force=True` on line_items — useless, since the
issue is on the account side. Now caught explicitly: we log the tenant schema_name and
raise a user-friendly `ValidationError`. No more 500, the user sees a clear message.

### Decision : pas de patch preventif cote Lespass / Decision: no preventive patch on Lespass side

**FR :**
On a envisage de pre-remplir `business_profile.name` dans
`Configuration.get_stripe_connect_account()` (BaseBillet/models.py) pour que les nouveaux
tenants n'aient jamais l'erreur. **Decision finale : non.** Le bug racine est gere
**cote Stripe** (le gerant doit completer son `business_profile.name` lors du onboarding,
le dashboard Stripe le demande explicitement). Cote Lespass, on se contente donc de :

1. Faire remonter l'erreur a l'utilisateur final via `serializers.ValidationError`
   (message generique).
2. Logger en `ERROR` avec le `schema_name` du tenant pour que Sentry remonte l'incident
   et que l'admin sache ou intervenir.

`Configuration.get_stripe_connect_account()` reste donc inchange : il cree le compte avec
seulement `type="standard"` et `country="FR"`. C'est volontaire.

**Tenants existants deja sans nom commercial :** ils doivent fixer manuellement via
dashboard Stripe ou `stripe accounts update <acct_id> -d "business_profile[name]=..."`.

**EN :**
We considered pre-filling `business_profile.name` in
`Configuration.get_stripe_connect_account()` so that new tenants would never hit the error.
**Final decision: no.** The root cause is handled on the Stripe side (tenant admins now
explicitly fill `business_profile.name` during Connect onboarding). On Lespass we just
surface the error to the user and log it in Sentry.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `PaiementStripe/views.py` | Nouveau branch `elif 'account or business name'` dans `CreationPaiementStripe._checkout_session()` (avant le fallback retry). Loggue l'erreur avec le `schema_name` du tenant (visible dans Sentry), leve `ValidationError` avec un message generique. |

### Migration
- **Migration necessaire / Migration required:** Non

### i18n
Une nouvelle chaine traduisible ajoutee :
- `"Online payment is temporarily unavailable. Please contact the site administrator."`

A executer : `makemessages -l fr -l en` puis `compilemessages`.

---

## v1.7.17 — Améliorations SEO home Faire Festival + humans.txt / SEO improvements on Faire Festival home + humans.txt

**Date :** 2026-05-05
**Migration :** Non

---

### Améliorations SEO sur la home du skin Faire Festival / SEO improvements on Faire Festival skin home

**FR :**
Suite à l'audit RoastMyUrl sur `fairefestival.fr` (score 69/100), correction des points SEO
sur la home du skin Faire Festival :

- **Title trop court (24 char)** : enrichi en `Festival du Faire — Toulouse, 28-30 mai 2026 | <organisation>` (61 char). Inclut désormais les mots-clés métier (`Festival`, `Faire`), géo (`Toulouse`) et la date.
- **Meta description courte (113 char)** : étendue à 158 char avec `fablabs`, `22 thématiques`, et la date.
- **og:title / twitter:title** : alignés sur le nouveau title.
- **og:description / twitter:description** : alignées sur la meta description longue.
- **Bug HTML** : 3 balises `<h3>` étaient fermées par `</h4>` (typo lors du merge `template-faire-festival`). Corrigées en `</h3>`.
- **Hiérarchie H2** : la baseline `Le grand rendez-vous toulousain...` était dans un `<p>`. Passée en `<h2>` (classes Bootstrap conservées, rendu visuel identique). On passe de 1 H2 à 2 H2.
- **Alts d'images génériques** (`Billets`, `Programmation`, `Faire Festival`) : enrichis pour le SEO et l'accessibilité (`Prendre vos billets pour le Faire Festival`, `Programmation du Faire Festival : 22 thématiques`, `Infos pratiques du Faire Festival, 28-30 mai`).

**EN :**
Following the RoastMyUrl audit on `fairefestival.fr` (score 69/100), SEO fixes on the Faire
Festival skin home:

- Title extended from 24 to 61 char with geo + date keywords.
- Meta description extended to 158 char with metier keywords.
- og/twitter title and description aligned.
- Fixed 3 `<h3>` tags closed with `</h4>` (typo from the merge).
- Tagline `<p>` upgraded to `<h2>` for proper heading hierarchy.
- Generic image alts replaced with descriptive ones.

### Ajout de humans.txt dynamique / Dynamic humans.txt added

**FR :**
Ajout d'un endpoint `/humans.txt` dynamique au standard [humanstxt.org](https://humanstxt.org/Standard.html).
Crédite la Coopérative Code Commun comme équipe de développement. Le contenu est identique
pour tous les tenants (même réponse quel que soit le `Host`). La version et la date du
dernier bump sont lues depuis le fichier `VERSION` à la racine.

**EN :**
Added a dynamic `/humans.txt` endpoint following the [humanstxt.org standard](https://humanstxt.org/Standard.html).
Credits Coopérative Code Commun as the dev team. Same content for all tenants. Version
and last update date read from the root `VERSION` file.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/templates/faire_festival/views/home.html` | Title / og / twitter enrichis ; meta description étendue ; fix `<h3>...</h4>` ×3 ; baseline `<p>` → `<h2>` ; alts d'images enrichis |
| `BaseBillet/views_humans.py` | **Nouveau** — vue `humans_txt`, parse le fichier `VERSION` (version + mtime) au chargement du module |
| `BaseBillet/urls.py` | Import `humans_txt` + route `path('humans.txt', humans_txt, name='humans_txt')` |

### Migration
- **Migration necessaire / Migration required:** Non

### À faire en config admin / Admin config TODO (no code)
Pour activer pleinement le SEO en prod sur `fairefestival.fr` :
- Uploader la social card sur `Configuration > img` (1200×630 → génère `og:image`)
- Renseigner `Configuration > facebook` / `instagram` / `twitter` (alimente `JSON-LD sameAs`)
- Compléter `Configuration > postal_address` (alimente `JSON-LD address`)

### À faire i18n / i18n TODO
Les nouvelles chaînes (`Festival du Faire — Toulouse, 28-30 mai 2026`, meta description longue,
3 alts enrichis) sont en `{% translate %}` mais pas encore dans les `.po`. À traiter dans
une session de traduction dédiée (`makemessages` + `compilemessages`).

---

## Unreleased — Fix message trompeur sur reservation gratuite anonyme / Misleading message on anonymous free booking

**Date :** 2026-04-21
**Migration :** Non

---

### Correction de la page de confirmation de reservation gratuite / Free booking confirmation page fix

**FR :**
Lorsqu'un visiteur non connecte reservait une activite gratuite avec l'email d'un compte
deja existant et actif, la page de confirmation affichait « Veuillez valider votre e-mail »
alors que les billets etaient deja envoyes (resa en `FREERES_USERACTIV`) et que la
reservation etait confirmee en back-office.

Cause : la vue `EventViewset.reservation` passait `request.user` au template. Quand le
visiteur n'est pas connecte, `request.user` vaut `AnonymousUser` dont `is_active` est
toujours `False`. Le template basculait alors sur la branche « validez votre email »
en ignorant l'etat reel de l'user retrouve en base par email.

Fix : passer `validator.reservation.user_commande` au template. Cet user est celui
resolu par `get_or_create_user(email)` dans le validator, donc coherent avec la
decision prise par `TicketCreator.method_F` pour envoyer (ou non) les billets
immediatement.

**EN :**
When an unauthenticated visitor booked a free activity using the email of an
already-existing active account, the confirmation page showed "Please validate your
e-mail" even though the tickets were already sent and the booking was confirmed.

Root cause: the view passed `request.user` (an `AnonymousUser` with `is_active=False`)
to the template. Fix: pass `validator.reservation.user_commande` instead — the user
resolved by the validator from the submitted email.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `EventViewset.reservation` : passe `validator.reservation.user_commande` au template au lieu de `request.user` |

### Migration
- **Migration necessaire / Migration required:** Non

---

## v1.7.7 — Unification actions admin Membership dans MembershipMVT

**Date :** Mars 2026
**Migration :** Non

---

### Unification des actions admin sur les adhésions / Membership admin actions unified

**FR :**
Les actions admin sur les adhésions sont désormais centralisées dans `MembershipMVT` (viewset DRF),
exposées via HTMX dans un panneau inline affiché avant le formulaire admin.

- **Supprimé** : `actions_detail` / `actions_row` Unfold dans `MembershipAdmin` (5 méthodes `@action`)
- **Supprimé** : `has_custom_actions_row_permission`, `has_custom_actions_detail_permission`
- **Supprimé** : templates orphelins `cancel_confirm.html` et `ajouter_paiement.html`
- **Ajouté** : `change_form_before_template = "admin/membership/actions_panel.html"` sur `MembershipAdmin`
- **Ajouté** : 3 nouvelles actions dans `MembershipMVT` : `send_invoice`, `ajouter_paiement`, `cancel`
- **Ajouté** : `PaiementHorsLigneSerializer` dans `BaseBillet/validators.py`
- **Ajouté** : 4 nouveaux partials HTMX dans `admin/membership/partials/`

**EN :**
Admin actions on memberships are now centralised in `MembershipMVT` (DRF viewset),
exposed via HTMX in an inline panel displayed before the admin change form.

**Fichiers modifiés :**
- `BaseBillet/validators.py` : + `PaiementHorsLigneSerializer`
- `BaseBillet/views.py` : + imports `get_or_create_price_sold`, `dec_to_int`, `reverse`, `PaiementHorsLigneSerializer` + 3 actions + update `get_permissions`
- `Administration/admin_tenant.py` : - 5 `@action` Unfold + enrichissement `changeform_view` + `change_form_before_template`
- `Administration/templates/admin/membership/actions_panel.html` : Nouveau — panneau HTMX
- `Administration/templates/admin/membership/partials/send_invoice_success.html` : Nouveau
- `Administration/templates/admin/membership/partials/cancel_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_form.html` : Nouveau
- `Administration/templates/admin/membership/partials/ajouter_paiement_success.html` : Nouveau

---

## v1.7.6 — Skin Faire Festival + Corrections UX et Sentry

**Date :** Mars 2026
**Migration :** Non

---

### 1. Skin Faire Festival — ameliorations CSS et templates / Faire Festival skin — CSS and template improvements

**FR :**
Ameliorations du skin "Faire Festival" suite aux retours terrain :
- Bordures arrondies (`border-radius`) sur les cartes et le bouton burger mobile
- Titres des evenements en police mono, taille reduite, avec `hyphens: auto`
- Bordure image evenement epaissie (1px → 3px)
- Badge de date repositionne (`margin-left: 0` au lieu de -100px)
- Padding horizontal des cartes ajuste

**EN:**
Improvements to the "Faire Festival" skin based on field feedback:
- Rounded borders (`border-radius`) on cards and mobile burger button
- Event titles in mono font, smaller size, with `hyphens: auto`
- Event image border thickened (1px → 3px)
- Date badge repositioned (`margin-left: 0` instead of -100px)
- Card horizontal padding adjusted

**Fichiers / Files:**
- `BaseBillet/static/faire_festival/css/faire_festival.css`

---

### 2. Lazy-load video sur la page d'accueil / Video lazy-load on homepage

**FR :**
La video motion-table de la page d'accueil bloquait le chargement sur Firefox mobile.
Remplacement de `autoplay` + `src` par un mecanisme `IntersectionObserver` :
la video n'est telechargee et lue que lorsqu'elle entre dans le viewport.
`preload="none"` empeche tout telechargement au chargement initial de la page.

**EN:**
The motion-table video on the homepage was blocking page load on Firefox mobile.
Replaced `autoplay` + `src` with an `IntersectionObserver` mechanism:
the video is only downloaded and played when it enters the viewport.
`preload="none"` prevents any download on initial page load.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/home.html`

---

### 3. Description adhesion en accordeon intelligent / Smart collapsible membership description

**FR :**
La description longue de la page d'adhesion est desormais tronquee automatiquement
si elle depasse ~10-12 lignes (250px). Un bouton "Lire la suite" / "Reduire" apparait.
Si la description est courte, elle s'affiche en entier sans bouton.

**EN:**
The long description on the membership page is now automatically truncated
if it exceeds ~10-12 lines (250px). A "Read more" / "Show less" button appears.
If the description is short, it displays fully without a button.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/membership/list.html`

---

### 4. Filtre par date sur la page evenements / Date filter on events page

**FR :**
Le dropdown "Trier par date" etait present dans le template mais non branche cote back.
Le parametre `?date=` est maintenant lu par la vue `list()`, et le dict `dated_events`
est filtre pour n'afficher que les evenements de la date selectionnee.
Le dropdown conserve toutes les dates disponibles meme quand un filtre est actif.
Le bouton affiche la date selectionnee en format lisible ("lundi 15 mars").

**EN:**
The "Sort by date" dropdown was present in the template but not wired to the backend.
The `?date=` parameter is now read by the `list()` view, and the `dated_events` dict
is filtered to display only events for the selected date.
The dropdown keeps all available dates even when a filter is active.
The button shows the selected date in readable format ("Monday March 15").

**Fichiers / Files:**
- `BaseBillet/views.py` — `EventMVT.list()` : lecture param `date`, filtrage du dict
- `BaseBillet/templates/faire_festival/views/event/list.html` — affichage date active, format ISO dans les liens

---

### 5. Correction erreur Sentry : confirmation email reservation expiree / Fix Sentry error: expired reservation email confirmation

**FR :**
Quand un utilisateur confirmait son email plus de 15 minutes apres une reservation gratuite
et que l'evenement etait presque complet, le signal levait un `ValueError` qui remontait
en `Http404` generique. L'utilisateur voyait une page 404 sans explication.
Desormais le `ValueError` est intercepte dans `emailconfirmation()` et le message
est affiche a l'utilisateur via `django.messages` sur la page d'accueil.
Les messages d'erreur sont maintenant traduits via `_()`.

**EN:**
When a user confirmed their email more than 15 minutes after a free reservation
and the event was nearly full, the signal raised a `ValueError` that surfaced
as a generic `Http404`. The user saw a 404 page with no explanation.
Now the `ValueError` is caught in `emailconfirmation()` and the message
is displayed to the user via `django.messages` on the homepage.
Error messages are now translated via `_()`.

**Fichiers / Files:**
- `BaseBillet/views.py` — `emailconfirmation()` : catch `ValueError` separement
- `BaseBillet/signals.py` — `activator_free_reservation()` : messages avec `_()`

---

### 6. Section produits retiree de la page evenement / Products section removed from event detail page

**FR :**
La section "Tickets and prices" a ete retiree de la page detail evenement du skin Faire Festival.
Le label "Intervenant-e-s" en dur a egalement ete supprime.

**EN:**
The "Tickets and prices" section was removed from the event detail page of the Faire Festival skin.
The hardcoded "Intervenant-e-s" label was also removed.

**Fichiers / Files:**
- `BaseBillet/templates/faire_festival/views/event/retrieve.html`

---

### 7. Correction calcul paiement adhesion sans contribution / Fix membership payment calculation without contribution

**FR :**
Correction d'un crash quand `contribution_value` etait absente lors du calcul
du montant de paiement d'une adhesion. La valeur manquante est maintenant traitee gracieusement.

**EN:**
Fixed a crash when `contribution_value` was missing during membership payment amount calculation.
The missing value is now handled gracefully.

**Fichiers / Files:**
- Commit `50132e35`

---

### Autres ameliorations / Other improvements

- **Admin breadcrumb** : affiche le nom du produit au lieu du nom du tarif dans le fil d'Ariane
- **Admin product archive filter** : filtre pour afficher/masquer les produits archives
- **Redirect tarif → produit** : retour automatique vers le produit parent apres sauvegarde d'un tarif
- **Widget adhesions obligatoires** : passage en `MultipleHiddenInput`
- **Integration Fedow** : gestion d'erreur non-bloquante lors de la creation d'assets et validation d'adhesion
- **Newsletter** : ajout de l'URL newsletter dans le skin
- **Traductions** : nouvelles chaines FR/EN pour les filtres, messages d'erreur, et boutons

**Migration necessaire / Migration required:** Non

---

## v1.7.2 — Corrections production + Paiement admin adhesions + Avoir comptable

**Date :** Mars 2026
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 0. Protection doublon paiement adhesion (SEPA) / Duplicate membership payment protection (SEPA)

**FR :**
Quand un utilisateur cliquait plusieurs fois sur le lien de paiement d'adhesion
(recu par email apres validation admin), un nouveau checkout Stripe etait cree a chaque clic.
Cela pouvait entrainer des **doubles prelevements SEPA** (signaie en production).

La vue `get_checkout_for_membership` verifie maintenant si un paiement Stripe existe deja :
- **Session Stripe encore ouverte** : reutilise l'URL existante (pas de doublon).
- **Session "complete" (SEPA en cours)** : affiche une page d'information expliquant
  que le prelevement est en cours de traitement (jusqu'a 14 jours).
- **Session expiree** : cree un nouveau checkout normalement.

**EN:**
When a user clicked multiple times on the membership payment link
(received by email after admin validation), a new Stripe checkout was created each time.
This could cause **duplicate SEPA debits** (reported in production).

The `get_checkout_for_membership` view now checks for an existing Stripe payment:
- **Stripe session still open**: reuses the existing URL (no duplicate).
- **Session "complete" (SEPA pending)**: displays an info page explaining
  the debit is being processed (up to 14 days).
- **Session expired**: creates a new checkout normally.

**Fichiers / Files:**
- `BaseBillet/views.py` — protection doublon dans `get_checkout_for_membership`
- `BaseBillet/templates/reunion/views/membership/payment_already_pending.html` — nouveau template

**Migration necessaire / Migration required:** Non

---

### 1. Avoir comptable (credit note) sur les ventes / Credit note on sales

**FR :**
Les admins peuvent emettre un **avoir** sur une ligne de vente depuis l'admin (bouton "Avoir" dans la liste des ventes).
Un avoir cree une ligne miroir avec quantite negative pour annuler comptablement la vente,
sans supprimer l'ecriture originale (conformite fiscale francaise).
Gardes : uniquement sur lignes confirmees ou payees, et un seul avoir par ligne.
L'avoir est envoye a LaBoutik si un serveur cashless est configure.
L'export CSV inclut une colonne "Ref. avoir" pour la tracabilite.

**EN:**
Admins can issue a **credit note** on a sale line from the admin (row action button in the sales list).
A credit note creates a mirror line with negative quantity to cancel the sale for accounting purposes,
without deleting the original entry (French fiscal compliance).
Guards: only on confirmed or paid lines, and only one credit note per line.
The credit note is sent to LaBoutik if a cashless server is configured.
CSV export includes a "Credit note ref." column for traceability.

**Fichiers / Files:**
- `BaseBillet/models.py` — status `CREDIT_NOTE`, FK `credit_note_for`
- `BaseBillet/signals.py` — transition CREATED → CREDIT_NOTE
- `Administration/admin_tenant.py` — `LigneArticleAdmin.emettre_avoir()`
- `Administration/importers/lignearticle_exporter.py` — colonne export
- `BaseBillet/migrations/0199_credit_note_lignearticle.py`

**Annulation adhesion avec avoir :**
L'action "Annuler" sur une adhesion affiche desormais une page de confirmation.
Si l'adhesion a des lignes de vente payees, l'admin peut choisir "Annuler et creer un avoir".
Les avoirs sont crees pour chaque ligne VALID/PAID liee a l'adhesion.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.cancel()` (GET/POST avec confirmation)
- `Administration/templates/admin/membership/cancel_confirm.html` (nouveau)

---

### 2. Correction annulation reservation admin (cheque, especes) / Fix admin reservation cancellation (non-Stripe)

**FR :**
Quand un admin annulait une reservation creee manuellement (payee par cheque, especes, etc.),
aucune ligne de remboursement ou d'avoir n'etait creee. La reservation passait en "annulee"
sans trace comptable, car `cancel_and_refund_resa` ne cherchait les LigneArticle que via
les `Paiement_stripe` (FK), et les reservations admin n'en ont pas.
Desormais, lors de l'annulation, un avoir (CREDIT_NOTE) est automatiquement cree pour chaque
LigneArticle hors-Stripe (sale_origin=ADMIN) liee a la reservation.
Meme correction pour l'annulation de ticket individuel (`cancel_and_refund_ticket`).

**EN:**
When an admin cancelled a manually created reservation (paid by check, cash, etc.),
no refund or credit note line was created. The reservation was marked as cancelled
with no accounting trace, because `cancel_and_refund_resa` only looked for LigneArticle
via `Paiement_stripe` (FK), and admin reservations don't have one.
Now, upon cancellation, a credit note (CREDIT_NOTE) is automatically created for each
non-Stripe LigneArticle (sale_origin=ADMIN) linked to the reservation.
Same fix for single ticket cancellation (`cancel_and_refund_ticket`).

**Fichiers / Files:**
- `BaseBillet/models.py` — `Reservation._lignes_hors_stripe()`, `Reservation._creer_avoir()`,
  `cancel_and_refund_resa()`, `cancel_and_refund_ticket()`

---

### 3. FK reservation sur LigneArticle / Reservation FK on LigneArticle

**FR :**
Ajout d'une FK directe `LigneArticle.reservation` pour lier une ligne comptable a sa reservation
sans dependre de `Paiement_stripe` comme intermediaire.
Avant, les reservations admin (cheque, especes) n'avaient aucun lien vers leurs LigneArticle.
La FK est renseignee dans les 4 flows de creation (front, API v1, API v2, admin).
Une data migration backfill les lignes existantes depuis `paiement_stripe.reservation`.
Les methodes `articles_paid()` et `_lignes_hors_stripe()` utilisent la FK directe
avec fallback sur l'ancien chemin pour compatibilite.

**EN:**
Added a direct FK `LigneArticle.reservation` to link an accounting line to its reservation
without relying on `Paiement_stripe` as intermediary.
Previously, admin reservations (check, cash) had no link to their LigneArticle.
The FK is set in all 4 creation flows (front, API v1, API v2, admin).
A data migration backfills existing lines from `paiement_stripe.reservation`.
`articles_paid()` and `_lignes_hors_stripe()` use the direct FK with legacy fallback.

**Fichiers / Files:**
- `BaseBillet/models.py` — FK `reservation` + simplification `articles_paid()`, `_lignes_hors_stripe()`
- `BaseBillet/validators.py` — `reservation=reservation` (front)
- `ApiBillet/serializers.py` — `reservation=reservation` (API v1)
- `api_v2/serializers.py` — `reservation=reservation` (API v2)
- `Administration/admin_tenant.py` — `reservation=reservation` (admin)
- `BaseBillet/migrations/0200_add_reservation_fk_to_lignearticle.py`
- `BaseBillet/migrations/0201_backfill_lignearticle_reservation.py`

---

### 4. Correction niveau de log API Brevo / Fix Brevo API log level

**FR :**
Quand un admin testait sa cle API Brevo depuis la configuration et que la cle etait invalide,
l'erreur 401 remontait en `logger.error` dans Sentry, polluant les alertes.
C'est une erreur de configuration utilisateur, pas un bug applicatif.
Le niveau de log est passe a `logger.warning`.

**EN:**
When an admin tested their Brevo API key from the configuration and the key was invalid,
the 401 error was logged as `logger.error` in Sentry, polluting alerts.
This is a user configuration error, not an application bug.
Log level changed to `logger.warning`.

**Fichiers / Files:** `Administration/admin_tenant.py` — `BrevoConfigAdmin.test_api_brevo()`

---

### 5. Correction deconnexion automatique apres 3 mois / Fix automatic logout after 3 months

**FR :**
Les utilisateurs etaient deconnectes apres exactement 3 mois, meme s'ils utilisaient le site quotidiennement.
Cause : `SESSION_SAVE_EVERY_REQUEST` n'etait pas defini (defaut Django = `False`),
donc le cookie de session n'etait renouvele que lors de modifications de la session, pas a chaque visite.
Ajout de `SESSION_SAVE_EVERY_REQUEST = True` pour que chaque visite renouvelle le cookie.

**EN:**
Users were logged out after exactly 3 months, even when using the site daily.
Cause: `SESSION_SAVE_EVERY_REQUEST` was not set (Django default = `False`),
so the session cookie was only renewed when the session was modified, not on every visit.
Added `SESSION_SAVE_EVERY_REQUEST = True` so every visit renews the cookie.

**Fichiers / Files:** `TiBillet/settings.py`

---

### 6. Bouton "Ajouter un paiement" sur les adhesions en attente / "Add payment" button on pending memberships

**FR :**
Les admins de lieux recoivent des adhesions remplies en ligne mais payees sur place
(especes, cheque, virement). Ces adhesions restaient bloquees en "attente de paiement"
sans moyen de les valider depuis l'admin.
Nouveau bouton "Ajouter un paiement" sur la page detail d'une adhesion en attente (WP ou AW).
Le formulaire demande le montant et le moyen de paiement, puis declenche toute la chaine :
creation de la ligne de vente, calcul de la deadline, envoi de l'email de confirmation,
transaction Fedow, et notification LaBoutik.

**EN:**
Venue admins receive memberships filled out online but paid on-site
(cash, check, bank transfer). These memberships were stuck in "waiting for payment"
with no way to validate them from the admin.
New "Add payment" button on the detail page of a pending membership (WP or AW).
The form asks for the amount and payment method, then triggers the full chain:
sale line creation, deadline calculation, confirmation email,
Fedow transaction, and LaBoutik notification.

**Fichiers / Files:**
- `Administration/admin_tenant.py` — `MembershipAdmin.ajouter_paiement()`
- `Administration/templates/admin/membership/ajouter_paiement.html` (nouveau / new)

---

## v1.6.8 — Corrections Sentry + Import/Export Events

**Date :** Fevrier 2026
**Migration :** Non

---

### 1. Correction boucle infinie sur ProductFormField.save() / Fix infinite loop on ProductFormField.save()

**FR :**
Quand le label d'un champ de formulaire dynamique generait un slug de 64 caracteres ou plus,
la generation de nom unique entrait dans une boucle infinie (le suffixe etait tronque puis identique a chaque tour).
Le serveur finissait par un `SystemExit`.
On utilise maintenant un fragment d'UUID pour garantir l'unicite en un seul essai.

**EN:**
When a dynamic form field label produced a slug of 64+ characters,
the unique name generation entered an infinite loop (the suffix was truncated to the same value each iteration).
The server ended up with a `SystemExit`.
We now use a UUID fragment to guarantee uniqueness in a single attempt.

**Fichiers / Files:** `BaseBillet/models.py` — `ProductFormField.save()`

---

### 2. Correction timeout cashless / Fix cashless ReadTimeout

**FR :**
L'appel HTTP vers le serveur cashless avait un timeout de 1 seconde, trop court en production.
Passe a 10 secondes.

**EN:**
The HTTP call to the cashless server had a 1-second timeout, too short for production.
Increased to 10 seconds.

**Fichiers / Files:** `BaseBillet/tasks.py`

---

### 3. Correction creation de tenant en doublon / Fix duplicate tenant creation

**FR :**
Quand un utilisateur cliquait deux fois sur le lien de confirmation email,
la creation du tenant pouvait echouer car le lien `WaitingConfiguration → tenant` n'etait pas assigne assez tot.
On assigne maintenant le tenant des sa creation, et on ajoute un fallback qui repare le lien si le tenant existe deja.

**EN:**
When a user clicked the email confirmation link twice,
tenant creation could fail because the `WaitingConfiguration → tenant` link was not assigned early enough.
We now assign the tenant immediately after creation, and added a fallback that repairs the link if the tenant already exists.

**Fichiers / Files:** `BaseBillet/validators.py`, `BaseBillet/views.py`

---

### 4. Correction carte perdue 404 / Fix lost_my_card 404

**FR :**
Quand un utilisateur cliquait deux fois sur "carte perdue", le deuxieme appel a Fedow renvoyait un 404
car la carte etait deja detachee. On attrape maintenant cette erreur proprement.

**EN:**
When a user double-clicked "lost my card", the second call to Fedow returned a 404
because the card was already detached. We now catch this error gracefully.

**Fichiers / Files:** `BaseBillet/views.py` — `admin_lost_my_card`, `lost_my_card`

---

### 5. Correction formulaire adhesion admin sans wallet / Fix admin membership form without wallet

**FR :**
Dans l'admin, le formulaire d'adhesion plantait si on validait le numero de carte
sans avoir d'abord renseigne un email valide (attribut `user_wallet_serialized` absent).
On verifie maintenant que le wallet existe avant d'y acceder.

**EN:**
In the admin, the membership form crashed when validating the card number
without first providing a valid email (missing `user_wallet_serialized` attribute).
We now check the wallet exists before accessing it.

**Fichiers / Files:** `Administration/admin_tenant.py` — `MembershipForm.clean_card_number()`

---

### 6. Verification SEPA Stripe avant activation / Stripe SEPA capability check before activation

**FR :**
Activer le paiement SEPA dans la configuration alors que le compte Stripe Connect n'a pas la capacite SEPA
provoquait une erreur au moment du paiement. On verifie maintenant la capacite SEPA via l'API Stripe
au moment de la sauvegarde de la configuration. Si le checkout echoue malgre tout, le SEPA est desactive automatiquement.

**EN:**
Enabling SEPA payment in the configuration while the Stripe Connect account lacked SEPA capability
caused an error at checkout time. We now verify SEPA capability via the Stripe API
when saving the configuration. If checkout still fails, SEPA is automatically disabled.

**Fichiers / Files:** `BaseBillet/models.py` — `Configuration.check_stripe_sepa_capability()`, `PaiementStripe/views.py`

---

### 7. Tri des produits par poids / Product weight ordering

**FR :**
Les prix affiches sur la page evenement ignoraient le poids (`poids`) du produit parent.
Les produits sont maintenant tries par `product__poids`, puis `order`, puis `prix`.

**EN:**
Prices displayed on the event page ignored the parent product's weight (`poids`).
Products are now sorted by `product__poids`, then `order`, then `prix`.

**Fichiers / Files:** `BaseBillet/views.py`

---

### 8. Import/Export CSV des evenements (PR #351) / CSV import/export for events (PR #351)

**FR :**
Contribution de @AoiShidaStr : ajout de l'import/export CSV des evenements depuis l'admin Django.
Ameliore ensuite avec : export de l'adresse postale par nom (pas par ID),
lignes identiques ignorees a l'import, et rapport des lignes ignorees.

**EN:**
Contribution by @AoiShidaStr: added CSV import/export for events from the Django admin.
Then improved with: postal address exported by name (not ID),
unchanged rows skipped on import, and skipped rows reported.

**Fichiers / Files:** `Administration/admin_tenant.py` — `EventResource`

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*

---

## v1.6.4 — Migration requise

**Date :** Fevrier 2025
**Migration :** Oui (`migrate_schemas --executor=multiprocessing`)

---

### 1. Moteur de skin configurable / Configurable skin engine

**FR :**
Nous pouvons maintenant choisir son theme graphique depuis l'administration.
Un nouveau champ `skin` a ete ajoute au modele `Configuration`.
Le systeme cherche d'abord le template dans le dossier du skin choisi,
puis retombe automatiquement sur le theme par defaut (`reunion`) si le template n'existe pas.
Cela permet de creer un nouveau skin en ne surchargeant que les templates souhaités.

**EN:**
Each venue can now choose its visual theme from the admin panel.
A new `skin` field has been added to the `Configuration` model.
The system first looks for the template in the chosen skin folder,
then automatically falls back to the default theme (`reunion`) if the template does not exist.
This allows creating a new skin by only overriding the desired templates.

**Details techniques / Technical details:**

- Nouveau champ `Configuration.skin` (CharField, defaut `"reunion"`)
  New field `Configuration.skin` (CharField, default `"reunion"`)
- Nouvelle fonction `get_skin_template(config, path)` avec logique de fallback
  New function `get_skin_template(config, path)` with fallback logic
- Ajout du skin `faire_festival` (theme brutaliste) avec templates et CSS dedies
  Added `faire_festival` skin (brutalist theme) with dedicated templates and CSS
- Migration : `BaseBillet/migrations/0195_configuration_skin.py`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — resolution dynamique des templates
- `BaseBillet/models.py` — champ `skin` sur `Configuration`
- `BaseBillet/templates/faire_festival/` — nouveau dossier skin complet
- `BaseBillet/static/faire_festival/css/` — styles dedies
- `Administration/admin_tenant.py` — champ expose dans l'admin

---

### 2. Pre-remplissage des formulaires d'adhesion / Membership form pre-fill

**FR :**
Quand un utilisateur connecte remplit un formulaire d'adhesion,
le systeme recherche sa derniere adhesion au meme produit.
Si une adhesion precedente existe, tous les champs du formulaire dynamique
sont pre-remplis avec les valeurs deja saisies.
L'utilisateur n'a plus a re-saisir son adresse, telephone, etc. a chaque renouvellement.

**EN:**
When a logged-in user fills out a membership form,
the system looks up their most recent membership for the same product.
If a previous membership exists, all dynamic form fields
are pre-filled with the previously entered values.
The user no longer has to re-enter their address, phone, etc. on each renewal.

**Details techniques / Technical details:**

- Recherche de la derniere `Membership` du user pour le meme produit avec `custom_form` non vide
  Lookup of the user's latest `Membership` for the same product with non-empty `custom_form`
- Construction d'un dict `prefill` qui mappe `field.name` vers la valeur stockee
  Builds a `prefill` dict mapping `field.name` to the stored value
- Tous les types de champs supportes : texte, textarea, select, radio, checkbox, multi-select
  All field types supported: text, textarea, select, radio, checkbox, multi-select
- Nouveau filtre de template `get_item` pour acceder aux cles d'un dict dans le template
  New `get_item` template filter for dict key lookup in templates

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — logique de pre-remplissage dans `MembershipMVT.retrieve()`
- `BaseBillet/templates/reunion/views/membership/form.html` — affichage des valeurs pre-remplies
- `BaseBillet/templatetags/tibitags.py` — filtre `get_item`

---

### 3. Edition des formulaires dynamiques depuis l'admin / Admin custom form field editing

**FR :**
Les administrateurs peuvent maintenant modifier les reponses d'un formulaire dynamique
directement depuis la fiche adhesion dans l'admin, sans passer par le shell ou la base de donnees.
Ils peuvent aussi ajouter des champs libres (non definis dans le produit).
Tout se fait en HTMX, sans rechargement de page.

**EN:**
Admins can now edit dynamic form responses
directly from the membership detail page in the admin panel, without using the shell or database.
They can also add free-form fields (not defined in the product).
Everything works via HTMX, without page reload.

**Details techniques / Technical details:**

- 5 nouvelles actions HTMX sur `MembershipMVT` :
  5 new HTMX actions on `MembershipMVT`:
  - `admin_edit_json_form` (GET) — affiche le formulaire editable / shows editable form
  - `admin_cancel_edit` (GET) — annule l'edition / cancels editing
  - `admin_change_json_form` (POST) — valide et sauvegarde / validates and saves
  - `admin_add_custom_field_form` (GET) — formulaire d'ajout de champ / add field form
  - `admin_add_custom_field` (POST) — sauvegarde le nouveau champ / saves new field
- Validation des champs requis, anti-doublon sur les labels, sanitisation HTML via `nh3`
  Required field validation, duplicate label check, HTML sanitization via `nh3`
- Chaque type de champ (`ProductFormField`) est rendu avec le bon widget HTML
  Each field type (`ProductFormField`) is rendered with the appropriate HTML widget
- Support des champs "orphelins" (presents dans le JSON mais pas dans le produit)
  Support for "orphan" fields (present in JSON but not defined in the product)
- Protection par `TenantAdminPermission`

**Fichiers concernes / Files involved:**
- `BaseBillet/views.py` — actions HTMX
- `Administration/utils.py` — fonction `clean_text()` (sanitisation `nh3`)
- `Administration/templates/admin/membership/custom_form.html` — vue lecture avec boutons
- `Administration/templates/admin/membership/partials/custom_form_edit.html` — formulaire editable
- `Administration/templates/admin/membership/partials/custom_form_edit_success.html` — confirmation
- `Administration/templates/admin/membership/partials/custom_form_add_field.html` — ajout de champ
- `BaseBillet/models.py` — correction de `ProductFormField.save()` (ne pas ecraser `name`)
- `BaseBillet/validators.py` — recherche de cle robuste avec fallback UUID/label

---

### Autres ameliorations / Other improvements

- **Duplication de produit** : nouvelle action admin pour dupliquer un produit existant
  New admin action to duplicate an existing product
- **Validation anti-doublon d'evenement** : empeche la creation d'evenements avec le meme nom et la meme date
  Prevents creating events with same name and date
- **Accessibilite** : ameliorations `aria-label`, `visually-hidden`, meilleur support des themes clair/sombre
  Accessibility improvements: `aria-label`, `visually-hidden`, better light/dark theme support
- **Tests E2E** : nouveau test Playwright pour le cycle complet d'edition des formulaires dynamiques
  New Playwright test for the full dynamic form editing cycle

---

*Lespass est un logiciel libre sous licence AGPLv3, developpe par la Cooperative Code Commun.*
*Lespass is free software under AGPLv3 license, developed by Cooperative Code Commun.*
