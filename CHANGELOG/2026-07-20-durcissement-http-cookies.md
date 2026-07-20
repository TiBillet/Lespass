# Durcissement HTTP : cookies et en-têtes / HTTP hardening: cookies and headers

**Date :** 2026-07-20
**Migration :** Non

## Resume / Summary

**Quoi / What :** Cookies de session et CSRF marqués `Secure` en production. Ajout de
`Strict-Transport-Security` et `Permissions-Policy` côté nginx. `X-Forwarded-Proto`
imposé au lieu d'être relayé. Documentation de l'état réel de la configuration CORS.
/ Session and CSRF cookies marked Secure in production. HSTS and Permissions-Policy
added in nginx. X-Forwarded-Proto hardcoded instead of relayed. CORS state documented.

**Pourquoi / Why :** Un audit externe a relevé l'absence de HSTS et des cookies sans
`Secure`. La vérification a montré que Django envoyait déjà quatre en-têtes de
sécurité par ses défauts — seuls deux manquaient réellement.
/ An external audit flagged missing HSTS and non-Secure cookies. Verification showed
Django already sent four security headers by default; only two were genuinely missing.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/settings.py` | `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` = `not DEBUG`. `SAMESITE` explicité à `Lax`. Bloc de commentaire sur l'état réel du CORS. |
| `nginx_prod/lespass_prod.conf` | `Strict-Transport-Security` et `Permissions-Policy` au niveau `server`. `proxy_set_header X-Forwarded-Proto https` dans `location /`. |

### Repartition Django / nginx — et pourquoi

| Où | Quoi | Raison |
|---|---|---|
| **Django** | Cookies `Secure` / `SameSite` | C'est Django qui émet les cookies. |
| **Django** (déjà par défaut) | `Referrer-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Cross-Origin-Opener-Policy` | Déjà envoyés. Les redéclarer dans nginx produirait un **en-tête en double**. |
| **Django** (plus tard) | CSP `frame-ancestors` | Deux vues neutralisent `X-Frame-Options` pour autoriser l'embed iframe (`BaseBillet/views.py`). L'exception vit dans le code, l'en-tête doit y rester. |
| **nginx** | `Strict-Transport-Security`, `Permissions-Policy` | Django ne les envoie pas. Et nginx voit **toutes** les réponses, y compris les 301 de `CanonicalDomainRedirectMiddleware` qui court-circuitent `SecurityMiddleware`. |

### Deux erreurs d'analyse corrigees en cours de route

**1. Le CORS n'est pas une faille — il est totalement désactivé.** Une lecture rapide de
`settings.py` laisse croire que `CORS_ALLOW_ALL_ORIGINS = True` est actif. C'est faux
sur deux plans : ce bloc est encadré par des triples guillemets (c'est une chaîne, pas
du code), et `CORS_ORIGIN_WHITELIST` est un nom de réglage **supprimé** dans
django-cors-headers 4.0 (le projet est en 4.9). Aucun réglage CORS n'est appliqué.
Comportement inchangé, un bloc de commentaire explique désormais le piège.

**2. Django envoyait déjà quatre en-têtes de sécurité.** L'audit des fichiers de
configuration ne montrait aucun `add_header` nulle part, ce qui laissait croire à une
absence totale. Un simple `curl -skI` montre que `SecurityMiddleware` et
`XFrameOptionsMiddleware` posent déjà `referrer-policy: same-origin`,
`x-content-type-options: nosniff`, `x-frame-options: DENY` et
`cross-origin-opener-policy: same-origin`. **Vérifier les réponses réelles, pas
seulement les fichiers de conf.**

### Pieges nginx documentes dans le fichier

- **`add_header` n'est hérité que si le bloc enfant n'en déclare aucun.** `location
  /static` et ses trois sous-blocs posent un `add_header Cache-Control`, donc ils ne
  reçoivent pas les en-têtes de sécurité. Accepté : ce sont nos propres assets
  versionnés.
- **CORRECTION (audit du 2026-07-20)** — une version antérieure de ce document
  affirmait que `location /media` héritait des en-têtes de sécurité. **C'était
  faux, et dans les deux sens :** nginx ne pose au niveau `server` que HSTS et
  `Permissions-Policy` ; le `nosniff` vient de Django, or `/media` est servi
  directement depuis le disque et ne passe jamais par Django. Ces réponses
  partaient donc sans aucune protection, alors que le dossier est **partagé par
  tous les tenants** et contient des dépôts d'utilisateurs. `location /media` pose
  désormais explicitement `nosniff` et `X-Frame-Options`, et un bloc `location ~*`
  renvoie 404 sur toute extension exécutable (`.html`, `.svg`, `.js`, `.php`…) —
  `nosniff` seul ne suffisait pas, puisqu'il empêche de deviner un type mais pas
  de servir un `.html` déclaré `text/html`. Côté modèle, `Bloc.video` n'acceptait
  aucune validation d'extension : une liste blanche a été ajoutée
  (`pages.models.valider_extension_video`, migration `pages/0012`).
  **Conséquence directe du piège ci-dessus** : en posant ses propres `add_header`,
  `location /media` a cessé d'hériter de HSTS et `Permissions-Policy`. Les deux
  sont donc recopiés dans le bloc. Toute ligne ajoutée au niveau `server` devra
  l'être ici aussi — c'est précisément le piège que ce document décrit.
- **`always` est obligatoire**, sinon les réponses 4xx/5xx partent sans en-tête.

---

## Comment tester (a la main) / Manual test

### Test 1 — en local, rien ne doit changer

`DEBUG=1` en dev, donc `SESSION_COOKIE_SECURE = False`. Se connecter sur
`https://lespass.tibillet.localhost/`, vérifier que la session tient.

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c \
  "from django.conf import settings; print(settings.DEBUG, settings.SESSION_COOKIE_SECURE)"
