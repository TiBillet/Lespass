# Dev43

Le module `booking/` suit le processus Dev43. Avant tout travail dans
`booking/`, charger la skill `dev43:core` et la suivre.

Ce fichier est lu par un lien symbolique local, ignoré par git, à la
racine du dépôt : `ln -s booking/DEV43.md CLAUDE.md`.

## Langue

- Les documents Dev43 de `booking/` et les échanges avec l'humain sont
  en français.
- Les noms de fichiers restent en anglais, comme le code source.

## Tableaux

Par exception à la règle de Dev43 qui les interdit, la spécification
peut contenir un tableau s'il est petit et contient surtout des chiffres.

## Périmètre : le module booking seul

Dev43 ne régit que le module `booking/` de ce dépôt, partagé avec
d'autres développeurs qui n'utilisent pas Dev43. Ces règles adaptent les
skills Dev43 et l'emportent sur elles quand elles diffèrent.

- Chemins : tout chemin `spec/` des skills Dev43 désigne
  `booking/spec/` (`booking/spec/main/`, `booking/spec/changes/`,
  `booking/spec/BACKLOG.md`), y compris dans les commandes git qu'elles
  donnent, par exemple `git diff <base> -- booking/spec/` et
  `git log -p -- booking/spec`. De même, le `README.md` du projet
  désigne `booking/README.md`.
- Le logiciel que décrit `booking/spec/main/` est le module `booking`.
  Les autres apps (par exemple `BaseBillet`, `AuthBillet`) sont son
  environnement : on ne spécifie que ce que `booking` en utilise, jamais
  leur propre comportement.
- Un incrément sur `booking` peut modifier des fichiers partagés hors
  de `booking/` (par exemple migrations, configuration de l'admin,
  réglages, URL, gabarits). Ils font partie de l'incrément, et l'humain
  les indexe avec le reste au commit de sortie (`git add -A`).
- Le travail sans rapport avec `booking` est hors du processus : la
  Pause ne le contraint pas.
- Git : d'autres développeurs committent sur la même branche, donc les
  commits entre `<base>` et `HEAD` ne sont pas forcément les nôtres.
  Pour lire l'historique d'un incrément, ne garder que ses propres
  commits, par exemple
  `git log -p --reverse --grep='^Dev43-Next: ' <first>^..HEAD`.
- Commits : conformément à `GUIDELINES.md`, l'agent ne lance aucune
  opération git qui modifie le dépôt ; il garde les commandes de lecture
  (`git log`, `git diff`, `git status`). Là où Dev43 prévoit un commit,
  il écrit le message complet, trailers compris, dans `.git/SQUASH_MSG`,
  s'arrête et attend que l'humain ait commité. Il relit ensuite l'état
  avec `git log`, puis continue. Les autres commandes que Dev43 lui
  demande, par exemple le `git revert` d'un abandon, il les donne à
  l'humain.

## Lancer les tests

Référence : `tests/README.md`, et `tests/PIEGES.md` pour les pièges.

- `make test` et `make e2e` lancent pytest dans le conteneur, jamais sur
  l'hôte. `make help` donne les autres formes (un fichier, une famille).
- Pour la suite complète, `make e2e` passe avant `make test` : les
  ventes des E2E faussent des comptages de pytest.
- L'agent démarre lui-même le serveur et `stripe listen` s'ils manquent,
  depuis la racine du dépôt.

Serveur, exigé par les deux suites. Contrôle : `200` est prêt, `502` ou
pas de réponse veut dire arrêté.

```bash
curl -sk -o /dev/null -w "%{http_code}\n" https://lespass.tibillet.localhost/
docker exec -d lespass_django bash -c 'poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002 > /DjangoFiles/runserver.log 2>&1'
tail -f runserver.log
docker exec lespass_django pkill -f 'manage.py runserver'
```

`stripe listen`, exigé par `make e2e`. Contrôle, démarrage, logs, arrêt :

```bash
pgrep -af '[s]tripe listen.*/api/webhook_stripe/'
STRIPE_API_KEY=$(grep '^STRIPE_KEY_TEST=' .env | cut -d= -f2- | tr -d "'\"") setsid nohup stripe listen --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,invoice.paid,transfer.created --forward-to https://tibillet.localhost/api/webhook_stripe/ --skip-verify > stripe_listen.log 2>&1 < /dev/null &
tail -f stripe_listen.log
pkill -f '[s]tripe listen.*/api/webhook_stripe/'
```

- `[s]tripe` évite que `pgrep` et `pkill` visent le shell qui les lance.
  Ne pas enchaîner l'arrêt et le démarrage dans un même appel : le shell
  contiendrait alors le motif et serait tué.
- Un seul `stripe listen`, vers Lespass, suffit, malgré les en-têtes de
  certains tests qui en demandent un second vers Fedow.
- `stripe login` est inutile avec la clé de `.env`, et le secret
  `whsec_…` affiché peut être ignoré. Si un test à webhook échoue sans
  raison claire, essayer `--all-snapshot` à la place de `--events …`.

Chromium, exigé par `make e2e`. Il disparaît à chaque recréation du
conteneur, `down -v` compris, et son absence donne `Executable doesn't
exist` sur presque tous les E2E :

```bash
VENV=$(docker exec lespass_django poetry env info -p)
docker exec -u root lespass_django "$VENV/bin/playwright" install-deps chromium
docker exec lespass_django poetry run playwright install chromium
```

### Repartir d'une base neuve

Ces commandes effacent les bases Lespass et Fedow et le cache : jamais
sans l'accord de l'humain. Si Claude Code refuse `down -v` à l'agent,
l'humain le lance lui-même. Celery reste arrêté pendant le flush, sinon
il entre en course avec `install` (`duplicate key …
BaseBillet_configuration_pkey`).

```bash
docker compose down -v
docker compose up -d
docker compose stop lespass_celery
docker exec lespass_django bash -c 'until pg_isready -q -h postgres; do sleep 1; done'
docker exec lespass_django ./flush.sh --no-runserver
docker compose start lespass_celery
```

- La sortie doit contenir `Smoke caisse OK`, avec la carte `A49E8E2A`.
- Ensuite, réinstaller Chromium et démarrer le serveur.
- `flush.sh` seul ne suffit pas : il ne remet à zéro ni Fedow
  (`already registered`) ni le cache, et un serveur encore connecté fait
  échouer son `dropdb`.
- Le faire après une mise à jour du dépôt qui touche les migrations, ou
  après un changement de `DEMO_TAGID_*` dans `.env`.
- Une erreur `column … does not exist` sur un schéma `test_*` demande
  seulement de purger ces schémas : voir
  `TECH_DOC/SKILLS/tibillet-test/SKILL.md`, §3.
