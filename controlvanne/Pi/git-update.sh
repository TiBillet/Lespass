#!/bin/bash
# Script de mise à jour au démarrage

set -e

# Charger les variables d'environnement
set -a
[ -f /home/sysop/tibeer/.env ] && . /home/sysop/tibeer/.env
set +a

# Vérifier si les variables sont définies
if [ -z "$GIT_REPO" ] || [ -z "$GIT_BRANCH" ]; then
    echo "⚠️  GIT_REPO ou GIT_BRANCH non défini dans .env, saut de la mise à jour"
    exit 0
fi

cd /home/sysop/tibeer

# Vérifier si c'est un repo git, sinon l'initialiser
if [ ! -d ".git" ]; then
    echo "📦 Initialisation du dépôt git..."
    git init
    git remote add origin "$GIT_REPO"
    echo "✅ Dépôt git initialisé avec remote: $GIT_REPO"
    
    # Récupérer les données du repo distant
    echo "⬇️  Récupération des données du dépôt distant..."
    git fetch origin "$GIT_BRANCH"
    
    # Créer une branche locale qui suit la branche distante
    git checkout -b "$GIT_BRANCH" "origin/$GIT_BRANCH" || {
        echo "⚠️  Impossible de checkout la branche $GIT_BRANCH, tentative avec git pull..."
        git pull origin "$GIT_BRANCH" --allow-unrelated-histories || {
            echo "⚠️  Conflit détecté, utilisation de la version distante..."
            git checkout --theirs .
            git add -A
            git commit -m "Auto-merge: use remote version"
        }
    }
    
    echo "✅ Dépôt initialisé et synchronisé"
    exit 0
fi

echo "🔄 Mise à jour depuis $GIT_REPO (branche: $GIT_BRANCH)..."

# Vérifier s'il y a des commits avant de faire un stash
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    # Sauvegarder les modifications locales non commitées
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo "💾 Sauvegarde des modifications locales..."
        git stash push -m "Auto-stash avant git pull $(date)" || true
        STASHED=true
    else
        STASHED=false
    fi
else
    echo "⚠️  Pas de commit initial, impossible de faire un stash"
    STASHED=false
fi

# Faire le git pull
echo "⬇️  Git pull..."
if git pull origin "$GIT_BRANCH"; then
    echo "✅ Mise à jour réussie"
    
    # Restaurer les modifications locales si elles existent
    if [ "$STASHED" = true ]; then
        echo "📦 Restauration des modifications locales..."
        git stash pop 2>/dev/null || echo "⚠️  Pas de stash à restaurer ou conflit"
    fi
else
    echo "❌ Erreur lors du git pull"
    exit 1
fi

# Mettre à jour les permissions
chown -R sysop:sysop /home/sysop/tibeer

echo "✅ Mise à jour terminée"
exit 0
