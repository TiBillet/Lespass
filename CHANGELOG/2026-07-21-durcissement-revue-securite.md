# Durcissement issu de la revue de sécurité / Hardening from the security review

**Date :** 2026-07-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** sept correctifs issus d'une revue de securite adversariale menee sur les
modifications de la journee — publication d'image, page d'erreur, identification du client,
confiance proxy, rotation des journaux, collisions de slug, panneaux du domaine racine.
/ Seven fixes from an adversarial security review of the day's changes: image publishing,
error page, client identification, proxy trust, log rotation, slug collisions, root-domain panels.

**Hors perimetre volontaire / Deliberately out of scope :** le hook `post_worker_init`
(`gunicorn_conf.py`) et le jeton d'authentification par email — traites sur une autre branche.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `.dockerignore` | reecrit : chemins corriges, `.git` exclu |
| `BaseBillet/views.py` | `handler500` n'expose plus l'exception ; `sans_panneaux_globaux` sur le schema public |
| `AuthBillet/utils.py` | `get_client_ip()` : `X-Real-IP` d'abord, dernier element de `X-Forwarded-For` en repli |
| `nginx_prod/lespass_prod.conf` | `set_real_ip_from` reduit a une seule plage, documente |
| `docker-compose.prod.yml` | nouveau service `logrotate` |
| `pages/models.py` | `PREFIXES_SLUGS_RESERVES` + deux slugs exacts |
| `pages/templates/pages/classic/{shell,headless}.html` | panneaux globaux conditionnels |

---

## 1. L'image Docker publiee ne contient plus l'historique git (etait : CRITIQUE)

`.dockerignore` filtrait des chemins **qui ne matchaient rien** : ils etaient prefixes
`DjangoFiles/` alors que le contexte de build est la RACINE du depot (`dockerfile` :
`COPY ./ /DjangoFiles`). Et `#.git` etait commente.

Consequence verifiee sur l'image publiee `tibillet/lespass:1.8.24` : **196 Mo de `.git`**,
plus `logs/nginxAccess.log`. Tout secret jamais commite — meme retire de HEAD depuis —
restait recuperable par `docker pull` puis `git log -p`.

Sont desormais exclus : `.git`, `certs/`, `www/` (STATIC_ROOT reconstruit au demarrage par
le `collectstatic` de `start.sh` ; MEDIA_ROOT contient les depots utilisateurs de TOUS les
tenants), `logs/`, sauvegardes et caches.
**Verifie avant exclusion :** `STATICFILES_DIRS` ne pointe pas dans `www/` — le
`collectstatic` reste complet. `static/` a la racine n'est PAS exclu.

## 2. La page 500 n'affiche plus le message d'exception (etait : CRITIQUE)

`handler500` placait `str(exception)` dans le contexte, et `500.html` le rendait — or ces
handlers ne tournent QUE avec `DEBUG=0`. N'importe quel visiteur anonyme pouvait donc lire
`password authentication failed for user "tibillet"`, le nom des tables, ou une
`IntegrityError` renvoyant **l'adresse email d'un tiers** a qui provoquait le conflit. La
page etant aussi servie sur le domaine racine, elle etait exposee en permanence aux scanners.

Le detail part maintenant dans les logs (`logger.error(..., exc_info=...)`), et n'atteint le
gabarit que si `DEBUG` est actif. `500.html` prevoyait deja la branche sans exception.

**Detail d'implementation :** la lecture passe par `django.conf.settings` (importe sous
l'alias `django_settings`) et non par `TiBillet.settings`, deja importe dans le fichier :
ce dernier est le module brut, fige a l'import, qu'un `override_settings()` de test ne
toucherait pas.

## 3. `get_client_ip()` ne lit plus une valeur forgeable (etait : IMPORTANT)

La fonction lisait `x_forwarded_for.split(',')[0]` — **l'element le plus a gauche**, donc
celui que le client a envoye lui-meme. `X-Forwarded-For` s'ecrit en ajoutant a DROITE.

