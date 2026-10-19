#!/usr/bin/env bash
# Met a jour Lespass en production sans couper le site, sans 502 et sans gel.
# / Updates Lespass in production with no downtime, no 502 and no freeze.
#
# LOCALISATION : scripts/mise_a_jour_prod.sh — appele par le Makefile (make update).
# A lancer sur l'HOTE de production, dans le dossier du depot, dans byobu/tmux.
# Spec : TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md (geste 2). La release (image Docker du
# commit) doit avoir ete poussee avant : make release.
# / Run on the production HOST. The release image must have been pushed first.
#
# FLUX :
#  1. Verrou partage avec la sauvegarde (cron/saveDb.sh) : un seul make update a la fois,
#     et jamais pendant un pg_dumpall. Journal dans logs/mise_a_jour_*.log.
#  2. Pas de fenetre horaire : le verrou remplace l'ancienne fenetre de :05 a :20.
#  3. Etat de depart : les 3 services en RUNNING, arbre git propre, venv de prod conforme
#     a poetry.lock, aucun conteneur lespass_maj en cours.
#  4. git fetch. Si un fichier qui demande un geste a la main a change (dependances,
#     dockerfile, supervisor, nginx...) : arret AVANT de toucher au code servi.
#  5. docker pull de l'image latest, qui doit porter le commit cible (label).
#  6. Migration necessaire ? (fichiers */migrations/*.py changes depuis la derniere
#     migration reussie). Si oui : aucun pg_dump lance a la main en cours.
#  7. Conteneur jetable lespass_maj, lance depuis la NOUVELLE image : il controle le code
#     (manage.py check, imports wsgi/asgi, resolveurs d'URLs) puis migre. Pendant ce
#     temps, le dossier servi n'a pas bouge : l'ancien code sert, sans melange.
#  8. git merge --ff-only, puis collectstatic.
#  9. Gunicorn : remplacement des workers UN PAR UN (TTIN, attente du prechauffage,
#     TTOU). Jamais moins de N workers prets.
# 10. Test : /robots.txt doit repondre 200, ou 301/302 (redirection vers le domaine principal).
# 11. Redemarrage de daphne puis de celery (hors de :58 a :04, quand tournent les taches
#     Celery beat), controle final, menage des images.
#
# REPRISE APRES UN ECHEC : relancer make update. Deux marqueurs dans logs/ disent ou on
# en est : dernier_commit_migre (base du calcul des migrations) et dernier_commit_deploye.
# Variables : MIGRER=1 force la migration, MIGRER=0 la saute (deja faite a la main) ;
# EXECUTEUR=standard migre un lieu apres l'autre.
# / On failure, run make update again. Two marker files in logs/ track progress.
#
# CE QUE LE SCRIPT NE FAIT PAS (« grosse mise a jour », voir la spec) : dependances,
# dockerfile, conf supervisor, conf nginx, gunicorn_conf.py, docker-compose.prod.yml.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

CONTENEUR="lespass_django"
CONTENEUR_DE_MAJ="lespass_maj"
CONTENEUR_POSTGRES="lespass_postgres"
IMAGE="tibillet/lespass:latest"
COMPOSE=(docker compose -f docker-compose.prod.yml)
FICHIER_LOG_GUNICORN="logs/gunicorn.logs"
MARQUEUR_MIGRE="logs/dernier_commit_migre"
MARQUEUR_DEPLOYE="logs/dernier_commit_deploye"

# Fichiers dont un changement demande un geste a la main. Le script s'arrete avant le merge.
# - poetry.lock, pyproject.toml : dependances. Les workers remplaces un par un gardent le
#   venv du conteneur de prod : ils n'auraient pas les nouveaux paquets.
# - dockerfile : l'image change, le conteneur de prod doit etre recree.
# - supervisor/, start.sh : relus seulement au demarrage du conteneur.
# - gunicorn_conf.py : relu seulement par le maitre (HUP ou restart). Les workers ajoutes
#   par TTIN heritent de l'ANCIEN hook de prechauffage.
# - nginx_prod/ : monte FICHIER PAR FICHIER dans lespass_nginx. git remplace un fichier
#   par un nouveau (nouvel inode) : le conteneur garde l'ancien tant qu'il n'est pas recree.
# - docker-compose.prod.yml : docker compose up -d --no-deps <service>.
# / Files whose change needs a manual step. The script stops before the merge.
FICHIERS_A_GERER_A_LA_MAIN=(poetry.lock pyproject.toml dockerfile start.sh supervisor/
    gunicorn_conf.py nginx_prod/ docker-compose.prod.yml)

