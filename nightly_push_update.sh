#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

readonly IMAGE_NAME="lespass"
readonly DOCKER_USER="tibillet"

if [[ -f VERSION ]]; then
  VERSION="$(< VERSION)"
else
  echo "VERSION file not found next to this script" >&2
  exit 1
fi

git checkout PreProd
git pull

docker build -t "$DOCKER_USER/$IMAGE_NAME:nightly" -t "$DOCKER_USER/$IMAGE_NAME:nightly-$VERSION" .

docker push "$DOCKER_USER/$IMAGE_NAME:nightly"
docker push "$DOCKER_USER/$IMAGE_NAME:nightly-$VERSION"
