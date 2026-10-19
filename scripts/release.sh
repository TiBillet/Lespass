#!/bin/bash
# Release : construit l'image Docker d'origin/main et la pousse sur Docker Hub.
# / Release: builds the Docker image of origin/main and pushes it to Docker Hub.
#
# LOCALISATION : scripts/release.sh — appele par le Makefile (make release), lance par le
# mainteneur, sur SA machine (connecte a Docker Hub : docker login).
# Spec : TECH_DOC/SESSIONS/DEPLOIEMENT/SPEC.md (geste 1).
#
# FLUX :
# 1. git fetch de main. L'image est TOUJOURS celle d'origin/main, quelle que soit la
#    branche ou l'on se trouve et l'etat du dossier local : c'est exactement le commit
#    que la prod tirera (make update suit origin/main).
# 2. VERSION est lu dans origin/main (fichier VERSION du commit, pas celui du dossier).
# 3. Extrait le commit (git archive) dans un dossier temporaire et construit l'image
#    depuis ce dossier. Deux barrieres contre les fuites dans l'image PUBLIQUE :
#    seuls les fichiers suivis par git, puis le .dockerignore.
# 4. Pousse les tags latest et $VERSION.
#
# Chaque release doit avoir son numero : le script refuse un $VERSION deja publie (le tag
# de version sert a revenir en arriere, il ne doit jamais etre ecrase).
# REFAIRE_LA_BASE=1 make release : retelecharge python:3.11 et reconstruit tout
# (systeme a jour, venv repousse). A faire lors d'une grosse mise a jour, pas a chaque
# release : sinon chaque release repousse et fait retelecharger tout le venv.
#
# L'image porte le label org.opencontainers.image.revision = SHA du commit.
# make update (scripts/mise_a_jour_prod.sh) le lit pour verifier que latest est bien
# l'image du commit qu'il deploie.
# / The image is always origin/main's; it carries the commit SHA as a label, which
# make update checks.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

readonly IMAGE="tibillet/lespass"
readonly BRANCHE_DE_PROD="main"
readonly REFERENCE="origin/$BRANCHE_DE_PROD"

# 1. Le commit a construire : le bout d'origin/main, fraichement recupere.
# / 1. The commit to build: the tip of origin/main, freshly fetched.
git fetch origin "$BRANCHE_DE_PROD"
commit_de_la_release=$(git rev-parse "$REFERENCE")

# Seulement une information : la branche courante et le dossier local ne comptent pas.
# / Information only: the current branch and the local folder do not matter.
if [[ "$(git rev-parse HEAD)" != "$commit_de_la_release" ]]; then
  echo "Info : HEAD ($(git rev-parse --abbrev-ref HEAD), $(git rev-parse --short HEAD)) n'est pas $REFERENCE."
  echo "       L'image est construite depuis $REFERENCE, pas depuis le dossier local."
fi

# 2. VERSION tel qu'il est dans le commit construit.
# / 2. VERSION as it is in the built commit.
VERSION=$(git show "$commit_de_la_release:VERSION" | sed -n "s/^VERSION=['\"]\{0,1\}\([^'\" ]*\)['\"]\{0,1\} *$/\1/p")
if [[ -z "$VERSION" ]]; then
  echo "Pas de ligne VERSION=... dans le fichier VERSION de $REFERENCE." >&2
  exit 1
fi
echo "Release $VERSION — $REFERENCE ${commit_de_la_release:0:12}"

# Un tag de version deja publie ne s'ecrase pas : incrementer VERSION sur main.
# / A published version tag is never overwritten: bump VERSION on main.
if docker manifest inspect "$IMAGE:$VERSION" >/dev/null 2>&1; then
  echo "$IMAGE:$VERSION existe deja sur Docker Hub : incrementer VERSION sur $BRANCHE_DE_PROD, pousser, relancer." >&2
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

echo "Release poussee : $IMAGE:latest et $IMAGE:$VERSION ($REFERENCE ${commit_de_la_release:0:12})."
