#!/usr/bin/env bash
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

set -Eeuo pipefail

deployment_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd "$deployment_dir/.." && pwd -P)"
infra_dir="$repo_root/source/infra"
version="${1:-}"
release_repository="${RELEASE_REPOSITORY:-aws-solutions-library-samples/account-assessment-for-aws-organizations}"

if [[ -z "$version" ]]; then
  echo "Usage: $0 <release-version>" >&2
  exit 2
fi

if [[ ! "$version" =~ ^v?[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "Invalid release version: $version" >&2
  exit 2
fi

# shellcheck disable=SC1091
source "$deployment_dir/solution_config"

export SOLUTION_ID
export SOLUTION_NAME
export SOLUTION_TRADEMARKEDNAME
export SOLUTION_VERSION="$version"
export ASSET_MODE=installer
export NPM_CONFIG_USERCONFIG="$repo_root/.npmrc"

release_dir="$deployment_dir/release"
staging_dir="$(mktemp -d "${TMPDIR:-/tmp}/account-assessment-release.XXXXXX")"
synth_dir="$staging_dir/cdk.out"
payload_dir="$staging_dir/payload"
artifact_prefix="$SOLUTION_TRADEMARKEDNAME/$version"
hub_template_key="$artifact_prefix/templates/$SOLUTION_TRADEMARKEDNAME-hub.template"
payload_name="$SOLUTION_TRADEMARKEDNAME-$version-payload.zip"
installer_name="$SOLUTION_TRADEMARKEDNAME-$version-installer.template"
org_template_name="$SOLUTION_TRADEMARKEDNAME-$version-org-management.template"
spoke_template_name="$SOLUTION_TRADEMARKEDNAME-$version-spoke.template"
payload_path="$release_dir/$payload_name"
installer_path="$release_dir/$installer_name"
org_template_path="$release_dir/$org_template_name"
spoke_template_path="$release_dir/$spoke_template_name"

cleanup() {
  rm -rf "$staging_dir"
}
trap cleanup EXIT

if [[ "${SKIP_ASSET_BUILD:-false}" != "true" ]]; then
  echo "Building release assets"
  "$deployment_dir/build-assets.sh"
fi

if [[ ! -f "$deployment_dir/regional-s3-assets/lambda.zip" ]]; then
  echo "Lambda release asset not found. Run deployment/build-assets.sh." >&2
  exit 1
fi
if [[ ! -d "$deployment_dir/regional-s3-assets/webui" ]]; then
  echo "Web UI release assets not found. Run deployment/build-assets.sh." >&2
  exit 1
fi

echo "Synthesizing GitHub installer templates"
npm --prefix "$infra_dir" ci
npm --prefix "$infra_dir" run build
npm --prefix "$infra_dir" run cdk -- synth '*' --output "$synth_dir"

hub_template_source="$synth_dir/account-assessment-for-aws-organizations-hub.template.json"
org_template_source="$synth_dir/account-assessment-for-aws-organizations-org-management.template.json"
spoke_template_source="$synth_dir/account-assessment-for-aws-organizations-spoke.template.json"
for template_source in \
  "$hub_template_source" \
  "$org_template_source" \
  "$spoke_template_source"; do
  if [[ ! -f "$template_source" ]]; then
    echo "Synthesized template not found: $template_source" >&2
    exit 1
  fi
done

echo "Creating GitHub release payload"
rm -rf "$release_dir"
mkdir -p \
  "$release_dir" \
  "$payload_dir/$artifact_prefix/templates"
cp "$hub_template_source" "$payload_dir/$hub_template_key"
cp "$deployment_dir/regional-s3-assets/lambda.zip" \
  "$payload_dir/$artifact_prefix/lambda.zip"
python3 "$deployment_dir/create-zip.py" \
  "$deployment_dir/regional-s3-assets/webui" \
  "$payload_dir/$artifact_prefix/webui.zip"
python3 "$deployment_dir/create-zip.py" "$payload_dir" "$payload_path"

cp "$org_template_source" "$org_template_path"
cp "$spoke_template_source" "$spoke_template_path"

python3 "$deployment_dir/create-installer-template.py" \
  --installer-code "$deployment_dir/prepackaged/github_release_installer.py" \
  --payload "$payload_path" \
  --release-repository "$release_repository" \
  --release-tag "$version" \
  --payload-name "$payload_name" \
  --hub-template-key "$hub_template_key" \
  --solution-version "$version" \
  --output "$installer_path"

payload_sha256="$(python3 -c \
  'import json, pathlib, sys; print(json.loads(pathlib.Path(sys.argv[1]).read_text())["Resources"]["ReleaseAssets"]["Properties"]["ReleaseSha256"])' \
  "$installer_path")"
printf '%s  %s\n' "$payload_sha256" "$payload_name" > "$payload_path.sha256"

python3 "$deployment_dir/validate-release.py" \
  --installer "$installer_path" \
  --payload "$payload_path" \
  --hub-template-key "$hub_template_key" \
  --org-template "$org_template_path" \
  --spoke-template "$spoke_template_path" \
  --asset-prefix "$artifact_prefix"

echo "Built release artifacts in $release_dir"
