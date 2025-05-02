#!/bin/bash

VERSION="1.1.1"
IMAGE_NAME="lespass"
DOCKER_USER="tibillet"

git pull || exit 1
docker build -t $IMAGE_NAME . || exit 1
docker tag $IMAGE_NAME $DOCKER_USER/$IMAGE_NAME:latest
docker tag $IMAGE_NAME $DOCKER_USER/$IMAGE_NAME:$VERSION
docker push $DOCKER_USER/$IMAGE_NAME:latest
docker push $DOCKER_USER/$IMAGE_NAME:$VERSION