supervisorctl() {
    docker exec "$CONTENEUR" /usr/bin/supervisorctl -c /DjangoFiles/supervisor/supervisord.conf "$@"
}

arreter() {
    echo "" >&2
    echo "ARRET : $1" >&2
    exit 1
}

# Vrai si gunicorn, daphne ET celery sont en RUNNING.
# On lit la sortie : le code retour de `status` vaut 0 meme en STARTING ou en BACKOFF.
# / True if the three programs are RUNNING. The exit code of `status` is 0 even in BACKOFF.
tous_les_services_tournent() {
    local etat_des_services
    etat_des_services=$(supervisorctl status) || return 1
    echo "$etat_des_services"
    for programme in gunicorn daphne celery; do
        if ! echo "$etat_des_services" | grep -qE "^$programme +RUNNING"; then
            return 1
        fi
    done
}


# ---------------------------------------------------------------------------------------
# 1. Verrou et journal
# Le meme fichier que cron/saveDb.sh (/DjangoFiles/logs/mise_a_jour.lock dans le
# conteneur, le dossier est monte) : la sauvegarde attend la fin de make update, et
# make update attend la fin du pg_dumpall. Une sauvegarde pose un verrou sur toutes les
# tables : une migration lancee en meme temps echouerait sur son lock_timeout.
# flock marche entre l'hote et le conteneur : c'est le meme fichier, sur le meme noyau.
# Le verrou est tenu jusqu'a la fin du script (descripteur 9, ferme a la sortie).
# / Lock shared with cron/saveDb.sh: the backup waits for make update and vice versa.
# ---------------------------------------------------------------------------------------
exec 9>logs/mise_a_jour.lock
if ! flock -n 9; then
    echo "Verrou pris : sauvegarde (pg_dumpall) ou autre make update en cours. Attente, 30 min au plus..."
    if ! flock -w 1800 9; then
        arreter "verrou toujours pris apres 30 min (logs/mise_a_jour.lock). Rien n'a ete modifie."
    fi
fi

FICHIER_JOURNAL="logs/mise_a_jour_$(date +%F_%Hh%M).log"
exec > >(tee -a "$FICHIER_JOURNAL") 2>&1
echo "== make update — $(date '+%F %T') — journal : $FICHIER_JOURNAL"


# ---------------------------------------------------------------------------------------
# 3. Etat de depart
# / Starting state
# ---------------------------------------------------------------------------------------
echo "== Etat des services"
# En dev, supervisord ne tourne pas (conteneur en `sleep infinity`) : on s'arrete ici.
# / In dev, supervisord is not running: we stop here.
if ! tous_les_services_tournent; then
    arreter "supervisord ne tourne pas, ou un service n'est pas en RUNNING."
fi

# Une modification locale sur le serveur bloquerait le merge, ou serait ecrasee.
# Les fichiers non suivis (database/, backup/, logs/...) ne comptent pas.
# / A local change on the server would block the merge. Untracked files do not count.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short --untracked-files=no
    arreter "le depot du serveur a des modifications locales."
fi

# Le controle du nouveau code se fait dans l'image, avec SES dependances. Il ne vaut pour
# les workers de prod que si leur venv est conforme au poetry.lock de HEAD (l'etape 4
# verifie ensuite que ce poetry.lock est celui de la cible). start.sh le realigne a chaque
# demarrage du conteneur ; ici, on le verifie.
# / The new code is checked inside the image; it only holds for the prod workers if
# their venv matches HEAD's poetry.lock.
echo "== Venv de prod"
sortie_du_dry_run=$(docker exec -w /DjangoFiles "$CONTENEUR" poetry install --dry-run 2>&1)
if ! echo "$sortie_du_dry_run" | grep -qE "Package operations: 0 installs, 0 updates, 0 removals|No dependencies to install or update"; then
    echo "$sortie_du_dry_run" | grep -v "Skipped for the following reason" | head -20
    arreter "le venv du conteneur de prod ne correspond pas a poetry.lock : grosse mise a jour."
fi

