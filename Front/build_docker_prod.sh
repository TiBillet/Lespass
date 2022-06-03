#!/bin/sh
echo Building tibillet/front:build
docker build  -t tibillet/front:latest .
docker push tibillet/front:latest