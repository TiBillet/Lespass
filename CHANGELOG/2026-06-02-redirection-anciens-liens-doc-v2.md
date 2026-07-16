# Redirection des anciens liens de la doc Docusaurus v2 → doc v3

**Date :** 2026-06-02
**Migration :** Non

## Ce qui a été fait

L'ancienne documentation (Docusaurus v2) était servie sur `tibillet.org` avec des chemins
`/docs/…`, `/fr/…`, `/en/…`, `/roadmap/`, `/search/`, `/cgucgv/`. Ces chemins n'existent plus
dans Lespass. Avant, le `CanonicalDomainRedirectMiddleware` se contentait de rediriger
`tibillet.org → tibillet.coop` **en gardant le chemin** : le 404 était juste déplacé sur `.coop`.

Désormais, le middleware **rattrape ces anciens chemins** (sur le tenant ROOT uniquement) et
redirige vers la nouvelle doc (`documentation_v3` sur `tibillet.github.io`), **avant** la
redirection canonique de domaine.

### Modifications
| Fichier | Changement |
|---|---|
| `Customers/middleware.py` | Fonction pure `url_doc_v3_pour_chemin_herite(path)` (mapping testable) + méthode `_redirection_doc_heritee(request)` (ROOT public, GET/HEAD, 302), appelée avant `_redirection_canonique` |
| `tests/pytest/test_middleware_doc_redirect.py` | 26 cas DB-only sur la fonction pure |

### Table de redirection (302 temporaire)
| Ancien chemin (sur `.org`/`.coop`) | Cible v3 |
|---|---|
| `/docs/presentation/demonstration/` + `/fr/docs/presentation/demonstration/` | `…/documentation_v3/les-bases-et-valeurs-tibillet/demonstration-des-differents-modules/` |
| `/cgucgv/` + `/fr/cgucgv/` | `…/documentation_v3/les-bases-et-valeurs-tibillet/aspects-legaux-et-reglementaires/cgu-cgv/` |
| tout autre `/docs/…`, `/fr/…`, `/en/…`, `/roadmap/…`, `/search/…` | `…/documentation_v3/` (racine) |

## Tests à réaliser

### Test 1 : tests automatiques (fonction pure)
```bash
docker exec -e API_KEY=dummy lespass_django poetry run pytest tests/pytest/test_middleware_doc_redirect.py -q
# Attendu : 26 passed
```

### Test 2 : redirection réelle en dev (sur le ROOT public)
Serveur dev actif (byobu, port 8002). Le ROOT en local = `tibillet.localhost` (schema public).

```bash
# Page de démonstration → page démo v3 (302 + Location)
curl -skI "https://tibillet.localhost/docs/presentation/demonstration/" | grep -iE "HTTP|location"
# Attendu : 302 + Location: .../documentation_v3/les-bases-et-valeurs-tibillet/demonstration-des-differents-modules/

# Variante FR
curl -skI "https://tibillet.localhost/fr/docs/presentation/demonstration/" | grep -i location

# CGU/CGV
curl -skI "https://tibillet.localhost/cgucgv/" | grep -i location
# Attendu : .../documentation_v3/.../cgu-cgv/

# Préfixe générique → racine doc v3
curl -skI "https://tibillet.localhost/fr/docs/install/docker_install/" | grep -i location
# Attendu : .../documentation_v3/

curl -skI "https://tibillet.localhost/roadmap/" | grep -i location
```

### Test 3 : routes Lespass NON impactées
```bash
# La home et les vraies routes ne doivent PAS rediriger vers la doc
curl -skI "https://tibillet.localhost/" | grep -i "HTTP"          # 200, pas de redirect doc
curl -skI "https://tibillet.localhost/explorer/" | grep -i "HTTP" # 200
curl -skI "https://tibillet.localhost/lieux/" | grep -i "HTTP"    # 200
```

### Test 4 : sous-domaine tenant NON impacté
Sur un sous-domaine de tenant (ex : `lespass.tibillet.localhost`, schema ≠ public),
un chemin `/docs/…` ne doit PAS être redirigé vers la doc v3 (il suit le routing normal
du tenant, donc 404 Lespass classique). La redirection doc est limitée au ROOT public.

## Compatibilité

- **POST jamais redirigé** (webhooks Stripe, formulaires) — comme la redirection canonique.
- **302 temporaire** : passable en 301 plus tard une fois la table figée (cf. `REDIRECTION_PERMANENTE`).
- **Pas d'`i18n_patterns`** dans Lespass : `/fr` et `/en` ne sont pas des routes Django, donc
  les rediriger ne casse rien. Vérifié : aucune collision dans `seo.urls`, `onboard.urls`,
  `BaseBillet.urls`.
- **Liens `tibillet.github.io/documentation_v2/…`** : hors de portée de Django (site GitHub Pages
  séparé). Leur redirection éventuelle se ferait côté Docusaurus/GitHub Pages, pas ici.
