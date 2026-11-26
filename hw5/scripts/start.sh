#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .local
if ! command -v kind >/dev/null 2>&1; then
  os=$(uname -s | tr '[:upper:]' '[:lower:]')
  arch=$(uname -m)
  case "$arch" in arm64|aarch64) arch=arm64;; x86_64) arch=amd64;; *) exit 1;; esac
  curl -fL "https://kind.sigs.k8s.io/dl/v0.30.0/kind-${os}-${arch}" -o .local/kind
  chmod +x .local/kind
  export PATH="$PWD/.local:$PATH"
fi
export BUILDX_CONFIG="$PWD/.local/buildx"
kind create cluster --name hw4-skills --image kindest/node:v1.34.0 --kubeconfig .local/kubeconfig --wait 180s
# Exact RustFS image from HW2; the experiment loads it directly into kind.
docker pull rustfs/rustfs@sha256:1803faef57627e2d9c2e7d89d655d712ddded5389040054987163043fecb6a3c
docker tag rustfs/rustfs@sha256:1803faef57627e2d9c2e7d89d655d712ddded5389040054987163043fecb6a3c rustfs/rustfs:latest
python3 scripts/run_lab.py --kubeconfig .local/kubeconfig
python3 scripts/verify_submission.py
python3 scripts/build_report.py
