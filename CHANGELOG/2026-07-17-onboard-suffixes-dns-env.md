# Suffixes DNS de l'onboarding dérivés de l'environnement / Onboarding DNS suffixes from env

**Date :** 2026-07-17
**Migration :** Non

## Resume / Summary
**Quoi / What :** Le formulaire de création d'un nouveau tenant (onboard) ne
propose plus des suffixes de domaine codés en dur (`tibillet.coop`, `tibillet.re`).
Il dérive désormais la liste depuis les variables d'environnement `DOMAIN` et
`ADDITIONAL_DOMAINS`, via une source unique `onboard.services.dns_suffixes_disponibles()`.
The new-tenant onboarding form no longer offers hardcoded domain suffixes; it
derives the list from the `DOMAIN` and `ADDITIONAL_DOMAINS` environment variables
through a single source of truth.

**Pourquoi / Why :** Sur une nouvelle install, l'onboard imposait `tibillet.coop`/
`tibillet.re` quels que soient les domaines réellement servis. Les variables
`DOMAIN` (wildcard principal) et `ADDITIONAL_DOMAINS` (modèle SaaS multi-domaine)
existaient déjà pour ALLOWED_HOSTS/CSRF mais étaient ignorées par l'onboard. Un
déploiement configure maintenant ses suffixes en éditant son `.env`, sans toucher
au code. On a aussi retiré le forçage `if DEBUG: dns='tibillet.localhost'` (en dev,
`DOMAIN` vaut déjà `tibillet.localhost`).
A fresh install forced `tibillet.coop`/`tibillet.re`. The env vars already existed
for ALLOWED_HOSTS/CSRF but the onboard ignored them. The DEBUG suffix override was
also removed.

**Règle de priorité / Priority rule :** le 1er suffixe de la liste est le choix par
défaut du formulaire. `tibillet.coop` puis `tibillet.localhost` sont remontés en tête
s'ils sont présents (dans `DOMAIN` **ou** `ADDITIONAL_DOMAINS`), sinon `DOMAIN` en
premier. / The 1st suffix is the form default; `tibillet.coop` then
`tibillet.localhost` are floated to the front when present.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `onboard/services.py` | + `dns_suffixes_disponibles()` (source unique) + `SUFFIXES_DNS_PREFERES` |
| `onboard/serializers.py` | `DNS_CHOICES`/`DNS_DEFAUT` dérivés de l'env ; retrait forçage DEBUG dans `validate()` |
| `onboard/views.py` | `venue()` passe `dns_choices` au template ; initial dérivé |
| `onboard/templates/onboard/steps/03_venue.html` | radios générées par boucle sur `dns_choices` ; preview sans domaine en dur |
| `BaseBillet/validators.py` | construction du domaine final : suffixe dérivé, retrait forçage DEBUG |
| `onboard/management/commands/create_empty_tenant.py` | domaine technique du pool dérivé du 1er suffixe |
| `Administration/management/commands/batch_new_tenant.py` | résidu `base_domain = 'tibillet.coop'` remplacé par le 1er suffixe dérivé de l'env |
| `onboard/tests/*.py` | `dns_choice` de test aligné sur `tibillet.localhost` (DOMAIN de test) |
| `onboard/tests/test_services_dns.py` | **nouveau** : tests unitaires de la fonction |

---

## Comment tester (a la main) / Manual test

### Test 1 — dev (DOMAIN=tibillet.localhost)
1. Aller sur l'onboarding, étape « Votre lieu ».
2. Attendu : les boutons radio de suffixe affichent `tibillet.localhost` (+ `domainbis.localhost`
   si `ADDITIONAL_DOMAINS` le contient). Plus de `.coop`/`.re` en dur.
3. L'aperçu « Votre adresse finale » montre `<slug>.tibillet.localhost`.

### Test 2 — priorité tibillet.coop en prod
1. Config prod avec `DOMAIN=tibillet.re` et `ADDITIONAL_DOMAINS=tibillet.coop,...`.
2. Attendu : `tibillet.coop` apparaît **en premier** (coché par défaut) dans le formulaire.

### Test 3 — création réelle d'un tenant
1. Finaliser un onboarding en dev (slug `mon-lieu`, suffixe `tibillet.localhost`).
2. Attendu : le tenant est créé avec le domaine `mon-lieu.tibillet.localhost`.

### Verifs
- `docker exec lespass_django poetry run python /DjangoFiles/manage.py check` -> 0 issue.
- `docker exec lespass_django poetry run pytest onboard/tests/ -q`
- Smoke : `dns_suffixes_disponibles()` renvoie la liste attendue selon `DOMAIN`/`ADDITIONAL_DOMAINS`.
