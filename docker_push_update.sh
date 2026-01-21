#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

readonly IMAGE_NAME="lespass"
readonly DOCKER_USER="tibillet"

# Charger les variables depuis le fichier VERSION (contient maintenant des assignments shell)
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

git checkout main
git pull

docker build -t "$DOCKER_USER/$IMAGE_NAME:latest" -t "$DOCKER_USER/$IMAGE_NAME:$VERSION" .

docker push "$DOCKER_USER/$IMAGE_NAME:latest"
docker push "$DOCKER_USER/$IMAGE_NAME:$VERSION"
