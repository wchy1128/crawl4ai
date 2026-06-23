#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Build a custom Crawl4AI image from your GitHub fork.
# All code comes from GitHub — no local project files needed.
#
# Just put this script + Dockerfile.custom in the same directory:
#   bash build-custom-image.sh
#
# Override defaults with env vars:
#   BASE_IMAGE=my-registry/crawl4ai:latest bash build-custom-image.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BASE_IMAGE="${BASE_IMAGE:-docker.1ms.run/unclecode/crawl4ai:latest}"
TAG="${TAG:-crawl4ai-wchy-dev:latest}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/wchy1128/crawl4ai.git}"
GITHUB_BRANCH="${GITHUB_BRANCH:-wchy_dev}"

# Build-time proxy (optional). Set HTTP_PROXY/HTTPS_PROXY in the shell to speed
# up apt/pip/git downloads during build. Only passed as --build-arg, NOT baked
# into the image (Dockerfile uses ARG, not ENV). Lowercase variants are also
# honored — Linux tools commonly read either.
HTTP_PROXY="${HTTP_PROXY:-${http_proxy:-}}"
HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-}}"
NO_PROXY="${NO_PROXY:-${no_proxy:-localhost,127.0.0.1,::1}}"

echo "========================================="
echo " Building custom Crawl4AI image"
echo "========================================="
echo "  Base image : ${BASE_IMAGE}"
echo "  Output tag : ${TAG}"
echo "  GitHub repo: ${GITHUB_REPO}"
echo "  Branch     : ${GITHUB_BRANCH}"
if [ -n "${HTTP_PROXY}${HTTPS_PROXY}" ]; then
    echo "  HTTP proxy : ${HTTP_PROXY:-<unset>}"
    echo "  HTTPS proxy: ${HTTPS_PROXY:-<unset>}"
    echo "  No proxy   : ${NO_PROXY}"
else
    echo "  Proxy      : (none)"
fi
echo "  Script dir : ${SCRIPT_DIR}"
echo "========================================="

cd "${SCRIPT_DIR}"

# Make sure the base image exists locally
if ! docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
    echo "==> Pulling base image..."
    docker pull "${BASE_IMAGE}"
fi

# Assemble build args. Proxy args are only appended when set so we don't
# pollute builds that don't need them.
BUILD_ARGS=(
    --build-arg "BASE_IMAGE=${BASE_IMAGE}"
    --build-arg "GITHUB_REPO=${GITHUB_REPO}"
    --build-arg "GITHUB_BRANCH=${GITHUB_BRANCH}"
)
if [ -n "${HTTP_PROXY}" ]; then
    BUILD_ARGS+=(--build-arg "HTTP_PROXY=${HTTP_PROXY}")
fi
if [ -n "${HTTPS_PROXY}" ]; then
    BUILD_ARGS+=(--build-arg "HTTPS_PROXY=${HTTPS_PROXY}")
fi
if [ -n "${HTTP_PROXY}${HTTPS_PROXY}" ]; then
    BUILD_ARGS+=(--build-arg "NO_PROXY=${NO_PROXY}")
fi

docker build \
    --progress=plain \
    --no-cache \
    "${BUILD_ARGS[@]}" \
    -t "${TAG}" \
    -f ./Dockerfile.custom \
    .

echo ""
echo "========================================="
echo " Build complete: ${TAG}"
echo "========================================="
echo ""
echo "Quick test:"
echo "  docker run --rm -p 11235:11235 ${TAG}"
