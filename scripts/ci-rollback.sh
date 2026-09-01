#!/bin/bash
# Rollback-on-smoke-failure logic, run on the dev host. See ci-deploy.sh's
# header comment for why this lives as a real file instead of an inline
# appleboy/ssh-action script.
#
# Invoked as: sudo bash ci-rollback.sh "$HEALTH_CHECK_URL" "$GHCR_USER"
# GHCR_TOKEN is read from .ghcr_token (shipped alongside this script,
# deleted immediately below) rather than passed as an argument.
set -euo pipefail

HEALTH_CHECK_URL="$1"
GHCR_USER="$2"

GHCR_TOKEN="$(cat .ghcr_token)"
rm -f .ghcr_token

PREV_REF="$(cat .deploy/previous_image 2>/dev/null || true)"
if [ -z "$PREV_REF" ]; then
  echo "::error::Smoke tests failed but no previous image is recorded -- the NEW image is still live. Manual intervention required."
  exit 1
fi

# finalize-deploy is the only pruner and it did not run, so the
# previous image should still be local. Pull is a safety net.
docker image inspect "$PREV_REF" >/dev/null 2>&1 || {
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
  docker pull "$PREV_REF"
}

printf "DATASPACE_IMAGE=%s\n" "$PREV_REF" > .deploy/image.env
COMPOSE="docker compose -f docker-compose.yml --env-file .env --env-file .deploy/image.env"

$COMPOSE up -d --no-build --no-deps --force-recreate backend

attempts=0
until curl -fsS -o /dev/null --max-time 10 "$HEALTH_CHECK_URL"; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge 20 ]; then
    echo "::error::Rolled-back image did not become healthy after $attempts attempts."
    exit 1
  fi
  sleep 5
done

printf "%s" "$PREV_REF" > .deploy/current_image
echo "Rolled back to $PREV_REF"
echo "NOTE: migrations applied by the failed deploy were NOT reverted:"
cat .deploy/migrations.txt 2>/dev/null || echo "  (none recorded)"
