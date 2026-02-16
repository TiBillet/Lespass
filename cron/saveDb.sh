#!/bin/bash
set -e

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

echo $DATE_NOW" on dump la db en sql "
/usr/bin/pg_dumpall | gzip >$DUMPS_DIRECTORY/$PREFIX-$DATE_NOW.sql.gz

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