# Un lespass_maj qui tourne : une migration est en cours (le script precedent a pu mourir,
# le conteneur continue seul). Un lespass_maj arrete : reste d'un echec, on garde sa fin
# dans le journal puis on le supprime.
# / A running lespass_maj means a migration is in progress. A stopped one is a leftover.
etat_du_conteneur_de_maj=$(docker inspect -f '{{.State.Status}}' "$CONTENEUR_DE_MAJ" 2>/dev/null || true)
if [ "$etat_du_conteneur_de_maj" = "running" ]; then
    arreter "$CONTENEUR_DE_MAJ tourne encore (migration en cours) : suivre docker logs -f $CONTENEUR_DE_MAJ."
fi
if [ -n "$etat_du_conteneur_de_maj" ]; then
    echo "== Reste d'un $CONTENEUR_DE_MAJ precedent ($etat_du_conteneur_de_maj), fin de sa sortie :"
    docker logs --tail 30 "$CONTENEUR_DE_MAJ"
    docker rm "$CONTENEUR_DE_MAJ" >/dev/null
fi


# ---------------------------------------------------------------------------------------
# 4. Recuperation du code, SANS toucher au dossier servi
# / Fetch the code WITHOUT touching the served folder
# ---------------------------------------------------------------------------------------
echo "== git fetch"
git fetch
if ! branche_suivie=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
    arreter "la branche courante ne suit aucune branche distante (git branch -u)."
fi
commit_actuel=$(git rev-parse HEAD)
commit_cible=$(git rev-parse '@{u}')
dernier_commit_deploye=$(cat "$MARQUEUR_DEPLOYE" 2>/dev/null || true)

if [ "$commit_actuel" = "$commit_cible" ] && [ "$dernier_commit_deploye" = "$commit_cible" ]; then
    echo "Deja a jour ($branche_suivie, ${commit_cible:0:12}). Rien a faire."
    exit 0
fi
echo "Mise a jour vers $branche_suivie : ${commit_actuel:0:12} -> ${commit_cible:0:12}"

fichiers_a_gerer_qui_changent=$(git diff --name-only "$commit_actuel" "$commit_cible" -- "${FICHIERS_A_GERER_A_LA_MAIN[@]}")
if [ -n "$fichiers_a_gerer_qui_changent" ]; then
    echo "$fichiers_a_gerer_qui_changent"
    arreter "ces fichiers demandent une grosse mise a jour (TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md). Rien n'a ete modifie."
fi


# ---------------------------------------------------------------------------------------
# 5. L'image de la release. Le pull n'a aucun effet sur la prod ; il peut prendre
# plusieurs minutes si la couche du venv a change. Le label pose par make release dit de
# quel commit vient l'image.
# / 5. The release image. Its label tells which commit it was built from.
# ---------------------------------------------------------------------------------------
echo "== docker pull $IMAGE"
docker pull "$IMAGE"
commit_de_l_image=$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$IMAGE")
if [ "$commit_de_l_image" != "$commit_cible" ]; then
    arreter "$IMAGE vient du commit « $commit_de_l_image », pas de ${commit_cible:0:12} : lancer make release sur la machine du mainteneur."
fi


# ---------------------------------------------------------------------------------------
# 6. Faut-il migrer ?
# On compare au dernier commit MIGRE avec succes, pas a HEAD : apres une migration qui a
# echoue, la relance migre encore. Un migrate_schemas sans rien a faire coute ~15 min.
# Angle mort : les migrations d'une app tierce (montee de dependance) ne se voient pas
# ici. Ce cas passe par la grosse mise a jour, puis MIGRER=1 make update.
# / Compare with the last SUCCESSFULLY migrated commit, not HEAD.
# ---------------------------------------------------------------------------------------
faut_il_migrer="non"
dernier_commit_migre=$(cat "$MARQUEUR_MIGRE" 2>/dev/null || true)
if [ "${MIGRER:-}" = "1" ]; then
    faut_il_migrer="oui"
elif [ "${MIGRER:-}" = "0" ]; then
    faut_il_migrer="non"
elif [ -z "$dernier_commit_migre" ]; then
    echo "Pas de marqueur $MARQUEUR_MIGRE (premier lancement) : on migre."
    faut_il_migrer="oui"
elif [ -n "$(git diff --name-only "$dernier_commit_migre" "$commit_cible" -- '*/migrations/*.py')" ]; then
    git diff --name-only "$dernier_commit_migre" "$commit_cible" -- '*/migrations/*.py'
    faut_il_migrer="oui"
