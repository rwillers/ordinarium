#!/bin/sh
set -eu

PLATFORM="${PLATFORM:-linux/amd64}"
PREFIX="ordinarium-phase2"
ROLES="web documents jobs"

cleanup() {
    for role in $ROLES; do
        docker rm -f "${PREFIX}-${role}" >/dev/null 2>&1 || true
    done
}

wait_for_health() {
    container="$1"
    attempts=0
    while [ "$attempts" -lt 45 ]; do
        status="$(docker inspect --format '{{.State.Health.Status}}' "$container")"
        if [ "$status" = "healthy" ]; then
            return 0
        fi
        if [ "$status" = "unhealthy" ]; then
            docker logs "$container"
            return 1
        fi
        attempts=$((attempts + 1))
        sleep 1
    done
    docker logs "$container"
    return 1
}

trap cleanup EXIT INT TERM
cleanup

for role in $ROLES; do
    docker buildx build \
        --platform "$PLATFORM" \
        --file "containers/${role}/Dockerfile" \
        --tag "${PREFIX}-${role}:local" \
        --load \
        .
done

docker run --detach --platform "$PLATFORM" \
    --name "${PREFIX}-web" \
    --env SECRET_KEY=phase2-smoke-test \
    --env TURNSTILE_ENABLED=false \
    "${PREFIX}-web:local" >/dev/null

docker run --detach --platform "$PLATFORM" \
    --name "${PREFIX}-documents" \
    "${PREFIX}-documents:local" >/dev/null

docker run --detach --platform "$PLATFORM" \
    --name "${PREFIX}-jobs" \
    --env ORDINARIUM_CONTAINER_ROLE=pco-jobs \
    "${PREFIX}-jobs:local" >/dev/null

for role in $ROLES; do
    wait_for_health "${PREFIX}-${role}"
    test "$(docker exec "${PREFIX}-${role}" id -u)" = "10001"
done

docker exec "${PREFIX}-documents" python -c \
    "from weasyprint import HTML; assert HTML(string='<p>ok</p>').write_pdf().startswith(b'%PDF')"
docker exec "${PREFIX}-documents" python -c \
    "from docx import Document; document=Document(); document.add_paragraph('ok'); assert document.paragraphs[0].text == 'ok'"
docker exec "${PREFIX}-web" python -c \
    "import importlib.util; assert importlib.util.find_spec('weasyprint') is None; assert importlib.util.find_spec('docx') is None"
docker exec "${PREFIX}-jobs" python -c \
    "import cryptography, httpx, requests; import importlib.util; assert importlib.util.find_spec('weasyprint') is None; assert importlib.util.find_spec('docx') is None"

for role in $ROLES; do
    docker stop --time 10 "${PREFIX}-${role}" >/dev/null
    test "$(docker inspect --format '{{.State.ExitCode}}' "${PREFIX}-${role}")" = "0"
done

echo "Phase 2 container verification passed for ${PLATFORM}."
