#!/usr/bin/env bash
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
#

set -Eeuo pipefail
[[ "${DEBUG:-false}" == "true" ]] && set -x

deployment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$deployment_dir/.." && pwd -P)"
lambda_source_dir="$repo_root/source/lambda"
build_output_dir="${BUILD_OUTPUT_DIR:-$deployment_dir/regional-s3-assets}"
staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/account-assessment-lambda.XXXXXX")"
package_dir="$staging_dir/lambda"
requirements_file="$staging_dir/requirements.txt"
lambda_zip="$build_output_dir/lambda.zip"

cleanup() {
  rm -rf "$staging_dir"
}
trap cleanup EXIT

for command_name in poetry python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
done

python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$python_version" != "3.12" ]]; then
  echo "Python 3.12 is required to package the Lambda functions; found $python_version." >&2
  exit 1
fi

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "Lambda assets must be built on Linux/x86_64. Run 'make build' to use the pinned container." >&2
  exit 1
fi

echo "Exporting locked Lambda dependencies"
(
  cd "$lambda_source_dir"
  poetry export \
    --only main \
    --format requirements.txt \
    --output "$requirements_file" \
    --without-hashes
)

echo "Staging Lambda source"
mkdir -p "$package_dir" "$build_output_dir"
cp -R "$lambda_source_dir/." "$package_dir/"
rm -rf \
  "$package_dir/.venv" \
  "$package_dir/.venv-test" \
  "$package_dir/coverage" \
  "$package_dir/tests"
rm -f \
  "$package_dir/.coveragerc" \
  "$package_dir/coverage.xml" \
  "$package_dir/poetry.lock" \
  "$package_dir/pyproject.toml"

echo "Installing Lambda runtime dependencies"
python3 -m pip install \
  --requirement "$requirements_file" \
  --target "$package_dir" \
  --upgrade \
  --no-compile

find "$package_dir" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$package_dir" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

echo "Creating deterministic Lambda archive"
rm -f "$lambda_zip"
python3 "$deployment_dir/create-zip.py" \
  "$package_dir" \
  "$lambda_zip" \
  --max-uncompressed-mib 250

echo "Built $lambda_zip"
