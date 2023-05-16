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
# borg init --encryption=repokey-blake2 /Backup/borg




touch /Backup/logs/backup_cron.log
touch /Backup/logs/error_backup_cron.log
DATE_NOW=`date +%Y-%m-%d-%H-%M`
MIGRATION=`ls /DjangoFiles/BaseBillet/migrations | grep -E '^[0]' | tail -1 | head -c 4`

PREFIX=$DOMAIN-M$MIGRATION

DUMPS_DIRECTORY="/Backup/dumps"
LOG_FILE="/Backup/error_backup_cron.log"



echo $DATE_NOW" on dump la db en sql "
/usr/bin/pg_dumpall -f $DUMPS_DIRECTORY/$PREFIX-$DATE_NOW.sql

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


#echo $DATE_NOW" on prune les vieux borg :"
#/usr/bin/borg prune -v $BORG_DIRECTORY --prefix $PREFIX --list \
#    --keep-within 2d --keep-daily=10 --keep-weekly=4 --keep-monthly=12
