# 404 du schema public : plus de requete SQL en erreur, scans WordPress coupes par nginx / Public-schema 404: no failing SQL query, WordPress scans cut by nginx

**Date :** 2026-07-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** la page 404 rendue sur le schema `public` ne tente plus d'appeler
`get_context()`, et nginx (prod) ferme les sondes WordPress (`/wp-*`, `xmlrpc.php`,
`wlwmanifest.xml`) sans les transmettre a Django.
/ The 404 page rendered on the `public` schema no longer calls `get_context()`, and
nginx (prod) closes WordPress probes without forwarding them to Django.

**Pourquoi / Why :** les memes handlers 404/500 servent l'URLconf public
(`TiBillet/urls_public.py`) et les tenants, mais `get_context()` ne lit que des
TENANT_APPS (`Configuration`, `CrowdConfig`, `Carrousel`, `Page`) dont les tables
n'existent pas dans `public`. Chaque 404 du root — les robots en produisent en continu —
declenchait donc un `SELECT` sur une table absente : `ERROR relation
"BaseBillet_configuration" does not exist` cote PostgreSQL, rattrape par l'`except` en
`WARNING page erreur : get_context indisponible, repli classic`. La page s'affichait
correctement, mais au prix d'une requete en erreur et de deux lignes de log par sonde.
/ The same 404/500 handlers serve the public URLconf and the tenants, but
`get_context()` only reads TENANT_APPS whose tables do not exist in `public`. Every root
404 fired a SELECT on a missing table: a PostgreSQL ERROR caught by the except clause.
The page rendered fine, at the cost of a failing query and two log lines per probe.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `_contexte_page_erreur()` : garde `connection.schema_name == "public"` avant le `try`, rend le socle `pages/classic/` directement (shell ou headless selon HTMX) |
| `nginx_prod/lespass_prod.conf` | Deux `location` en `return 444` : `^/wp-` et `^/(xmlrpc\.php\|wlwmanifest\.xml)$` |
| `tests/pytest/test_handlers_erreur.py` | Nouveau test : la 404 sur `public` se rend avec zero requete SQL |

Le `try/except` reste en place sous la garde : il couvre les vrais cas degrades
(tenant casse, base injoignable), ou une page d'erreur doit TOUJOURS pouvoir s'afficher.
/ The try/except stays below the guard, covering genuinely degraded cases.

**Effet de bord voulu :** la 404 du schema public devient swappable en HTMX (le repli
renvoyait toujours le shell complet, meme sur une requete HTMX).
/ Intended side effect: the public 404 is now HTMX-swappable.

---

## Comment tester (a la main) / Manual test

### Test 1 — plus de bruit dans les logs sur une 404 du root

1. Ouvrir les logs docker : `docker compose logs -f lespass_django lespass_postgres`
2. Frapper une URL inexistante sur le **domaine racine** (pas un tenant) :
   `curl -sk -o /dev/null -w '%{http_code}\n' https://tibillet.localhost/wp-json/`
3. Attendu : `404`, et **aucune** ligne `ERROR relation "BaseBillet_configuration" does
   not exist` cote postgres, **aucun** `WARNING page erreur : get_context indisponible`
   cote django.
4. Avant le correctif, la meme commande produisait les deux.

### Test 2 — la 404 d'un tenant n'a pas bouge

1. `curl -sk https://lespass.tibillet.localhost/page-qui-nexiste-pas/ | head -30`
2. Attendu : la 404 habituelle, **avec le skin du tenant** (navbar, logo, couleurs).
   La garde ne doit s'appliquer qu'au schema `public`.

### Test 3 — nginx coupe les scans (prod uniquement)

En dev, `nginx_prod/lespass_prod.conf` n'est pas monte : ce test se fait en pre-prod/prod.

1. `curl -sk -o /dev/null -w '%{http_code}\n' https://<domaine-prod>/wp-login.php`
   Attendu : `000` (connexion fermee sans reponse — c'est le `444`).
2. `curl -sk -o /dev/null -w '%{http_code}\n' https://<domaine-prod>/xmlrpc.php`
   Attendu : `000`.
3. Verifier qu'une page normale repond toujours :
   `curl -sk -o /dev/null -w '%{http_code}\n' https://<domaine-prod>/event/` -> `200`.
4. Verifier que la requete n'atteint plus Django : aucune ligne `/wp-login.php` dans les
   logs gunicorn, alors qu'elle reste visible dans `/logs/nginxAccess.log`.

**Point de vigilance :** `location ~* ^/wp-` intercepte aussi une `Page` de l'app `pages`
dont le slug commencerait par `wp-` (le slug est libre cote admin). Aucun tenant n'en a
au 2026-07-21. Si le cas se presente, restreindre le motif aux chemins WordPress reels
(`wp-admin|wp-login|wp-content|wp-includes|wp-json|wp-config`) plutot que d'ajouter une
exception. Meme famille de piege que le slug qui tombait en 403 sur une `re_path` non
ancree.

### Tests automatiques / Automated tests

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_handlers_erreur.py -q
```

Attendu : `4 passed`. Le nouveau test
`test_handler404_sur_schema_public_ne_touche_pas_la_base` echoue si la garde disparait
(verifie en la neutralisant : il reproduit exactement le `WARNING` d'origine).

### Verification de la syntaxe nginx

```bash
docker run --rm --network lespass_backend \
  -v $PWD/nginx_prod/lespass_prod.conf:/etc/nginx/conf.d/default.conf:ro \
  nginx:alpine nginx -t
```

Attendu : `syntax is ok`. (Le conteneur jetable n'a pas `/logs`, l'echec sur
`open() "/logs/nginxAccess.log"` est normal hors production.)
