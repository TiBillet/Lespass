#!/bin/bash
# Release : construit l'image Docker du commit courant et la pousse sur Docker Hub.
# / Release: builds the Docker image of the current commit and pushes it to Docker Hub.
#
# LOCALISATION : docker_push_update.sh — lance par le mainteneur, sur SA machine.
# Spec : TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md (geste 1).
#
# FLUX :
# 1. Refuse des modifications non commitees : l'image doit etre EXACTEMENT un commit.
# 2. Refuse un commit absent du depot distant : la prod doit pouvoir le recuperer.
# 3. Extrait le commit (git archive) dans un dossier temporaire et construit l'image
#    depuis ce dossier. Deux barrieres contre les fuites dans l'image PUBLIQUE :
#    seuls les fichiers suivis par git, puis le .dockerignore.
# 4. Pousse les tags latest et $VERSION (fichier VERSION).
#
# Chaque release doit avoir son numero : le script refuse un $VERSION deja publie (le tag
# de version sert a revenir en arriere, il ne doit jamais etre ecrase).
# REFAIRE_LA_BASE=1 ./docker_push_update.sh : retelecharge python:3.11 et reconstruit tout
# (systeme a jour, venv repousse). A faire lors d'une grosse mise a jour, pas a chaque
# release : sinon chaque release repousse et fait retelecharger tout le venv.
#
# L'image porte le label org.opencontainers.image.revision = SHA du commit.
# make update (scripts/mise_a_jour_prod.sh) le lit pour verifier que latest est bien
# l'image du commit qu'il deploie.
# / The image carries the commit SHA as a label; make update checks it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

readonly IMAGE="tibillet/lespass"

# Charger les variables depuis le fichier VERSION (contient des assignments shell)
# / Load variables from the VERSION file (shell assignments)
if [[ -f VERSION ]]; then
  # shellcheck disable=SC1091
  source VERSION
  if [[ -z "${VERSION:-}" ]]; then
    echo "La variable VERSION n'est pas définie dans le fichier VERSION" >&2
    exit 1
  fi
else
  echo "VERSION file not found next to this script" >&2
  exit 1
fi

# 1. Aucune modification non commitee. Les fichiers non suivis ne comptent pas :
# git archive ne les met pas dans l'image.
# / 1. No uncommitted change. Untracked files do not count: git archive ignores them.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  git status --short --untracked-files=no
  echo "Modifications non commitees : commiter avant la release." >&2
  exit 1
fi

# 2. Le commit doit etre sur le depot distant (branche suivie).
# / 2. The commit must be on the remote (tracked branch).
git fetch
if ! git merge-base --is-ancestor HEAD '@{u}'; then
  echo "Le commit $(git rev-parse --short HEAD) n'est pas sur $(git rev-parse --abbrev-ref '@{u}') : faire git push." >&2
  exit 1
fi

commit_de_la_release=$(git rev-parse HEAD)
echo "Release $VERSION — commit ${commit_de_la_release:0:12}"

# Un tag de version deja publie ne s'ecrase pas : incrementer VERSION.
# / A published version tag is never overwritten: bump VERSION.
if docker manifest inspect "$IMAGE:$VERSION" >/dev/null 2>&1; then
  echo "$IMAGE:$VERSION existe deja sur Docker Hub : incrementer VERSION dans le fichier VERSION." >&2
  exit 1
fi

options_de_construction=()
if [[ "${REFAIRE_LA_BASE:-0}" = "1" ]]; then
  options_de_construction=(--pull --no-cache)
fi

# 3. Construction depuis le commit extrait, et non depuis un `git archive | docker build -` :
# le .dockerignore n'est garanti que pour un contexte qui est un dossier (doc Docker,
# « build context »).
# / 3. Build from the extracted commit: .dockerignore is guaranteed for a directory context.
dossier_de_construction=$(mktemp -d)
trap 'rm -rf "$dossier_de_construction"' EXIT
git archive "$commit_de_la_release" | tar -x -C "$dossier_de_construction"

docker build "${options_de_construction[@]}" \
  -f "$dossier_de_construction/dockerfile" \
  --label "org.opencontainers.image.revision=$commit_de_la_release" \
  --label "org.opencontainers.image.version=$VERSION" \
  -t "$IMAGE:latest" \
  -t "$IMAGE:$VERSION" \
  "$dossier_de_construction"

# 4. Publication.
# / 4. Publish.
docker push "$IMAGE:latest"
docker push "$IMAGE:$VERSION"

echo "Release poussee : $IMAGE:latest et $IMAGE:$VERSION (commit ${commit_de_la_release:0:12})."
