#!/usr/bin/env bash
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail

deployment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$deployment_dir/.." && pwd -P)"
build_dist_dir="$deployment_dir/regional-s3-assets"
webui_dir="$repo_root/source/webui"
infra_dir="$repo_root/source/infra"
manifest_generator_dir="$deployment_dir/manifest-generator"

export NPM_CONFIG_USERCONFIG="$repo_root/.npmrc"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_command node
require_command npm
require_command python3
require_command poetry

echo "Building deployable assets in $build_dist_dir"
rm -rf "$build_dist_dir"
mkdir -p "$build_dist_dir"

echo "Building WebUI"
npm --prefix "$webui_dir" ci
npm --prefix "$webui_dir" run build
mkdir -p "$build_dist_dir/webui"
cp -R "$webui_dir/dist/." "$build_dist_dir/webui/"

echo "Generating WebUI manifest"
npm --prefix "$manifest_generator_dir" ci
node "$manifest_generator_dir/app.js" \
  --target "$build_dist_dir/webui" \
  --output "$build_dist_dir/webui/webui-manifest.json"

echo "Building Lambda package"
BUILD_OUTPUT_DIR="$build_dist_dir" "$deployment_dir/build-lambdas.sh"

echo "Compiling infrastructure"
npm --prefix "$infra_dir" ci
npm --prefix "$infra_dir" run build

echo "Built:"
echo "  $build_dist_dir/lambda.zip"
echo "  $build_dist_dir/webui/"