Elle sert d'identifiant de limitation de debit : throttle DRF de l'identification et plafond
de renvoi d'OTP (`onboard/views.py`). Un attaquant pouvait donc **contourner les deux
plafonds** en variant l'en-tete a chaque requete, et symetriquement **bloquer une victime**
une heure en remplissant le compteur associe a son adresse.

Nouvel ordre : `X-Real-IP` d'abord — nginx l'IMPOSE (`proxy_set_header X-Real-IP
$remote_addr`) et il vaut le `$remote_addr` reconstruit par `real_ip`, que le client ne
controle pas. `X-Forwarded-For` ne sert qu'en repli, et on y prend le **dernier** element.

## 4. La confiance proxy est reduite (etait : IMPORTANT, partiellement traite)

`set_real_ip_from` couvrait `172.16.0.0/12` **plus** `10.0.0.0/8` et `192.168.0.0/16`. Les
deux dernieres sont supprimees.

**Ce qui reste ouvert, sciemment :** `172.16.0.0/12` couvre tous les reseaux docker de la
machine, pas seulement celui de Traefik. Un conteneur voisin — le reseau `frontend` est
`external: true`, donc partage avec les autres stacks de l'hote — peut joindre nginx en
direct, court-circuiter Traefik et forger l'IP.

Le sous-reseau exact n'est PAS code en dur parce qu'il est attribue dynamiquement a la
creation du reseau et differe d'une machine a l'autre. **Une valeur erronee serait pire que
large** : `$remote_addr` retomberait sur l'IP de Traefik, identique pour tous les visiteurs,
et le plafond de limitation de debit les compterait comme un seul client — blocage general.
La commande pour durcir est donnee en commentaire dans le fichier. La consequence
reellement exploitable, elle, est fermee par le correctif 3.

## 5. Rotation des journaux (etait : IMPORTANT)

**Rien** ne bornait `./logs` : 258 Mo d'acces, 98 Mo d'erreurs, sans limite. Le plafond
`logging:` des autres services ne s'y applique pas (il ne couvre que la sortie standard des
conteneurs, alors que nginx et gunicorn ecrivent dans le volume monte), et le
`RotatingFileHandler` declare dans `settings.py` **n'est attache a aucun logger**.

Nouveau service `logrotate` (`blacklabelops/logrotate`, le meme que la stack Traefik) :
quotidien, **14 jours** de retention, compression. Depuis que nginx reconstruit l'adresse
reelle du visiteur, ces journaux contiennent des **donnees personnelles** : les conserver
sans limite n'etait ni utile — le diagnostic de latence se fait sur quelques jours — ni
defendable.

**`copytruncate` est vital ici**, et c'est le mode par defaut de cette image (verifie dans
`/usr/bin/logrotate.d/logrotate.sh:48`) : le fichier est vide SUR PLACE, son inode ne change
pas. nginx et gunicorn gardent leur descripteur ouvert et ne recoivent aucun signal — avec
une rotation par renommage, ils continueraient d'ecrire dans le fichier renomme et le journal
courant resterait vide indefiniment. **Ne pas definir `LOGROTATE_MODE` sans mesurer ca.**

## 6. Un slug de Page ne peut plus commencer par `wp-` (etait : MINEUR)

nginx coupe les sondes WordPress par un `return 444` **avant Django**. Une `Page` dont le
slug commencait par `wp-` etait donc injoignable en production — et de la pire facon : pas
de 404, pas de message, juste une connexion qui se ferme.

`valider_slug_non_reserve()` refuse desormais les **prefixes** (`PREFIXES_SLUGS_RESERVES`)
en plus des slugs exacts, avec un message qui explique la cause. `xmlrpc.php` et
`wlwmanifest.xml` rejoignent la liste exacte.

