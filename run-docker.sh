#!/usr/bin/env sh
# Build and run a one-off command on a service.

DOCKERFILE=docker/Dockerfile
IMAGE=clinic-test
# TAG=user
SERVICE=user-dev
ENV_FILE=.env.test  # use ./.pgpass
PGSERVICE=dev

SEND_EMAILS=false
FORGET_LAST=true

if [ -t 1 ]; then
    INTERACTIVE="-it"
else
    INTERACTIVE=""
fi

docker compose build -q user

docker compose run \
  --name $IMAGE \
  -e SEND_EMAILS=$SEND_EMAILS \
  -e FORGET_LAST=$FORGET_LAST \
  --rm \
  $SERVICE \
  "$@"

# docker compose down

# docker run \
#   $INTERACTIVE \
#   --name $IMAGE \
#   --env-file $ENV_FILE \
#   --env-file .secrets \
#   -e PGSERVICE=$PGSERVICE \
#   --rm \
#   $(docker build --target $TAG -t $IMAGE:$TAG -f "$DOCKERFILE" -q .) \
#   "$@"
