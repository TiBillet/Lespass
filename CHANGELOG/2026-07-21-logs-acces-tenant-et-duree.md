# Logs d'accès : le tenant, l'IP du visiteur et la durée des requêtes / Access logs: tenant, visitor IP and request duration

**Date :** 2026-07-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** nginx et Gunicorn journalisent desormais le **tenant** (`Host`), la **vraie
IP du visiteur** et la **duree** de chaque requete. Cote nginx, la duree est scindee en deux :
temps total et temps passe dans Gunicorn.
/ nginx and Gunicorn now log the **tenant** (`Host`), the **real visitor IP** and the
**duration** of each request. On nginx the duration is split in two: total time and time
spent in Gunicorn.

**Pourquoi / Why :** les deux serveurs utilisaient leur format par defaut, qui ne journalise
que le chemin (`GET /blog/ HTTP/1.1`). En multi-tenant, **deux lieux differents produisent des
lignes identiques** : impossible de savoir de quel tenant vient une requete. Cote Gunicorn,
`%(h)s` journalise en plus l'IP de nginx (`172.20.0.x`) pour 100 % des lignes, puisque tout le
trafic arrive par le proxy — la vraie IP du visiteur n'apparaissait nulle part.

Sans duree, il etait egalement impossible de trancher entre une lenteur reseau et une lenteur
applicative lors d'un diagnostic de performance.
/ Both servers used their default format, which logs only the path — in multi-tenant, two
different venues produce identical lines. Gunicorn also logged nginx's IP for every request.
And without timing, a slowness report could not be traced to network vs application.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `nginx_prod/lespass_prod.conf` | nouveau `log_format tibillet` (contexte `http`), reference par `access_log` ; bloc `set_real_ip_from` / `real_ip_header` / `real_ip_recursive` |
| `supervisor/conf.d/gunicorn.conf` | ajout de `--access-logformat` sur la ligne `command=` |

### La vraie IP demande `real_ip`, pas seulement un champ de log

Journaliser `$remote_addr` ne suffit pas : cette variable contient l'IP de **qui ouvre la
connexion vers nginx**, c'est-a-dire **Traefik** (`172.18.0.x`), sur 100 % des lignes. La
seule facon d'obtenir le visiteur est de reconstruire l'adresse depuis `X-Forwarded-For`,
ce que fait le module `real_ip` :

