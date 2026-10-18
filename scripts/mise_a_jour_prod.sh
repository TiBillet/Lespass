#!/usr/bin/env bash
# Met a jour Lespass en production sans couper le site, sans 502 et sans gel.
# / Updates Lespass in production with no downtime, no 502 and no freeze.
#
# LOCALISATION : scripts/mise_a_jour_prod.sh — appele par le Makefile (make update).
# A lancer sur l'HOTE de production, dans le dossier du depot, dans byobu/tmux.
# / Run on the production HOST, in the repository folder, inside byobu/tmux.
#
# Spec : TECH_DOC/SESSIONS/TODO/DEPLOIEMENT-mise-a-jour-sans-coupure.md
#
# FLUX :
#  1. Verrou (un seul make update a la fois) et journal dans logs/mise_a_jour_*.log.
#  2. Fenetre horaire : depart de :05 a :20 ou de :35 a :50 (crons a :00 et :30).
#  3. Etat de depart : les 3 services en RUNNING, memoire disponible, arbre git propre,
#     aucune migration deja en cours dans le conteneur.
#  4. git fetch. Si un fichier qui demande un geste a la main a change (dependances,
#     dockerfile, supervisor, nginx...) : arret AVANT de toucher au code servi.
#  5. Migration necessaire ? (fichiers */migrations/*.py changes depuis la derniere
#     migration reussie). Si oui : fenetre plus stricte, et aucune sauvegarde en cours.
#  6. Copie du code cible dans logs/code_cible (git archive). On CONTROLE ce code
#     (manage.py check, imports wsgi/asgi, resolveurs d'URLs) et on MIGRE depuis cette
#     copie. Pendant ce temps, le dossier servi n'a pas bouge : les workers en place
#     servent l'ancien code ET les anciens gabarits, sans melange.
#  7. git merge --ff-only, puis collectstatic.
#  8. Gunicorn : remplacement des workers UN PAR UN (TTIN, attente du prechauffage,
#     TTOU). Jamais moins de N workers prets, jamais plus de N+1 en memoire.
#  9. Test : /robots.txt doit repondre 200.
# 10. Redemarrage de daphne puis de celery, et controle final : tout en RUNNING.
#
# REPRISE APRES UN ECHEC : relancer make update. Deux marqueurs dans logs/ disent ou on
# en est : dernier_commit_migre (base du calcul des migrations) et dernier_commit_deploye.
# Variables : MIGRER=1 force la migration, MIGRER=0 la saute (deja faite a la main).
# / On failure, run make update again. Two marker files in logs/ track progress.
#
# CE QUE LE SCRIPT NE FAIT PAS (gestes a la main, voir la spec) : dependances,
# dockerfile, conf supervisor, conf nginx, gunicorn_conf.py, docker-compose.prod.yml.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

CONTENEUR="lespass_django"
CONTENEUR_POSTGRES="lespass_postgres"
FICHIER_LOG_GUNICORN="logs/gunicorn.logs"
DOSSIER_CODE_CIBLE="logs/code_cible"
MARQUEUR_MIGRE="logs/dernier_commit_migre"
MARQUEUR_DEPLOYE="logs/dernier_commit_deploye"
MEMOIRE_DISPONIBLE_MINIMUM_EN_MO=600

# Fichiers dont un changement demande un geste a la main. Le script s'arrete avant le merge.
# - poetry.lock, pyproject.toml : dependances (docker restart, start.sh refait poetry install).
# - dockerfile : reconstruction de l'image.
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
# / Lock and log
# ---------------------------------------------------------------------------------------
exec 9>logs/mise_a_jour.lock
if ! flock -n 9; then
    arreter "un autre make update tourne deja."
fi

FICHIER_JOURNAL="logs/mise_a_jour_$(date +%F_%Hh%M).log"
exec > >(tee -a "$FICHIER_JOURNAL") 2>&1
echo "== make update — $(date '+%F %T') — journal : $FICHIER_JOURNAL"


