#!/usr/bin/env bash
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Build the legacy AWS Solutions distribution layout. This path is intended for
# publishing CloudFormation templates and regional assets. For normal
# development and deployment, use deployment/cdk.sh instead.

set -Eeuo pipefail
[[ "${DEBUG:-false}" == "true" ]] && set -x

deployment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$deployment_dir/.." && pwd -P)"
source_dir="$repo_root/source"
infra_dir="$source_dir/infra"
helper_dir="$deployment_dir/cdk-solution-helper"
staging_dist_dir="$deployment_dir/staging"
template_dist_dir="$deployment_dir/global-s3-assets"
build_dist_dir="$deployment_dir/regional-s3-assets"
cdk_version="2.1021.0"

export NPM_CONFIG_USERCONFIG="$repo_root/.npmrc"

usage() {
  echo "Usage: $0 <bucket-base-name> [solution-name] <version>" >&2
  echo "Example: $0 my-bucket account-assessment-for-aws-organizations v1.1.13" >&2
  exit 2
}

if [[ ! -f "$deployment_dir/solution_config" ]]; then
  echo "Missing $deployment_dir/solution_config" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$deployment_dir/solution_config"

solution_bucket="${1:-}"
if [[ $# -ge 3 ]]; then
  version="$3"
elif [[ $# -ge 2 ]]; then
  version="$2"
else
  version="${SOLUTION_VERSION:-}"
fi

[[ -n "$solution_bucket" && -n "$version" ]] || usage
[[ -n "${SOLUTION_ID:-}" ]] || { echo "SOLUTION_ID is missing from solution_config" >&2; exit 1; }
[[ -n "${SOLUTION_NAME:-}" ]] || { echo "SOLUTION_NAME is missing from solution_config" >&2; exit 1; }
[[ -n "${SOLUTION_TRADEMARKEDNAME:-}" ]] || {
  echo "SOLUTION_TRADEMARKEDNAME is missing from solution_config" >&2
  exit 1
}

if [[ "$version" != v* ]]; then
  version="v$version"
fi

export ASSET_MODE=distribution
export DIST_OUTPUT_BUCKET="$solution_bucket"
export SOLUTION_ID
export SOLUTION_NAME
export SOLUTION_TRADEMARKEDNAME
export SOLUTION_VERSION="$version"
export overrideWarningsEnabled=false

cleanup() {
  rm -rf "$staging_dist_dir"
  npm --prefix "$infra_dir" run cleanup:tsc >/dev/null 2>&1 || true
  rm -rf "$helper_dir/build"
}
trap cleanup EXIT

echo "Cleaning distribution output"
rm -rf "$template_dist_dir" "$build_dist_dir" "$staging_dist_dir"
mkdir -p "$template_dist_dir" "$build_dist_dir" "$staging_dist_dir"

"$deployment_dir/build-assets.sh"

echo "Building CDK solution helper"
npm --prefix "$helper_dir" ci
npm --prefix "$helper_dir" run build

echo "Synthesizing distribution templates"
npm --prefix "$infra_dir" ci
current_cdk_version="$("$infra_dir/node_modules/aws-cdk/bin/cdk" --version | grep -Eo '^[0-9]+\.[0-9]+\.[0-9]+')"
if [[ "$current_cdk_version" != "$cdk_version" ]]; then
  echo "Required CDK version is $cdk_version; found $current_cdk_version" >&2
  exit 1
fi
npm --prefix "$infra_dir" run build
(
  cd "$infra_dir"
  ./node_modules/aws-cdk/bin/cdk synth '*' --output "$staging_dist_dir"
)

shopt -s nullglob
template_files=("$staging_dist_dir"/*.template.json)
if [[ ${#template_files[@]} -eq 0 ]]; then
  echo "CDK did not produce any templates in $staging_dist_dir" >&2
  exit 1
fi

for template_file in "${template_files[@]}"; do
  template_name="$(basename "$template_file")"
  cp "$template_file" "$template_dist_dir/${template_name%.json}"
done

if [[ "${RUN_SOLUTION_HELPER:-true}" == "true" ]]; then
  (
    cd "$helper_dir"
    node build/index.js
  )
fi

echo "Replacing distribution tokens"
for template_file in "$template_dist_dir"/*.template; do
  sed \
    -e "s|%%BUCKET_NAME%%|$solution_bucket|g" \
    -e "s|%%SOLUTION_NAME%%|$SOLUTION_TRADEMARKEDNAME|g" \
    -e "s|%%VERSION%%|$version|g" \
    "$template_file" > "$template_file.tmp"
  mv "$template_file.tmp" "$template_file"
done

echo "Distribution assets built:"
echo "  $template_dist_dir"
echo "  $build_dist_dir"
