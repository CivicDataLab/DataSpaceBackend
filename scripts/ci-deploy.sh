#!/bin/bash
# Deploy step logic, run on the dev host by the "Deploy" job in
# .github/workflows/deploy-backend.yml. Lives as a real file rather than an
# inline appleboy/ssh-action `script:` block -- ParakhAPI's equivalent
# pipeline hit a reproducible "syntax error near unexpected token ';'" from
# inline multi-line scripts sent through that action (confirmed the script
# text itself was valid bash both locally and on the target host every
# time; the corruption happened somewhere in the action's own transport,
# not in the script content). scp-action, which ships this file, has no
# such problem -- so complex logic never goes through the SSH action's
# inline `script:` here at all.
#
# Invoked as: sudo bash ci-deploy.sh "$IMAGE_REF" "$HEALTH_CHECK_URL" "$GHCR_USER"
# GHCR_TOKEN is read from .ghcr_token (shipped alongside this script,
# deleted immediately below) rather than passed as an argument, since
# argv is visible via ps aux for the process's lifetime.
#
# docker/docker compose need sudo on this host -- confirmed passwordless
# (sudo -n succeeds), so this script must itself be invoked with sudo.
set -euo pipefail

IMAGE_REF="$1"
HEALTH_CHECK_URL="$2"
GHCR_USER="$3"

mkdir -p .deploy
GHCR_TOKEN="$(cat .ghcr_token)"
rm -f .ghcr_token

# --- preflight -------------------------------------------------
AVAIL_MB=$(df -Pm . | awk "NR==2{print \$4}")
if [ "$AVAIL_MB" -lt 4096 ]; then
  echo "::error::Only ${AVAIL_MB}MB free on the deploy volume; refusing to pull. Free space and re-run."
  exit 1
fi
docker compose version >/dev/null 2>&1 || {
  echo "::error::Docker Compose V2 not available (V1 docker-compose is a different, incompatible tool)."
  exit 1
}

# --- record rollback anchor BEFORE touching anything -----------
PREV_REF="$(docker inspect --format "{{.Config.Image}}" DataSpace 2>/dev/null || true)"
if [ -z "$PREV_REF" ] && [ -f .deploy/current_image ]; then
  PREV_REF="$(cat .deploy/current_image)"
fi
# Only a digest ref is safely rollback-able. Anything else (a tag,
# a locally-built image, or nothing) means the previous state was
# hand-managed -- record that honestly instead of writing a value
# a later rollback would deploy blindly. The very first image-based
# deploy will land here: the currently running container was built
# locally (`dataexbackend-backend`), not pulled by digest.
case "$PREV_REF" in
  *@sha256:*) : ;;
  *)
    echo "::warning::No digest-pinned previous image found (got [${PREV_REF:-<none>}]). Automatic rollback is UNAVAILABLE for this run."
    PREV_REF=""
    ;;
esac
printf "%s" "$PREV_REF" > .deploy/previous_image

# --- pull the new image ----------------------------------------
# GHCR's toomanyrequests kept firing on every one of 5 attempts 5s apart
# (~25s total) in live testing despite each error reporting a sub-second
# retry-after -- that points to a sustained account-level quota, not a
# brief burst, so this is deliberately patient: 10 attempts, 30s apart,
# ~5 minutes of runway before giving up.
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  docker pull "$IMAGE_REF" && break
  if [ "$attempt" -eq 10 ]; then
    echo "::error::docker pull failed after 10 attempts."
    exit 1
  fi
  echo "pull attempt $attempt failed, retrying in 30s..."
  sleep 30
done
printf "DATASPACE_IMAGE=%s\n" "$IMAGE_REF" > .deploy/image.env

COMPOSE="docker compose -f docker-compose.yml --env-file .env --env-file .deploy/image.env"
RELEASE="$COMPOSE --profile release run --rm --no-deps -T release"
# The release service's entrypoint is already ["python", "manage.py"]
# (see docker-compose.yml) -- args below are manage.py subcommands
# only, not full "python manage.py ..." invocations.

# backend_db/elasticsearch/redis must be up before the release step below:
# it uses --no-deps (so compose never recreates them out from under a
# running deploy), which also means it will NOT wait for their
# depends_on healthchecks. In steady state these are already running,
# but a host that had the stack fully down would otherwise fail at
# migrate with a confusing connection error. up -d is idempotent --
# no-ops when they are already healthy and their config is unchanged.
$COMPOSE up -d backend_db elasticsearch redis

# --- release step, against the NEW image, before the swap ------
# Recorded for the rollback message: a rollback restores the image
# but NOT the schema, so whoever reads that failure needs to know
# what was applied.
$RELEASE showmigrations --plan 2>/dev/null | grep "^\[ \]" > .deploy/migrations.txt || true
$RELEASE migrate --noinput

# --- swap the running container ---------------------------------
# --no-deps so backend_db/elasticsearch/redis are never recreated
# out from under this.
$COMPOSE up -d --no-build --no-deps --force-recreate backend

# --- health gate, with in-job rollback (tier 1) ------------------
rollback_now() {
  echo "::error::$1"
  if [ -z "$PREV_REF" ]; then
    echo "::error::No previous image recorded -- the NEW image is still live. Manual intervention required."
    exit 1
  fi
  echo "Restoring $PREV_REF"
  printf "DATASPACE_IMAGE=%s\n" "$PREV_REF" > .deploy/image.env
  $COMPOSE up -d --no-build --no-deps --force-recreate backend
  exit 1
}

attempts=0
until curl -fsS -o /dev/null --max-time 10 "$HEALTH_CHECK_URL"; do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge 20 ]; then
    # $COMPOSE, not a bare docker compose -f ...: an explicit
    # --env-file disables .env auto-discovery, and DATASPACE_IMAGE
    # needs to keep resolving to the image just deployed for these
    # logs to target the right container.
    $COMPOSE logs --tail 50 backend || true
    rollback_now "Deployed image did not become healthy after $attempts attempts."
  fi
  sleep 5
done

printf "%s" "$IMAGE_REF" > .deploy/current_image
echo "Deploy healthy: $IMAGE_REF"
