#!/usr/bin/env bash
# Reproduce matching-kernel builds and the NHI source/header audit. No loading.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
versions=("$@")
if [ "$#" -eq 0 ]; then versions=(7.2.10 7.2.12 7.3); fi
for version in "${versions[@]}"; do
  module_attr=thunderbolt-ibverbs
  source_attr=framework-ring-source
  tree_attr=framework-modules-tree
  case "$version" in
    7.2.10) revision=94d35c7c05087e8b07373a403c55e97d99ff9af9 ;;
    7.2.12) revision=dce1caf58d1a943af38b376e824a0d036ec3eea7 ;;
    7.3)
      revision=dce1caf58d1a943af38b376e824a0d036ec3eea7
      module_attr=thunderbolt-ibverbs-7-3
      source_attr=framework-ring-source-7-3
      tree_attr=framework-modules-tree-7-3
      ;;
    *) echo "Unsupported fleet kernel: $version" >&2; exit 2 ;;
  esac
  nix build ".#$module_attr" ".#${module_attr}-no-profiling" \
    ".#checks.x86_64-linux.$source_attr" \
    ".#checks.x86_64-linux.$tree_attr" \
    --override-input nixpkgs "github:NixOS/nixpkgs/$revision" \
    --no-write-lock-file --cores 8 --max-jobs 1 \
    --out-link "result-fleet-$version" -L
done
