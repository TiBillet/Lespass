#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

readonly IMAGE_NAME="lespass"
readonly DOCKER_USER="tibillet"

# Build and tag images
docker build -f dockerfile_nightly \
  -t "$DOCKER_USER/$IMAGE_NAME:nightly" \
  .

# Push
docker push "$DOCKER_USER/$IMAGE_NAME:nightly"
