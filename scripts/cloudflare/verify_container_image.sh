#!/bin/sh
set -eu

ROLE="${1:?container role is required}"
IMAGE="${2:?container image is required}"
PLATFORM="${PLATFORM:-linux/amd64}"
CONTAINER="ordinarium-ci-${ROLE}-$$"

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

case "$ROLE" in
    web)
        docker run --detach --platform "$PLATFORM" --name "$CONTAINER" \
            --env SECRET_KEY=container-ci-smoke \
            --env TURNSTILE_ENABLED=false \
            "$IMAGE" >/dev/null
        ;;
    documents)
        docker run --detach --platform "$PLATFORM" --name "$CONTAINER" \
            "$IMAGE" >/dev/null
        ;;
    jobs)
        docker run --detach --platform "$PLATFORM" --name "$CONTAINER" \
            --env ORDINARIUM_CONTAINER_ROLE=pco-jobs \
            "$IMAGE" >/dev/null
        ;;
    *)
        echo "Unsupported container role: $ROLE" >&2
        exit 2
        ;;
esac

attempts=0
while [ "$attempts" -lt 45 ]; do
    status="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER")"
    if [ "$status" = "healthy" ]; then
        break
    fi
    if [ "$status" = "unhealthy" ]; then
        docker logs "$CONTAINER"
        exit 1
    fi
    attempts=$((attempts + 1))
    sleep 1
done

if [ "${status:-starting}" != "healthy" ]; then
    docker logs "$CONTAINER"
    exit 1
fi

test "$(docker exec "$CONTAINER" id -u)" = "10001"

case "$ROLE" in
    web)
        docker exec "$CONTAINER" python -c \
            "import requests; from jinja2 import Template; assert Template('{{ value }}').render(value='ok') == 'ok'; assert requests.Session"
        ;;
    documents)
        docker exec "$CONTAINER" python -c \
            "from weasyprint import HTML; assert HTML(string='<p>ok</p>').write_pdf().startswith(b'%PDF')"
        docker exec "$CONTAINER" python -c \
            "from docx import Document; document=Document(); document.add_paragraph('ok'); assert document.paragraphs[0].text == 'ok'"
        ;;
    jobs)
        docker exec "$CONTAINER" python -c \
            "import cryptography, httpx, requests"
        ;;
esac

docker stop --time 10 "$CONTAINER" >/dev/null
test "$(docker inspect --format '{{.State.ExitCode}}' "$CONTAINER")" = "0"
