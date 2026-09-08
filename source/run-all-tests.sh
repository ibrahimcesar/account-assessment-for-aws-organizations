#!/usr/bin/env bash
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail
[[ "${DEBUG:-false}" == "true" ]] && set -x

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$source_dir/.." && pwd -P)"
infra_dir="$source_dir/infra"
webui_dir="$source_dir/webui"
lambda_dir="$source_dir/lambda"
solution_helper_dir="$repo_root/deployment/cdk-solution-helper"
lambda_asset_dir="$repo_root/deployment/regional-s3-assets"
lambda_asset="$lambda_asset_dir/lambda.zip"
created_mock_asset=false

export NPM_CONFIG_USERCONFIG="$repo_root/.npmrc"
export POETRY_VIRTUALENVS_IN_PROJECT=false
export POETRY_VIRTUALENVS_PATH="${POETRY_VIRTUALENVS_PATH:-${TMPDIR:-/tmp}/account-assessment-poetry-envs}"

cleanup() {
  if [[ "$created_mock_asset" == "true" ]]; then
    rm -f "$lambda_asset"
  fi

  if [[ "${CLEAN:-true}" == "true" ]]; then
    rm -rf \
      "$infra_dir/coverage" \
      "$solution_helper_dir/coverage" \
      "$webui_dir/coverage" \
      "$lambda_dir/.coverage" \
      "$lambda_dir/.pytest_cache" \
      "$lambda_dir/coverage" \
      "$lambda_dir/coverage.xml"
    find "$lambda_dir" -type d -name '__pycache__' -prune -exec rm -rf {} +
  fi
}
trap cleanup EXIT

for command_name in npm poetry python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
done

python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$python_version" != "3.12" ]]; then
  echo "Python 3.12 is required to run the Lambda tests; found $python_version." >&2
  exit 1
fi

if [[ ! -f "$lambda_asset" ]]; then
  mkdir -p "$lambda_asset_dir"
  touch "$lambda_asset"
  created_mock_asset=true
fi

echo "Running infrastructure tests"
npm --prefix "$infra_dir" ci
npm --prefix "$infra_dir" test

echo "Running CDK solution helper tests"
npm --prefix "$solution_helper_dir" ci
npm --prefix "$solution_helper_dir" test

echo "Running WebUI tests"
npm --prefix "$webui_dir" ci
npm --prefix "$webui_dir" run test:ci

echo "Running Lambda tests"
(
  cd "$lambda_dir"
  poetry env use python3
  poetry sync
  poetry run python -m pytest \
    tests \
    --cov "$lambda_dir" \
    --cov-config "$lambda_dir/.coveragerc" \
    --cov-report term-missing \
    --cov-report "xml:$lambda_dir/coverage.xml" \
    --cov-report "html:$lambda_dir/coverage" \
    -ra \
    -q \
    -p tests.plugins.env_vars
)

echo "All tests passed."
