#!/bin/bash
set -e
# Sans pipefail, « pg_dumpall | gzip » renvoie le code de gzip (0) même si pg_dumpall échoue :
# le dump tronqué part dans borg et les anciens dumps sont supprimés.
set -o pipefail

# pour load une sql :
# après avoir lancé les 'export'
# Mais sans avoir fait de migrate !
# psql --dbname $POSTGRES_DB -f yourfile.sql
export DOMAIN=$DOMAIN

export PGPASSWORD=$POSTGRES_PASSWORD
export PGUSER=$POSTGRES_USER
export PGHOST=lespass_postgres

# Dans le cas d'un nouveau dépot BorgWarehouse ou d'un déplacement depuis ancienne méthode :
# Ajouter l'adresse et une clé dans le .env ( l'adresse se récupère sur le front de BWH )
# borg init --encryption=repokey-blake2 $BORG_REPO
# borg init --encryption=repokey-blake2 /Backup/borg

DATE_NOW=$(date +%Y-%m-%d-%H-%M)
MIGRATION=$(ls /DjangoFiles/BaseBillet/migrations | grep -E '^[0]' | tail -1 | head -c 4)

PREFIX=$DOMAIN-M$MIGRATION

DUMPS_DIRECTORY="/Backup/dumps"
mkdir -p $DUMPS_DIRECTORY

# Verrou partage avec make update (scripts/mise_a_jour_prod.sh), seulement le temps du
# pg_dumpall : il pose un verrou sur toutes les tables, une migration lancee en meme temps
# echouerait. Pendant un make update, la sauvegarde attend ; apres 25 min (avant le cron
# suivant, pour ne pas les empiler), elle est sautee : la suivante passera.
# Le fichier est cree par make update (hote, dossier monte) ; ouvert en lecture seule,
# flock n'a pas besoin du droit d'ecriture. Absent : aucun make update n'a jamais tourne.
# / Lock shared with make update, held only during pg_dumpall.
VERROU_MISE_A_JOUR="/DjangoFiles/logs/mise_a_jour.lock"
if [ -e "$VERROU_MISE_A_JOUR" ]; then
  exec 9<"$VERROU_MISE_A_JOUR"
  if ! /usr/bin/flock -w 1500 9; then
    echo $DATE_NOW" make update tourne depuis plus de 25 min : sauvegarde sautee" >&2
    exit 1
  fi
fi

echo $DATE_NOW" on dump la db en sql "
/usr/bin/pg_dumpall | gzip >$DUMPS_DIRECTORY/$PREFIX-$DATE_NOW.sql.gz

# Le dump est fini : make update peut partir pendant l'envoi borg.
# / Dump done: make update may start during the borg upload.
exec 9<&-

echo $DATE_NOW" on supprime les vieux dumps sql de plus de 30min"
/usr/bin/find $DUMPS_DIRECTORY -mmin +30 -type f -delete

#### BORG SEND TO SSH ####

export BORG_REPO=$BORG_REPO
export BORG_PASSPHRASE=$BORG_PASSPHRASE
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes
export BORG_RELOCATED_REPO_ACCESS_IS_OK=yes

echo $DATE_NOW" on cree l'archive borg "
/usr/bin/borg create -vs --compression lz4 \
  $BORG_REPO::$PREFIX-$DATE_NOW \
  $DUMPS_DIRECTORY

### BORG WWW FOLDER : media and logs
echo $DATE_NOW" on cree l'archive pour www (media et logs) "
/usr/bin/borg create -vs --compression lz4 \
  $BORG_REPO::$PREFIX-"MEDIA"-$DATE_NOW \
  /DjangoFiles/www


echo $DATE_NOW" on prune les vieux borg :"
/usr/bin/borg prune -v --list --keep-within=7d --keep-daily=30 --keep-weekly=12 --keep-monthly=-1 --keep-yearly=-1 $BORG_REPO
