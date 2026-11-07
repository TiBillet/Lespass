# Pages dont le slug commence par « media » ou « static » : 404 nginx / Pages whose slug starts with "media" or "static": nginx 404

**Date :** 2026-11-07
**Migration :** Non

## Resume / Summary
**Quoi / What :** dans la config nginx, `location /media` et `location /static` deviennent `location /media/` et `location /static/`, en prod et en dev.
/ In the nginx config, `location /media` and `location /static` become `location /media/` and `location /static/`, in prod and dev.

**Pourquoi / Why :** un prefixe nginx compare du texte, pas des dossiers. `/mediation-numerique-villeurbanne/` etait capte par `location /media`. nginx cherchait alors le fichier sur le disque et renvoyait son propre 404, sans jamais passer la requete a Django. Toute Page dont le slug commence par `media` ou `static` etait injoignable (mediation, mediatheque, `static-...`), sur tous les lieux. L'API acceptait pourtant ces slugs.
/ An nginx prefix matches text, not folders: `/mediation-...` was caught by `location /media`, looked up on disk and answered with an nginx 404, never reaching Django. Any Page whose slug starts with `media` or `static` was unreachable on every venue.

Non concerne : `statistiques` (`statis…` ne commence pas par `static`).
/ Not affected: `statistiques`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `nginx_prod/lespass_prod.conf` | `location /static/` et `location /media/`, commentaire sur le `/` final |
| `nginx/lespass_dev.conf` | `location /media/` (et le bloc `/static/` commente) |

---

## Comment tester (a la main) / Manual test

### Avant deploiement
1. `nginx -t` dans le conteneur nginx de prod.
2. Recharger nginx (`nginx -s reload`).

### Test 1 — une page au slug en « media » s'affiche
1. Creer une Page publiee avec le slug `mediation-test`.
2. Ouvrir `https://<lieu>/mediation-test/`.
3. Attendu : la page Django s'affiche (avant : 404 nginx, page blanche « 404 Not Found »).

### Test 2 — les fichiers sont toujours servis par nginx
1. Ouvrir une image de `/media/images/...` et un fichier `/static/...css`.
2. Attendu : 200, en-tetes `X-Content-Type-Options: nosniff` et `X-Frame-Options: DENY` sur `/media/`.
3. Ouvrir `/media/<n'importe quoi>.html` : toujours 404 (regle anti-XSS inchangee).

### Test 3 — `/media` et `/static` sans slash
1. Ouvrir `/media` puis `/static`.
2. Attendu : 404 Django « Page introuvable » (avant : redirection 301 puis 403 nginx). Les slugs `media` et `static` exacts restent reserves (`SLUGS_RESERVES`).

### Reproduction faite en session
nginx 1.27 jetable, sans reseau, meme structure de `location` :
`/mediation-numerique-villeurbanne/`, `/mediaX/`, `/static-test/` -> 404 nginx avant, Django apres ;
`/media/images/1.png`, `/static/app.css`, `/static/vendor/x.css` -> 200 fichier avant et apres ;
`/media/x.html` -> 404 avant et apres. `nginx -t` OK sur les deux fichiers reels.