fi
echo "Migration : $faut_il_migrer"

if [ "$faut_il_migrer" = "oui" ]; then
    # La sauvegarde du cron est tenue a l'ecart par le verrou. Reste un pg_dump lance a la
    # main, hors de saveDb.sh. pg_dumpall s'annonce
    # « pg_dumpall », et chacun de ses pg_dump « pg_dump » : d'ou le LIKE.
    # / A running backup: pg_dumpall and its pg_dump children, hence LIKE.
    requete_sauvegarde_en_cours="SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE 'pg_dump%'"
    nombre_de_sauvegardes=$(docker exec -e REQUETE="$requete_sauvegarde_en_cours" "$CONTENEUR_POSTGRES" \
        sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$REQUETE"')
    if [ "$nombre_de_sauvegardes" != "0" ]; then
        arreter "une sauvegarde (pg_dump) est en cours. Rien n'a ete modifie."
    fi
fi


# ---------------------------------------------------------------------------------------
# 7. Conteneur jetable lespass_maj : controle du nouveau code, puis migration.
#
# Il tourne depuis l'image du commit cible, sans volume : son code et ses dependances sont
# ceux de la nouvelle version, et le dossier servi par lespass_django n'a pas bouge.
#
# Le CONTROLE doit passer avant que le code arrive dans le dossier servi : un worker
# gunicorn qui ne demarre pas (code 3 ou 4) fait s'arreter le maitre ET tous les autres
# workers, donc tout le site. Il reprend ce que fait un worker : django.setup(),
# middlewares (TiBillet.wsgi), daphne (TiBillet.asgi), et les deux resolveurs du
# prechauffage. `check` ajoute les system checks (ex. admin.E039).
#
# La MIGRATION :
# - nice / ionice : priorite CPU et disque minimale pour les process Python. Le travail
#   fait par PostgreSQL n'est pas concerne.
# - PGOPTIONS lock_timeout : un ALTER TABLE qui attend un verrou bloque toutes les
#   requetes du site sur cette table. Au bout de 5 s, il abandonne : la migration EN COURS
#   de ce schema est annulee (les precedentes restent appliquees), les autres schemas
#   continuent, et la commande finit en erreur. Relancer make update reprend la ou on en est.
# - executor multiprocessing : quelques minutes au lieu de plusieurs heures pour 500 lieux.
#   Si une migration ajoute une cle etrangere vers une table publique : EXECUTEUR=standard
#   (interblocage vu deux fois dans ce cas).
#
# Lance DETACHE (-d) : un `docker compose run` attache relaie tous les signaux au
# conteneur, un Ctrl-C ou une coupure SSH interromprait la migration au milieu d'un
# schema. Detache, il finit seul si le script meurt (l'etape 3 le retrouve a la relance).
# Sans --rm : sa sortie reste lisible jusqu'au `docker rm`.
# --name est OBLIGATOIRE : `docker compose run` ignore le container_name du compose et
# invente un nom aleatoire. Le nom fixe sert a le suivre, a le retrouver a la relance, et
# empeche d'en lancer deux (« name already in use »).
# PYTHONUNBUFFERED : sans terminal, Python garde sa sortie en memoire par paquets ; la
# migration paraitrait muette pendant 15 min.
# / Throwaway lespass_maj container: checks the new code, then migrates. Detached, so a
# Ctrl-C or a lost SSH session cannot interrupt the migration.
# ---------------------------------------------------------------------------------------
read -r -d '' COMMANDES_DU_CONTENEUR_DE_MAJ <<'FIN_DES_COMMANDES' || true
set -euo pipefail
cd /DjangoFiles
echo "== Controle du code cible"
poetry run python manage.py check
poetry run python -c "
import TiBillet.wsgi, TiBillet.asgi
from django.conf import settings
from django.urls import get_resolver
get_resolver(settings.ROOT_URLCONF)._populate()
get_resolver(settings.PUBLIC_SCHEMA_URLCONF)._populate()
print('Code cible : wsgi, asgi et URLconf OK')
"
if [ "$FAUT_IL_MIGRER" = "oui" ]; then
    echo "== migrate_schemas --executor=$EXECUTEUR (l'ancien code continue de servir)"
    nice -n 19 ionice -c3 poetry run python manage.py migrate_schemas --executor="$EXECUTEUR"
fi
FIN_DES_COMMANDES

# Un pseudo-terminal dans le conteneur, seulement si on en a un (byobu) : sans lui,
# Django retire les couleurs ET le prefixe de django-tenants
# « [12/500 (2%) multiprocessing:<lieu>] » (OutputWrapper.style_func, isatty()).
# Sous `at` (make update_nuit), --tty ferait echouer le run : « cannot attach stdin to a
# TTY-enabled container because stdin is not a terminal ». Le journal garde alors les codes
# de couleur : le lire avec less -R.
# / A pseudo-TTY only when we have one: without it Django drops colours and the
# django-tenants prefix. Under `at`, --tty would make the run fail.
option_terminal=()
if [ -t 0 ]; then
    option_terminal=(--tty)
fi

echo "== Conteneur $CONTENEUR_DE_MAJ"
"${COMPOSE[@]}" run -d "${option_terminal[@]}" --no-deps --name "$CONTENEUR_DE_MAJ" \
    -e PYTHONUNBUFFERED=1 \
    -e FAUT_IL_MIGRER="$faut_il_migrer" \
    -e EXECUTEUR="${EXECUTEUR:-multiprocessing}" \
    -e PGOPTIONS="-c lock_timeout=5s" \
    "$CONTENEUR_DE_MAJ" bash -c "$COMMANDES_DU_CONTENEUR_DE_MAJ" >/dev/null

# `docker logs -f` rend la main quand le conteneur s'arrete.
# / `docker logs -f` returns when the container stops.
docker logs -f "$CONTENEUR_DE_MAJ"
code_de_sortie_du_conteneur_de_maj=$(docker wait "$CONTENEUR_DE_MAJ")
docker rm "$CONTENEUR_DE_MAJ" >/dev/null

if [ "$code_de_sortie_du_conteneur_de_maj" != "0" ]; then
    echo "" >&2
    echo "Lignes utiles du journal :" >&2
    grep -inE "lock timeout|deadlock" "$FICHIER_JOURNAL" | tail -20 >&2 || true
    arreter "$CONTENEUR_DE_MAJ a echoue (code $code_de_sortie_du_conteneur_de_maj). Le code servi n'a pas change. Corriger, puis relancer make update."
fi
# MIGRER=0 veut dire « la base est deja au niveau de la cible » (migration faite a la
# main, ou rien a migrer) : le marqueur est pose aussi, sinon la prochaine mise a jour
# croirait a un premier lancement et migrerait pour rien.
# / MIGRER=0 means the database is already at the target level: set the marker too.
if [ "$faut_il_migrer" = "oui" ] || [ "${MIGRER:-}" = "0" ]; then
    echo "$commit_cible" > "$MARQUEUR_MIGRE"
fi


# ---------------------------------------------------------------------------------------
# 8. Le code arrive dans le dossier servi
# A partir d'ici, les anciens workers lisent les NOUVEAUX gabarits (pas de cached.Loader) :
# les etapes 8 et 9 s'enchainent sans attendre.
# / From here on, old workers read the NEW templates: steps 8 and 9 run back to back.
# ---------------------------------------------------------------------------------------
echo "== git merge --ff-only"
git merge --ff-only "$commit_cible"

echo "== collectstatic"
docker exec -w /DjangoFiles "$CONTENEUR" poetry run python manage.py collectstatic --no-input


# ---------------------------------------------------------------------------------------
# 9. Gunicorn : remplacement des workers un par un
# Sans --preload, chaque nouveau worker charge le code depuis le disque : le nouveau.
# TTIN ajoute un worker. TTOU en retire un : toujours le PLUS VIEUX, en douceur (il finit
# sa requete en cours). On ne retire un ancien qu'une fois le nouveau pret : sa ligne
# « warmup worker <pid> : » est ecrite par gunicorn_conf.py juste avant qu'il accepte des
# requetes. HUP ne convient pas : il arrete les anciens AVANT que les nouveaux soient prets.
# On boucle sur les PID des anciens, pas sur un nombre de tours : un worker relance par
# timeout pendant la boucle fausserait le compte et laisserait un ancien en vie.
# / Replace gunicorn workers one by one: TTIN, wait for warmup, TTOU (kills the oldest).
# ---------------------------------------------------------------------------------------
echo "== Gunicorn : remplacement des workers un par un"
pid_du_maitre=$(supervisorctl pid gunicorn)
pid_des_anciens_workers=$(docker exec "$CONTENEUR" pgrep -P "$pid_du_maitre" || true)
nombre_d_anciens_workers=$(echo "$pid_des_anciens_workers" | wc -w)
echo "Maitre $pid_du_maitre, $nombre_d_anciens_workers workers a remplacer"
# Sans ce garde-fou, la boucle serait sautee et les anciens workers serviraient l'ancien
# code, avec un « Mise a jour terminee » a la fin.
# / Without this guard, the loop would be skipped and old workers would keep serving.
if [ "$nombre_d_anciens_workers" -eq 0 ]; then
    arreter "aucun worker gunicorn trouve sous le PID $pid_du_maitre."
fi

# Si le script s'arrete entre un TTIN et son TTOU, gunicorn garderait un worker de trop.
# / If the script stops between a TTIN and its TTOU, give the extra worker back.
un_ttin_attend_son_ttou="non"
rendre_le_worker_en_trop() {
    if [ "$un_ttin_attend_son_ttou" = "oui" ]; then
        supervisorctl signal TTOU gunicorn || true
    fi
}
trap rendre_le_worker_en_trop EXIT

compter_les_anciens_encore_vivants() {
    local workers_actuels
    local nombre_vivants=0
    workers_actuels=$(docker exec "$CONTENEUR" pgrep -P "$pid_du_maitre" || true)
    for pid_ancien in $pid_des_anciens_workers; do
        if echo "$workers_actuels" | grep -qx "$pid_ancien"; then
            nombre_vivants=$((nombre_vivants + 1))
        fi
    done
    echo "$nombre_vivants"
}

nombre_de_tours=0
anciens_encore_vivants=$(compter_les_anciens_encore_vivants)
while [ "$anciens_encore_vivants" -gt 0 ]; do
    nombre_de_tours=$((nombre_de_tours + 1))
    if [ "$nombre_de_tours" -gt $((2 * nombre_d_anciens_workers)) ]; then
        arreter "trop de tours ($nombre_de_tours) : $anciens_encore_vivants ancien(s) worker(s) encore en vie."
    fi
    if [ "$(supervisorctl pid gunicorn)" != "$pid_du_maitre" ]; then
        arreter "gunicorn a redemarre pendant la mise a jour : regarder $FICHIER_LOG_GUNICORN."
    fi

    # a. Ajouter un worker, et attendre qu'il soit pret (90 s au plus).
    # / a. Add a worker and wait until it is ready.
    taille_du_log_avant=$(stat -c %s "$FICHIER_LOG_GUNICORN")
    supervisorctl signal TTIN gunicorn >/dev/null
    un_ttin_attend_son_ttou="oui"

    nouveau_worker_pret="non"
    for seconde in $(seq 1 90); do
        lignes_ecrites_depuis=$(tail -c +"$((taille_du_log_avant + 1))" "$FICHIER_LOG_GUNICORN")
        # La ligne d'echec du prechauffage commence aussi par « warmup worker » : on la
        # teste en premier. Un worker qui l'ecrit tourne, mais ses requetes vont echouer.
        # / The warmup failure line also starts with "warmup worker": test it first.
        if echo "$lignes_ecrites_depuis" | grep -qE "warmup worker [0-9]+ echoue|Worker failed to boot|App failed to load|Shutting down: Master"; then
            echo "$lignes_ecrites_depuis" | tail -20
            # Pas de TTOU de rattrapage ici : il retirerait le PLUS VIEUX worker, donc un
            # ancien qui marche, et garderait le nouveau qui echoue.
            # / No catch-up TTOU: it would remove a healthy old worker, not the broken one.
            un_ttin_attend_son_ttou="non"
            arreter "le nouveau worker gunicorn ne demarre pas correctement. Les anciens workers servent toujours, avec un worker neuf en trop. Ancien commit : $commit_actuel (spec, « Revenir en arriere »)."
        fi
        if echo "$lignes_ecrites_depuis" | grep -qE "warmup worker [0-9]+ : "; then
            nouveau_worker_pret="oui"
            break
        fi
        sleep 1
    done
    if [ "$nouveau_worker_pret" != "oui" ]; then
        un_ttin_attend_son_ttou="non"
        arreter "pas de ligne « warmup worker » en 90 s dans $FICHIER_LOG_GUNICORN (--log-level doit rester info)."
    fi

    # b. Retirer le plus vieux worker, et attendre qu'il soit parti (40 s au plus : il finit
    # sa requete en cours ; au-dela de 30 s, gunicorn l'abat de lui-meme).
    # / b. Remove the oldest worker and wait until it is gone.
    supervisorctl signal TTOU gunicorn >/dev/null
    un_ttin_attend_son_ttou="non"
    for seconde in $(seq 1 40); do
        if [ "$(compter_les_anciens_encore_vivants)" -lt "$anciens_encore_vivants" ]; then
            break
        fi
        sleep 1
    done
    anciens_encore_vivants=$(compter_les_anciens_encore_vivants)
    echo "Tour $nombre_de_tours : encore $anciens_encore_vivants ancien(s) worker(s)"
done
trap - EXIT


# ---------------------------------------------------------------------------------------
# 10. Test : le site repond. Plusieurs appels : chacun tombe sur un worker au hasard.
# X-Forwarded-Proto : nginx le pose en vrai ; sans lui, Django se croit en HTTP.
# 200 ou 301/302 : sur $DOMAIN (le tenant public), CanonicalDomainRedirectMiddleware
# redirige vers le domaine principal du tenant quand ce n'est pas $DOMAIN. Une
# redirection prouve aussi que le worker a demarre et repond (Django, tenant, middlewares).
# Un worker en panne donne 500, 502 ou 000 (pas de reponse).
# / Smoke test: 200 or a canonical-domain redirect; a broken worker gives 5xx or 000.
# ---------------------------------------------------------------------------------------
echo "== Test de /robots.txt"
for essai in 1 2 3 4 5; do
    reponse=$(docker exec "$CONTENEUR" bash -c \
        'curl -s -o /dev/null -w "%{http_code} %{redirect_url}" -H "Host: $DOMAIN" -H "X-Forwarded-Proto: https" http://127.0.0.1:8002/robots.txt')
    code_http=${reponse%% *}
    case "$code_http" in
        200|301|302) ;;
        *) arreter "/robots.txt repond $code_http. Les workers servent le nouveau code : regarder $FICHIER_LOG_GUNICORN." ;;
    esac
