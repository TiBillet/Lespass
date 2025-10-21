#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

readonly IMAGE_NAME="lespass"
readonly DOCKER_USER="tibillet"

git checkout PreProd
git pull

docker build -t "$DOCKER_USER/$IMAGE_NAME:nightly" .
docker push "$DOCKER_USER/$IMAGE_NAME:nightly"
