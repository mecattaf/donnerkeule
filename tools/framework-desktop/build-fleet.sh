#!/usr/bin/env bash
# Reproduce matching-kernel builds and the NHI source/header audit. No loading.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
versions=("$@")
if [ "$#" -eq 0 ]; then versions=(7.2.10 7.2.12); fi
for version in "${versions[@]}"; do
  case "$version" in
    7.2.10) revision=94d35c7c05087e8b07373a403c55e97d99ff9af9 ;;
    7.2.12) revision=dce1caf58d1a943af38b376e824a0d036ec3eea7 ;;
    *) echo "Unsupported fleet kernel: $version" >&2; exit 2 ;;
  esac
  nix build .#thunderbolt-ibverbs .#thunderbolt-ibverbs-no-profiling \
    .#checks.x86_64-linux.framework-ring-source \
    --override-input nixpkgs "github:NixOS/nixpkgs/$revision" \
    --no-write-lock-file --cores 8 --max-jobs 1 \
    --out-link "result-fleet-$version" -L
done
