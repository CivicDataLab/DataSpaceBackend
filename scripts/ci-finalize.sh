#!/bin/bash
# Finalize-deploy image pruning logic, run on the dev host. See
# ci-deploy.sh's header comment for why this lives as a real file instead
# of an inline appleboy/ssh-action script. No secrets needed here.
set -euo pipefail

CUR="$(cat .deploy/current_image 2>/dev/null || true)"
PREV="$(cat .deploy/previous_image 2>/dev/null || true)"

# Keep the previous image: it is what makes rollback instant, and
# survivable even if GHCR is unreachable during an incident.
# Build the ref list explicitly rather than relying on unquoted
# expansion to drop an empty PREV -- PREV is legitimately empty on
# a first deploy, and passing "" to docker inspect is an error.
KEEP_REFS=()
[ -n "$CUR" ] && KEEP_REFS+=("$CUR")
[ -n "$PREV" ] && KEEP_REFS+=("$PREV")
KEEP=""
if [ ${#KEEP_REFS[@]} -gt 0 ]; then
  KEEP="$(docker inspect --format "{{.Id}}" "${KEEP_REFS[@]}" 2>/dev/null | sort -u || true)"
fi

# Guard against the degenerate case: if we somehow resolved
# nothing to keep, pruning by ID below would remove every image
# for this repo including the one currently running. Bail instead.
if [ -z "$KEEP" ]; then
  echo "::warning::Could not resolve current/previous image IDs; skipping prune rather than risk removing the running image."
  docker image prune -f
  df -h .
  exit 0
fi

for id in $(docker images --no-trunc --format "{{.ID}}" "ghcr.io/civicdatalab/dataspacebackend" 2>/dev/null); do
  if ! printf "%s\n" "$KEEP" | grep -q "$id"; then
    docker rmi "$id" 2>/dev/null || true
  fi
done

# Dangling layers only. NEVER `docker system prune -a` here -- it
# would remove the previous image and silently disable rollback.
docker image prune -f
df -h .