```
Doit afficher `True False` en dev.

### Test 2 — après déploiement en prod

```bash
curl -sI https://<domaine>/ | grep -iE "strict-transport|permissions-policy|set-cookie"
```
Attendu :
- `strict-transport-security: max-age=86400; includeSubDomains`
- `permissions-policy: camera=(self), geolocation=(self), ...`
- les `set-cookie` portent `Secure` **et** `SameSite=Lax`

Vérifier aussi qu'**aucun en-tête n'apparaît deux fois** :
```bash
curl -sI https://<domaine>/ | awk '{print tolower($1)}' | sort | uniq -d
```
Ne doit rien renvoyer (hors `set-cookie`, légitimement multiple).

### Test 3 — parcours sensibles à SameSite

1. Faire un paiement Stripe de bout en bout et vérifier qu'on revient **connecté**.
2. Demander un lien de connexion par e-mail, l'ouvrir depuis le client mail, vérifier
   que la connexion aboutit.

Ces deux parcours sont des navigations cross-site : ce sont eux qui casseraient si
quelqu'un passait `SameSite` en `Strict`.

### Test 4 — scan externe

Relancer Mozilla Observatory. Le score doit remonter (HSTS était à 0 %).

### Tests automatiques

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/ -q
```
923 tests, tous verts au moment de l'écriture.

```bash
docker run --rm --network lespass_backend \
  -v "$PWD/nginx_prod/lespass_prod.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:latest nginx -t
```
Doit afficher `syntax is ok` (l'erreur sur `/logs` est normale hors compose).

---

## A FAIRE / TODO

1. **Monter le `max-age` du HSTS.** Il est volontairement à **86400 (1 jour)**, pas à
   1 an. Un HSTS est irréversible côté navigateur : tant que le délai court, un
   visiteur ayant reçu l'en-tête ne peut plus joindre le site en HTTP, même si le
   certificat expire. Après une semaine sans incident, passer à `31536000`.
2. **Ne pas ajouter `preload`** tant que le domaine canonique du projet n'est pas
   stabilisé (migration `tibillet.org` → `tibillet.coop` en cours). La désinscription
   de la liste preload des navigateurs prend plusieurs mois.
3. **CSP — chantier séparé, non fait ici.** Une CSP stricte est hors de portée en
   l'état : le codebase contient **73 attributs `onclick=`**, 71 blocs `<script>`
   inline, 1503 `style=` inline et de l'Alpine.js. Les gestionnaires inline ne sont
   couverts ni par nonce ni par hash — ils exigent littéralement `'unsafe-inline'`.
   Chemin réaliste : `Content-Security-Policy-Report-Only` tolérant `unsafe-inline`
   sur script/style mais verrouillant `frame-ancestors`, `base-uri` et `object-src`,
   posée **côté Django** à cause de l'exception iframe de `BaseBillet/views.py`.
4. **nginx dev non modifié** (`nginx/lespass_dev.conf`). Volontaire : un HSTS sur
   `*.localhost` gênerait le développement sans rien apporter.
5. **`CSRF_TRUSTED_ORIGINS` contient une entrée morte** : `https://.{DOMAIN}` (point
   de tête sans joker), que Django ne matchera jamais. Cosmétique, non corrigé pour
   rester dans le périmètre de cette session.
