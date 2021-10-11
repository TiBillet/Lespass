#!/bin/bash
SECONDS=0

# pour load une sql :
# après avoir lancé les 'export'
# Mais sans avoir fait de migrate !
# psql --dbname $POSTGRES_DB -f yourfile.sql
export DOMAIN=$DOMAIN

export PGPASSWORD=$POSTGRES_PASSWORD
export PGUSER=$POSTGRES_USER
export PGHOST=$POSTGRES_HOST

# borg init --encryption=repokey-blake2 .
# borg init --encryption=repokey-blake2 /SaveDb/borg

export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes
export BORG_RELOCATED_REPO_ACCESS_IS_OK=yes
export BORG_PASSPHRASE=$BORG_PASSPHRASE


touch /Backup/logs/backup_cron.log
touch /Backup/logs/error_backup_cron.log
DATE_NOW=`date +%Y-%m-%d-%H-%M`
MIGRATION=`ls /DjangoFiles/BaseBillet/migrations | grep -E '^[0]' | tail -1 | head -c 4`

PREFIX=$DOMAIN-M$MIGRATION

DUMPS_DIRECTORY="/Backup/dumps"
BORG_DIRECTORY="/Backup/borg"
LOG_FILE="/Backup/error_backup_cron.log"



echo $DATE_NOW" on dump la db en sql "
/usr/bin/pg_dumpall -f $DUMPS_DIRECTORY/$PREFIX-$DATE_NOW.sql

#echo $DATE_NOW" on dumpdata en json via manage.py "
#/usr/local/bin/python /DjangoFiles/manage.py dumpdata -e auth.permission -e contenttypes -e sessions --all > $DUMPS_DIRECTORY/$PREFIX-$DATE_NOW.json

# -e contenttypes -e auth.Permission -e sessions --all

echo $DATE_NOW" on supprime les vieux dumps sql de plus de 30min"
/usr/bin/find $DUMPS_DIRECTORY -mmin +30 -type f -delete

#echo $DATE_NOW" on check l'archive borg "
#/usr/bin/borg check /syncthing/data/bisik

echo $DATE_NOW" on cree l'archive borg "
/usr/bin/borg create -vs --compression lz4 \
    $BORG_DIRECTORY::$PREFIX-$DATE_NOW \
    $DUMPS_DIRECTORY

echo $DATE_NOW" on prune les vieux borg :"
/usr/bin/borg prune -v $BORG_DIRECTORY --prefix $PREFIX --list \
    --keep-within 2d --keep-daily=10 --keep-weekly=4 --keep-monthly=12
