# Session marathon onboard + landing : hotfix prod + UX + i18n / Onboard marathon: prod hotfix + UX + i18n

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
