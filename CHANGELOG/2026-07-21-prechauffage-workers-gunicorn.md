# Préchauffage des workers Gunicorn : la latence des pages divisée par trois / Gunicorn worker warmup: page latency cut by three

**Date :** 2026-07-21
**Migration :** Non

## Resume / Summary

**Quoi / What :** un fichier `gunicorn_conf.py` ajoute un hook `post_worker_init` qui construit
le resolveur d'URLs de Django au demarrage de chaque worker, au lieu de le laisser se
construire a la premiere requete servie.
/ A `gunicorn_conf.py` adds a `post_worker_init` hook that builds Django's URL resolver at
worker startup instead of letting it happen on the first request served.

**Pourquoi / Why :** Gunicorn fonctionne en pre-fork — chaque worker est un PROCESS distinct
avec sa propre memoire, et les caches de code de Django (resolveur d'URLs, gabarits compiles)
sont de simples dictionnaires Python qui ne traversent pas la frontiere entre process. Chaque
worker doit donc les construire pour son propre compte, et Django ne le fait qu'a la PREMIERE
requete : `ROOT_URLCONF` n'est importe qu'a ce moment-la, avec toutes les vues et tout ce
qu'elles importent.

Le visiteur qui tombait sur un worker encore froid payait ce cout. Avec 18 workers et un site
peu frequente, presque chaque visite tombait sur un worker froid.
/ Gunicorn is pre-fork: each worker is a separate process, and Django's code caches are plain
Python dicts that cannot cross a process boundary. Django only builds them on the FIRST
request, so whoever lands on a cold worker pays the cost — and with 18 workers on a
low-traffic site, nearly every visit landed on a cold one.

### Les mesures / Measurements

Decomposition du premier rendu dans un process neuf, en production :

| Poste | Cout | Part |
|---|---|---|
| **URLconf + imports des vues** | **224,6 ms** | ~72 % |
| 40 gabarits | 62,8 ms | ~20 % |
| Premiere connexion memcached | 6,3 ms | 2 % |
| Catalogues gettext | 0,1 ms | — |

Effet observe sur les pages publiques d'un tenant :

| | Avant | Apres |
|---|---|---|
| Worker chaud | ~150 ms | ~150 ms (inchange) |
| Worker froid | **500 a 650 ms** | plus de worker froid |
| Prechauffage mesure au demarrage | — | **209 a 216 ms par worker**, hors requete |

Le diagnostic a ete etabli en confrontant trois sources : `upstream_response_time` de nginx
(542 ms), le `%(M)s` de gunicorn (654 / 497 / 519 / 612 ms) et un rendu direct par le test
client de Django (87 ms une fois chaud). L'ecart entre les deux derniers, et surtout le
caractere **bimodal** des temps sur une meme URL a taille de reponse identique (210 / 614 /
144 / 612 ms), ont designe le worker et non le code.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `gunicorn_conf.py` | **NOUVEAU** — hook `post_worker_init` |
| `supervisor/conf.d/gunicorn.conf` | ajout de `-c /DjangoFiles/gunicorn_conf.py` |

### Choix de conception / Design decisions

**Les DEUX resolveurs sont prechauffes.** django-tenants en utilise un pour les lieux
(`ROOT_URLCONF`) et un autre pour le schema public (`PUBLIC_SCHEMA_URLCONF`) : ce sont deux
objets memoises separement, n'en chauffer qu'un laisserait l'autre froid.

**Seul du CODE est prechauffe, jamais des DONNEES.** Le resolveur d'URLs est commun a tous les
lieux, le prechauffage coute donc la meme chose avec 3 tenants qu'avec 500. Le hook s'execute
hors de tout contexte de tenant : **il ne faut RIEN y ajouter qui soit propre a un lieu**, une
boucle sur les tenants ne passerait pas a l'echelle.

**Les gabarits (62,8 ms) ne sont PAS prechauffes.** Un cinquieme du gain pour un code qu'il
faudrait tenir a jour a chaque nouveau skin. A reconsiderer si la mesure montre un residuel.

**Le prechauffage a lieu APRES le fork, pas avant.** `--preload` aurait paye le cout une seule
fois au lieu de 18, mais toute connexion (PostgreSQL, memcached) ouverte avant le fork serait
**partagee par les 18 workers via la meme socket** — une classe de bugs difficiles a
diagnostiquer. 18 x 0,2 s au demarrage est un prix largement acceptable pour l'eviter.

**Le rattrapage d'erreur porte sur `BaseException`, et la journalisation elle-meme est
protegee.** Ce n'est pas de la prudence excessive : gunicorn ne marque le worker « demarre »
(`self.booted = True`) qu'APRES l'appel du hook (`gunicorn/workers/base.py`). Une exception qui
s'echappe d'ici fait donc sortir le worker en `WORKER_BOOT_ERROR`, que l'arbitre traduit en
`HaltServer` : **le master s'arrete, les 18 workers avec lui**, et supervisord boucle jusqu'a
`FATAL` — plus une seule reponse servie. Un prechauffage rate doit rester sans consequence, il
faut donc tout rattraper, y compris `SystemExit`.

**La journalisation passe par `worker.log`** (le logger de gunicorn) et non par
`logging.getLogger()` : elle ne depend ni de `django.setup()` ni du dictionnaire `LOGGING` du
projet. Un logger Django ne remonterait ici que grace a `disable_existing_loggers: False`, une
condition qu'un reglage de `settings.py` pourrait retirer sans que personne ne fasse le lien.

**Nuance sur « plus de worker froid » :** `URLResolver.reverse_dict` est memoise **par langue**.
Le hook s'execute avec la langue par defaut (`fr`), donc le premier visiteur d'une autre langue
sur un worker donne repeuplera ce dictionnaire. Le gros du cout — l'import des vues — etant
deja paye, le residuel est faible. Chauffer les autres langues coute trois lignes
(`translation.override()`), a ne faire que si la mesure le justifie.

**Le nombre de workers n'est PAS modifie.** 18 est sur-dimensionne pour ce trafic (CPU mesure
a 0,52 %), mais avec le prechauffage la latence ne depend plus du nombre de workers. Un
changement a la fois, mesurable separement.

