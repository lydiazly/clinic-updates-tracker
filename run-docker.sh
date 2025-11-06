#!/usr/bin/env sh
# Build and run the Docker image.

DOCKERFILE=docker/Dockerfile
IMAGE=clinic-test
TAG=user
SERVICE=user
ENV_FILE=.env.test
PGSERVICE=prod
IGNORE_HASH=true

if [ -t 1 ]; then
    INTERACTIVE="-it"
else
    INTERACTIVE=""
fi

docker compose build -q user

docker compose run \
  --name $IMAGE \
  -e IGNORE_HASH=$IGNORE_HASH \
  --rm \
  $SERVICE \
  "$@"

docker compose down

# docker run \
#   $INTERACTIVE \
#   --name $IMAGE \
#   --env-file $ENV_FILE \
#   --env-file .secrets \
#   -e PGSERVICE=$PGSERVICE \
#   --rm \
#   $(docker build --target $TAG -t $IMAGE:$TAG -f "$DOCKERFILE" -q .) \
#   "$@"
