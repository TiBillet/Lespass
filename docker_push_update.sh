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

# MIGRATE=1 ferait lancer migrate_schemas par start.sh a chaque demarrage du conteneur :
# une recreation du conteneur de prod deviendrait une coupure de plusieurs minutes.
# / MIGRATE=1 would run migrate_schemas at every container start: a long outage.
if [[ "${MIGRATE:-0}" != "0" ]]; then
  echo "MIGRATE=${MIGRATE} dans VERSION : remettre MIGRATE=0 (make update migre lui-meme)." >&2
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

# 3. Construction depuis le commit extrait. PAS de `git archive | docker build -` :
# avec un contexte tar sur l'entree standard, BuildKit n'applique pas le .dockerignore.
# / 3. Build from the extracted commit. Not from stdin: BuildKit would skip .dockerignore.
dossier_de_construction=$(mktemp -d)
trap 'rm -rf "$dossier_de_construction"' EXIT
git archive "$commit_de_la_release" | tar -x -C "$dossier_de_construction"

docker build \
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