```nginx
set_real_ip_from 172.16.0.0/12;   # + 10.0.0.0/8 et 192.168.0.0/16
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

`set_real_ip_from` liste les intermediaires a qui l'on fait confiance pour cet en-tete. **La
restriction aux plages privees est ce qui rend l'operation sure** : un client ne peut pas se
forger une fausse IP, puisque sa propre adresse source ne figure pas dans la liste. Elle est
correcte ici parce que nginx n'est pas expose directement — seul Traefik l'est.

`real_ip_recursive on` remonte la chaine `X-Forwarded-For` en ignorant les adresses de
confiance et retient la premiere qui n'en est pas une : la bonne des qu'il y a plus d'un
proxy en amont.

/!\ Ceci corrige `$remote_addr` pour **tout le serveur**, pas seulement le log : toute regle
future basee dessus (`limit_req`, `allow`/`deny`) verra elle aussi la vraie IP. C'est voulu.

### Ce que donnent les nouvelles lignes / What the new lines look like

nginx :
```
88.120.5.42 - - [21/Jul/2026:08:52:15 +0000] "GET launch-test.tibillet.localhost/event/?tag=concert HTTP/1.1" 200 42865 "-" "curl/8.21.0" rt=0.102 urt=0.102
88.120.5.42 - - [21/Jul/2026:08:52:15 +0000] "GET codecommun.coop/wp-login.php HTTP/1.1" 444 0 "-" "curl/8.21.0" rt=0.000 urt=-
```

Gunicorn :
```
88.120.5.42 launch-test.tibillet.localhost [21/Jul/2026:09:11:12 +0000] "GET /event/?tag=concert HTTP/1.1" 200 44162 212ms "-" "curl/7.74.0"
```

**Lire `rt` et `urt` :** `rt` est la duree totale vue par nginx (jusqu'au dernier octet envoye
au client, donc lenteur reseau incluse), `urt` le temps passe par Gunicorn seul. C'est
l'**ecart** qui localise une lenteur — `rt` eleve avec `urt` faible = reseau ou client lent ;
les deux eleves = applicatif Django. `urt` vaut `-` quand aucun upstream n'est sollicite
(fichier statique, `return 444`) : c'est la preuve qu'une requete n'a jamais atteint Django.

**Le schema est volontairement absent du log nginx.** Traefik termine le TLS en amont, nginx
ne voit que du http en interne : `$scheme` afficherait donc `http` pour une visite en https.

## Deux pieges rencontres / Two traps hit on the way

**1. `%(q)s` de Gunicorn rend la query string SANS son `?`.** Recomposer l'URL avec
`%(U)s%(q)s` produit `/event/tag=concert`, qui se lit comme un chemin alors que c'en est pas
un. On garde donc `%(r)s` (la ligne de requete brute) et on sort le `Host` a part.

**2. Les `%%` de `supervisor/conf.d/gunicorn.conf` sont OBLIGATOIRES.** supervisord fait une
interpolation Python sur la valeur de `command=` : un `%(t)s` simple y est lu comme une
variable supervisor, elle n'existe pas, et le demarrage echoue sur `KeyError: 't'` —
**gunicorn ne demarre alors pas du tout**. Le doublement `%%(` passe un `%(` litteral.
Les quotes simples autour du format sont tout aussi obligatoires : sans elles, shlex decoupe
le format sur les espaces et gunicorn ne recoit que le premier morceau.

**Impact operationnel :** ces formats remplacent `combined`. Tout parser de logs existant
(fail2ban, GoAccess, awstats) doit etre mis a jour, sinon il ne reconnait plus les lignes.

---

## Comment tester (a la main) / Manual test

### Test 1 — validation de la conf nginx AVANT deploiement

```bash
docker run --rm --network lespass_backend \
  -v $PWD/nginx_prod/lespass_prod.conf:/etc/nginx/conf.d/default.conf:ro \
  -v /tmp:/logs \
  nginx:alpine nginx -t
```
Attendu : `syntax is ok` et `test is successful`. Un `log_format` mal place (dans le bloc
`server` au lieu du contexte `http`) echoue ici.

### Test 2 — la ligne nginx porte bien le tenant

Apres deploiement :
```bash
tail -f /logs/nginxAccess.log
```
Puis visiter deux tenants differents. Attendu : deux lignes **distinguables**, chacune avec
son `Host`, et `rt=` / `urt=` renseignes.

### Test 3 — Gunicorn demarre toujours (LE test qui compte)

Le risque de ce chantier est concentre ici : une erreur d'echappement et **gunicorn ne
demarre pas**. Apres deploiement :

```bash
docker exec lespass_django supervisorctl status gunicorn
```
Attendu : `RUNNING`. Si `FATAL` ou `BACKOFF` :
```bash
docker exec lespass_django tail -30 /DjangoFiles/logs/supervisor/supervisord.log
```
Un `KeyError` dans ce fichier signale un `%` non double dans `--access-logformat`.

Verification prealable possible sans rien deployer, en simulant ce que fait supervisord :
```bash
python3 -c "
import shlex
ligne = next(l for l in open('supervisor/conf.d/gunicorn.conf') if l.startswith('command='))[8:].strip()
apres = ligne % {'program_name':'gunicorn','here':'/DjangoFiles','process_num':'0','group_name':'gunicorn','numprocs':'1'}
m = shlex.split(apres)
print('OK — format recu :', m[m.index('--access-logformat')+1])
"
```
Attendu : la ligne s'affiche sans exception. Un `KeyError` ici = gunicorn ne demarrerait pas.

### Test 4 — la ligne Gunicorn porte l'IP du visiteur

```bash
docker exec lespass_django tail -f /DjangoFiles/logs/gunicorn.logs
```
Visiter une page depuis l'exterieur. Attendu : la **vraie IP publique** en debut de ligne, pas
`172.20.0.x`. Si l'IP de nginx apparait encore, verifier que nginx transmet bien
`X-Forwarded-For` (`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`, deja
present dans `location /`).

### Tests automatiques / Automated tests

Aucun : il s'agit de configuration de serveurs, hors du perimetre de la suite pytest. Les
verifications ci-dessus (`nginx -t`, simulation de l'expansion supervisord) en tiennent lieu
et se lancent avant tout deploiement.