# ---------------------------------------------------------------------------------------
# 2. Fenetre horaire. Les crons tournent a :00 et :30 (sauvegarde pg_dumpall, taches
# Celery beat). La sauvegarde pose un verrou sur toutes les tables : une migration lancee en
# meme temps echouerait sur son lock_timeout.
# « 10# » force la base 10 : sans lui, bash lit « 08 » et « 09 » comme de l'octal invalide.
# / Time window: stay away from the :00 and :30 crons.
# ---------------------------------------------------------------------------------------
minute_actuelle=$((10#$(date +%M)))
if ! { [ "$minute_actuelle" -ge 5 ] && [ "$minute_actuelle" -le 20 ]; } \
    && ! { [ "$minute_actuelle" -ge 35 ] && [ "$minute_actuelle" -le 50 ]; }; then
    arreter "il est $(date +%H:%M), trop pres d'un cron. make update se lance de :05 a :20 ou de :35 a :50."
fi


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

# Le remplacement des workers en ajoute un avant d'en retirer un : il faut sa place en memoire.
# / Worker replacement adds one before removing one: it needs room in memory.
memoire_disponible_en_mo=$(( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) / 1024 ))
if [ "$memoire_disponible_en_mo" -lt "$MEMOIRE_DISPONIBLE_MINIMUM_EN_MO" ]; then
    arreter "seulement $memoire_disponible_en_mo Mo de memoire disponible (minimum $MEMOIRE_DISPONIBLE_MINIMUM_EN_MO)."
fi

# Une modification locale sur le serveur bloquerait le merge, ou serait ecrasee.
# Les fichiers non suivis (database/, backup/, logs/...) ne comptent pas.
# / A local change on the server would block the merge. Untracked files do not count.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short --untracked-files=no
    arreter "le depot du serveur a des modifications locales."
fi

# `docker exec` sans terminal : un Ctrl-C ou une coupure SSH tue le script, PAS la
# migration, qui continue dans le conteneur. On n'en lance pas une seconde par-dessus.
# / Without a TTY, a lost SSH session kills the script, not the migration.
if docker exec "$CONTENEUR" pgrep -f migrate_schemas >/dev/null; then
    arreter "une migration tourne deja dans le conteneur. Attendre qu'elle finisse."
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
    echo "Deja a jour ($branche_suivie, ${commit_cible:0:8}). Rien a faire."
    exit 0
fi
echo "Mise a jour vers $branche_suivie : ${commit_actuel:0:8} -> ${commit_cible:0:8}"

fichiers_a_gerer_qui_changent=$(git diff --name-only "$commit_actuel" "$commit_cible" -- "${FICHIERS_A_GERER_A_LA_MAIN[@]}")
if [ -n "$fichiers_a_gerer_qui_changent" ]; then
    echo "$fichiers_a_gerer_qui_changent"
    arreter "ces fichiers demandent un geste a la main (voir la spec DEPLOIEMENT-mise-a-jour-sans-coupure.md). Rien n'a ete modifie."
fi


# ---------------------------------------------------------------------------------------
# 5. Faut-il migrer ?
# On compare au dernier commit MIGRE avec succes, pas a HEAD : apres une migration qui a
# echoue, la relance migre encore. Un migrate_schemas sans rien a faire coute ~15 min.
# Angle mort : les migrations d'une app tierce (montee de dependance) ne se voient pas
# ici. Ce cas passe par le geste a la main de poetry.lock, puis MIGRER=1 make update.
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
    # La migration dure jusqu'a 15 min : partie apres :10, elle deborderait sur le cron suivant.
    # / Migration takes up to 15 min: started after :10, it would overlap the next cron.
    if ! { [ "$minute_actuelle" -ge 5 ] && [ "$minute_actuelle" -le 10 ]; } \
        && ! { [ "$minute_actuelle" -ge 35 ] && [ "$minute_actuelle" -le 40 ]; }; then
        arreter "il y a une migration : elle se lance de :05 a :10 ou de :35 a :40."
    fi

    # Sauvegarde lancee a la main, ou plus longue que prevu. pg_dumpall s'annonce
    # « pg_dumpall », et chacun de ses pg_dump « pg_dump » : d'ou le LIKE.
    # / A running backup: pg_dumpall and its pg_dump children, hence LIKE.
    requete_sauvegarde_en_cours="SELECT count(*) FROM pg_stat_activity WHERE application_name LIKE 'pg_dump%'"
    nombre_de_sauvegardes=$(docker exec -e REQUETE="$requete_sauvegarde_en_cours" "$CONTENEUR_POSTGRES" \
        sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$REQUETE"')
    if [ "$nombre_de_sauvegardes" != "0" ]; then
        arreter "une sauvegarde (pg_dump) est en cours."
    fi
fi


# ---------------------------------------------------------------------------------------
# 6. Copie du code cible, controle, migration
# logs/ est ignore par git et monte dans le conteneur : la copie y est visible en
# /DjangoFiles/logs/code_cible. settings.py calcule BASE_DIR depuis son propre chemin, et
# manage.py met son dossier en tete de sys.path : tout le code vient de la copie.
# On appelle le python du venv DIRECTEMENT : `poetry run` lance depuis la copie y lirait un
# autre pyproject.toml et chercherait un autre venv.
# / Copy of the target code, check, migration. Run the venv python directly.
# ---------------------------------------------------------------------------------------
echo "== Copie du code cible dans $DOSSIER_CODE_CIBLE"
rm -rf "$DOSSIER_CODE_CIBLE"
mkdir -p "$DOSSIER_CODE_CIBLE"
git archive "$commit_cible" | tar -x -C "$DOSSIER_CODE_CIBLE"
# LOGGING ecrit dans BASE_DIR/logs/Djangologfile : le dossier doit exister dans la copie.
# / LOGGING writes into BASE_DIR/logs: the folder must exist in the copy.
mkdir -p "$DOSSIER_CODE_CIBLE/logs"

python_du_venv=$(docker exec "$CONTENEUR" bash -c 'cd /DjangoFiles && poetry env info -p')/bin/python

# Un worker gunicorn qui ne demarre pas (code 3 ou 4) fait s'arreter le maitre ET tous les
# autres workers : tout le site tombe. Ce controle doit donc passer AVANT que le code arrive
# dans le dossier servi. Il reprend ce que fait un worker : django.setup(), middlewares
# (TiBillet.wsgi), daphne (TiBillet.asgi), et les deux resolveurs du prechauffage.
# `check` ajoute les system checks (ex. admin.E039, qui empeche Django de demarrer).
# / A worker that fails to boot halts the whole gunicorn. This check must pass BEFORE the
# code reaches the served folder.
echo "== Controle du code cible"
docker exec -w "/DjangoFiles/$DOSSIER_CODE_CIBLE" "$CONTENEUR" "$python_du_venv" manage.py check
docker exec -w "/DjangoFiles/$DOSSIER_CODE_CIBLE" "$CONTENEUR" "$python_du_venv" -c '
import TiBillet.wsgi, TiBillet.asgi
from django.conf import settings
from django.urls import get_resolver
get_resolver(settings.ROOT_URLCONF)._populate()
get_resolver(settings.PUBLIC_SCHEMA_URLCONF)._populate()
print("Code cible : wsgi, asgi et URLconf OK")
'

if [ "$faut_il_migrer" = "oui" ]; then
    # - nice / ionice : priorite CPU et disque minimale pour les process Python (heritee par
    #   les sous-process de l'executeur). Le travail fait par PostgreSQL n'est pas concerne.
    # - PGOPTIONS lock_timeout : un ALTER TABLE qui attend un verrou bloque toutes les
    #   requetes du site sur cette table. Au bout de 5 s, il abandonne : la migration EN COURS
    #   de ce schema est annulee (les precedentes restent appliquees), les autres schemas
    #   continuent, et la commande finit en erreur. Relancer make update reprend la ou on en est.
    # - executor multiprocessing : quelques minutes au lieu de plusieurs heures pour 500 lieux.
    #   Si une migration ajoute une cle etrangere vers une table publique, la spec conseille
    #   un lieu apres l'autre : EXECUTEUR=standard make update.
    # / Lowest CPU/disk priority, 5 s lock_timeout, multiprocessing executor by default.
    echo "== migrate_schemas (depuis la copie, l'ancien code continue de servir)"
    if ! docker exec -w "/DjangoFiles/$DOSSIER_CODE_CIBLE" -e PGOPTIONS="-c lock_timeout=5s" "$CONTENEUR" \
        nice -n 19 ionice -c3 \
        "$python_du_venv" manage.py migrate_schemas --executor="${EXECUTEUR:-multiprocessing}"; then
        echo "" >&2
        echo "Lignes utiles du journal :" >&2
        grep -inE "lock timeout|deadlock" "$FICHIER_JOURNAL" | tail -20 >&2 || true
        arreter "migrate_schemas a echoue. Le code servi n'a pas change. Corriger, puis relancer make update."
    fi
    echo "$commit_cible" > "$MARQUEUR_MIGRE"
fi


# ---------------------------------------------------------------------------------------
# 7. Le code arrive dans le dossier servi
# A partir d'ici, les anciens workers lisent les NOUVEAUX gabarits (pas de cached.Loader) :
# les etapes 7 et 8 s'enchainent sans attendre.
# / From here on, old workers read the NEW templates: steps 7 and 8 run back to back.
# ---------------------------------------------------------------------------------------
echo "== git merge --ff-only"
git merge --ff-only "$commit_cible"

echo "== collectstatic"
docker exec -w /DjangoFiles "$CONTENEUR" poetry run python manage.py collectstatic --no-input


# ---------------------------------------------------------------------------------------
# 8. Gunicorn : remplacement des workers un par un
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
            arreter "le nouveau worker gunicorn ne demarre pas correctement."
        fi
        if echo "$lignes_ecrites_depuis" | grep -qE "warmup worker [0-9]+ : "; then
            nouveau_worker_pret="oui"
            break
        fi
        sleep 1
    done
    if [ "$nouveau_worker_pret" != "oui" ]; then
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
# 9. Test : le site repond. /robots.txt passe par la resolution du tenant sans rien
# rediriger. Plusieurs appels : chacun tombe sur un worker au hasard.
# X-Forwarded-Proto : nginx le pose en vrai ; sans lui, Django se croit en HTTP.
# / Smoke test on /robots.txt, several times since each call hits a random worker.
# ---------------------------------------------------------------------------------------
echo "== Test de /robots.txt"
for essai in 1 2 3 4 5; do
    code_http=$(docker exec "$CONTENEUR" bash -c \
        'curl -s -o /dev/null -w "%{http_code}" -H "Host: $DOMAIN" -H "X-Forwarded-Proto: https" http://127.0.0.1:8002/robots.txt')
    if [ "$code_http" != "200" ]; then
        arreter "/robots.txt repond $code_http au lieu de 200. Les workers servent le nouveau code : regarder $FICHIER_LOG_GUNICORN."
    fi
done
echo "/robots.txt : 200"


# ---------------------------------------------------------------------------------------
# 10. daphne et celery, puis controle final
# Celery recoit TERM : il finit ses taches en cours avant de s'arreter.
# Supervisor annonce RUNNING au bout d'une seconde (startsecs) alors que Django met
# plusieurs secondes a demarrer : on attend avant le controle final.
# / daphne and celery, then a final check after Django had time to boot.
# ---------------------------------------------------------------------------------------
echo "== Redemarrage de daphne"
supervisorctl restart daphne
echo "== Redemarrage de celery"
supervisorctl restart celery

sleep 15
echo "== Etat final des services"
if ! tous_les_services_tournent; then
    arreter "un service n'est pas en RUNNING apres la mise a jour."
fi

echo "$commit_cible" > "$MARQUEUR_DEPLOYE"
rm -rf "$DOSSIER_CODE_CIBLE"
echo "Mise a jour terminee : ${commit_cible:0:8}."
