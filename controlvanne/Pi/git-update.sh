#!/bin/bash
# Mise à jour au démarrage : git pull sur le dépôt.
# / Startup update: git pull on the repo.

REPO_DIR="/home/sysop/tibeer"

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "Repo git absent dans $REPO_DIR, saut de la mise à jour."
    exit 0
fi

echo "Mise à jour depuis origin..."
git -C "$REPO_DIR" pull || echo "git pull échoué (on continue)."
echo "Mise à jour terminée."
