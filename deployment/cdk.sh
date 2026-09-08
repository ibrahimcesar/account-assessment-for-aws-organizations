#!/usr/bin/env bash
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail

deployment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$deployment_dir/.." && pwd -P)"
infra_dir="$repo_root/source/infra"

export NPM_CONFIG_USERCONFIG="$repo_root/.npmrc"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <cdk command> [arguments...]" >&2
  exit 2
fi

case "$1" in
  bootstrap|doctor|notices|acknowledge|version|--version|-v)
    ;;
  *)
    if [[ "${SKIP_ASSET_BUILD:-false}" != "true" ]]; then
      "$deployment_dir/build-assets.sh"
    fi
    ;;
esac

npm --prefix "$infra_dir" ci

export ASSET_MODE=local
exec npm --prefix "$infra_dir" run cdk -- "$@"
