#!/usr/bin/env bash
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail

deployment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$deployment_dir/.." && pwd -P)"

generated_paths=(
  "$deployment_dir/cdk.out"
  "$deployment_dir/global-s3-assets"
  "$deployment_dir/regional-s3-assets"
  "$deployment_dir/staging"
  "$deployment_dir/cdk-solution-helper/build"
  "$deployment_dir/cdk-solution-helper/coverage"
  "$repo_root/source/infra/build"
  "$repo_root/source/infra/coverage"
  "$repo_root/source/infra/webui/build"
  "$repo_root/source/lambda/.coverage"
  "$repo_root/source/lambda/.pytest_cache"
  "$repo_root/source/lambda/coverage"
  "$repo_root/source/lambda/coverage.xml"
  "$repo_root/source/webui/dist"
  "$repo_root/source/webui/coverage"
)

for generated_path in "${generated_paths[@]}"; do
  rm -rf "$generated_path"
done

find "$deployment_dir" "$repo_root/source/lambda" \
  -type d \( -name '__pycache__' -o -name '.pytest_cache' \) \
  -prune -exec rm -rf {} +

echo "Removed generated build outputs."