## 7. La page d'erreur du domaine racine n'offre plus de formulaires morts (etait : MINEUR)

Sur le schema public, les panneaux connexion et contact etaient rendus alors qu'ils postent
vers `/connexion/` et `/home/contact/`, absentes de l'URLconf public. Un
`sans_panneaux_globaux` pose par les handlers d'erreur les retire. Aucun impact securite,
mais deux formulaires qui echouaient a l'envoi.

---

## Comment tester (a la main) / Manual test

### Test 1 — l'image ne contient plus le depot git (LE test qui compte)

A faire **avant le prochain `docker push`** :
```bash
docker build -t lespass-verif-dockerignore .
docker run --rm --entrypoint sh lespass-verif-dockerignore -c \
  "du -sh /DjangoFiles/.git /DjangoFiles/www /DjangoFiles/logs 2>&1 | head"
```
Attendu : les trois chemins **absents** (`No such file or directory`).

Puis verifier que l'application demarre quand meme — c'est le risque de cette exclusion :
```bash
docker run --rm lespass-verif-dockerignore poetry run python /DjangoFiles/manage.py check
```
Attendu : `System check identified no issues`. Le `collectstatic` de `start.sh` reconstruit
`www/static` au demarrage ; si des fichiers statiques manquaient en production, c'est ici
qu'il faudrait regarder.

### Test 2 — la page 500 ne divulgue plus rien

`DEBUG=0` requis (donc pre-prod ou prod).
1. Provoquer une erreur serveur sur une vue quelconque.
2. Attendu : page d'erreur **sans** bloc `<pre><code>`, message neutre.
3. Le detail doit apparaitre dans les logs : `docker exec lespass_django grep handler500 /DjangoFiles/logs/gunicorn.logs`

### Test 3 — la limitation de debit compte la bonne IP

```bash
# Depuis l'exterieur, avec un X-Forwarded-For force : il ne doit PLUS etre pris en compte.
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code} " \
    -H "X-Forwarded-For: 1.2.3.$i" -X POST https://<tenant>/onboard/identity/
done
```
Attendu : le throttle finit par renvoyer `429` malgre l'IP variable. Avant le correctif,
chaque valeur forgee ouvrait un compteur neuf et le plafond n'etait jamais atteint.

### Test 4 — la rotation fonctionne (a verifier 24 h apres deploiement)

```bash
docker exec lespass_logrotate logrotate -d /etc/logrotate.conf 2>&1 | grep -A3 "considering"
ls -la logs/
```
Attendu : apparition de `nginxAccess.log.1` (puis `.gz`), et surtout **`nginxAccess.log`
qui continue de grossir** — c'est la preuve que `copytruncate` fonctionne et que nginx
n'ecrit pas dans un inode orphelin. Si le journal courant reste a 0 octet apres une
rotation, c'est exactement ce piege : verifier `LOGROTATE_MODE`.

### Test 5 — le slug reserve

1. Admin → Pages → creer une page, slug `wp-partenaires`.
2. Attendu : refus a l'enregistrement, avec le message expliquant que le serveur bloque ces
   adresses. Un slug `wordpress-partenaires` (sans tiret apres `wp`) doit, lui, passer.

### Test 6 — page d'erreur du domaine racine

`curl -sk https://<domaine-racine>/page-inexistante/ | grep -c "offcanvas"`
Attendu : `0`. Sur un tenant, les panneaux doivent toujours etre presents.

### Tests automatiques / Automated tests

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```
Resultat au 2026-07-21 apres ces correctifs : **926 passed** en 2 min 18 s, sans echec.
Lancer en **sequentiel** — jamais `-n`/xdist, la base de dev est partagee.

**Non couvert par la suite** : aucun test n'exerce `get_client_ip()` ni le validateur de
prefixe de slug. Deux tests seraient utiles et ne demandent pas de navigateur :
un sur l'ordre de lecture des en-tetes, un sur le refus d'un slug `wp-*`.
