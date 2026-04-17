#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <image-repo> <tag>"
  echo "Example: $0 ghcr.io/erdembestas/k8s-insight-analyzer 0.1.0"
  exit 1
fi

IMAGE_REPO="$1"
IMAGE_TAG="$2"
IMAGE_NAME="$IMAGE_REPO:$IMAGE_TAG"

echo "Building image $IMAGE_NAME"
docker build -t "$IMAGE_NAME" -f docker/Dockerfile .

echo "Running quick smoke test"
docker run --rm \
  -e MOCK_LLM=1 \
  -e LLM_API_TOKEN=dummy \
  -v "$PWD/mocks:/mocks" \
  -v "$PWD:/opt/k8s-insight-analyzer" \
  -w /opt/k8s-insight-analyzer \
  -e PATH="/mocks:$PATH" \
  "$IMAGE_NAME" \
  /bin/sh -c 'export PATH=/mocks:$PATH && /usr/local/bin/entrypoint.sh'

echo "Logging into GHCR..."
read -rp 'GitHub username: ' GH_USER
read -rsp 'GHCR token: ' GH_TOKEN
printf '\n'

echo "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin

echo "Pushing $IMAGE_NAME"
docker push "$IMAGE_NAME"

echo "Published $IMAGE_NAME"