done
echo "/robots.txt : $reponse"


# ---------------------------------------------------------------------------------------
# 11. daphne et celery, controle final, menage
# Celery recoit TERM : il finit ses taches en cours avant de s'arreter.
# Supervisor annonce RUNNING au bout d'une seconde (startsecs) alors que Django met
# plusieurs secondes a demarrer : on attend avant le controle final.
# / daphne and celery, then a final check after Django had time to boot.
# ---------------------------------------------------------------------------------------
echo "== Redemarrage de daphne"
supervisorctl restart daphne
# Les taches Celery beat partent toutes a :00 (clotures comptables chaque heure, et
# d'autres a 03:00, 05:00, 08:00, toutes les 4 h) : un restart a ce moment couperait une
# tache en cours au bout de stopwaitsecs (10 s). On attend :05.
# « 10# » force la base 10 : sans lui, bash lit « 08 » et « 09 » comme de l'octal invalide.
# / Celery beat tasks all start at :00: wait until :05 before restarting celery.
minute_actuelle=$((10#$(date +%M)))
if [ "$minute_actuelle" -ge 58 ] || [ "$minute_actuelle" -le 4 ]; then
    echo "Il est $(date +%H:%M) : taches Celery beat de :00. Attente de :05 avant de redemarrer celery..."
    while [ "$minute_actuelle" -ge 58 ] || [ "$minute_actuelle" -le 4 ]; do
        sleep 20
        minute_actuelle=$((10#$(date +%M)))
    done
fi
echo "== Redemarrage de celery"
supervisorctl restart celery

sleep 15
echo "== Etat final des services"
if ! tous_les_services_tournent; then
    arreter "un service n'est pas en RUNNING apres la mise a jour."
fi

echo "$commit_cible" > "$MARQUEUR_DEPLOYE"

# Le pull a detague l'ancienne latest. `image prune` retire les images sans tag que plus
# aucun conteneur n'utilise : celle du conteneur de prod reste, tant qu'il n'est pas recree.
# Le filtre limite le menage aux images de release (label pose par make release) :
# les autres piles de l'hote ne sont pas touchees.
# / Prune untagged release images only; the prod container's image stays.
echo "== Menage des anciennes images de release"
docker image prune -f --filter "label=org.opencontainers.image.revision"

echo "Mise a jour terminee : ${commit_cible:0:12}."