**Ne JAMAIS ajouter `--max-requests` sans ce prechauffage** : chaque recyclage de worker
refabriquerait un worker froid.

---

## Comment tester (a la main) / Manual test

### Test 1 — Gunicorn demarre (LE test qui compte, a faire AVANT tout le reste)

Le risque de ce chantier est concentre ici : ce fichier s'execute au demarrage de chaque
worker en production. Une erreur et le service ne demarre pas.

**Verification prealable, sans rien deployer** — simule ce que fait supervisord :
```bash
python3 -c "
import shlex
ligne = next(l for l in open('supervisor/conf.d/gunicorn.conf') if l.startswith('command='))[8:].strip()
apres = ligne % {'program_name':'gunicorn','here':'/DjangoFiles','process_num':'0','group_name':'gunicorn','numprocs':'1'}
m = shlex.split(apres)
print('OK -', m[m.index('-c')+1])
"
```
Attendu : le chemin du fichier de conf. Un `KeyError` signalerait un `%` non double.

**Apres deploiement :**
```bash
docker exec lespass_django supervisorctl status gunicorn
```
Attendu : `RUNNING`. Si `FATAL` ou `BACKOFF` :
```bash
docker exec lespass_django tail -40 /DjangoFiles/logs/supervisor/supervisord.log
```

### Test 2 — le prechauffage s'execute vraiment

```bash
docker exec lespass_django grep "warmup worker" /DjangoFiles/logs/gunicorn.logs | tail -20
```
Attendu : **une ligne par worker** (donc 18), du type
`INFO warmup worker 3622 : 2 URLconf en 209 ms`.

- `2 URLconf` : si la ligne affiche `1`, `PUBLIC_SCHEMA_URLCONF` a disparu des settings.
- **Aucune ligne** : le hook ne s'execute pas — verifier que `-c` est bien sur la ligne
  `command=` et que le fichier est present dans le conteneur.
- Une ligne `warmup worker ... echoue` : le prechauffage a leve. Le service tourne quand meme
  (c'est voulu), mais la latence n'est pas corrigee — lire la trace journalisee.

### Test 3 — la latence a bien baisse

```bash
docker exec lespass_django sh -c 'for i in $(seq 1 40); do
  curl -so /dev/null -w "%{time_total}\n" -H "Host: <domaine-du-tenant>" http://127.0.0.1:8002/
done' | sort -n | tail -10
```
Attendu : **aucune valeur au-dela de ~0,25 s**, des la premiere requete. Avant le
prechauffage, les premieres requetes sortaient entre 0,5 et 0,65 s et la queue lente ne
disparaissait qu'apres une centaine de passages.

Et cote log d'acces, sur du trafic reel :
```bash
awk -F'"' '$0 ~ /urt=[0-9]/ {split($NF, a, "urt="); split($2, b, " "); print a[2], b[2]}' \
  /logs/nginxAccess.log | sort -rn | head -20
```
Attendu : plus de valeurs a 0,5-0,6 s sur les pages publiques.

### Test 4 — le demarrage n'est pas rallonge de facon genante

```bash
docker exec lespass_django grep -E "Booting worker|warmup worker" /DjangoFiles/logs/gunicorn.logs | tail -40
```
Les 18 workers bootent en parallele ; le prechauffage ajoute ~0,2 s a chacun, en parallele
lui aussi. Si le demarrage complet depassait plusieurs dizaines de secondes, c'est que le
prechauffage fait plus que prevu — le relire.

### Tests automatiques / Automated tests

Aucun : il s'agit de configuration de serveur, hors du perimetre de la suite pytest. Les
verifications ci-dessus en tiennent lieu, et le test 1 doit etre joue avant chaque
deploiement qui touche a `supervisor/conf.d/gunicorn.conf`.
