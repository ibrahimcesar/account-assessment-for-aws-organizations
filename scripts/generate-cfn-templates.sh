#!/usr/bin/env bash
# Synthesize CloudFormation templates from the CDK source and write them to
# deployment/cfn-templates/ so they can be committed and deployed directly
# without a staging S3 bucket.
#
# Usage:
#   ./scripts/generate-cfn-templates.sh           # from repo root
#   Called automatically by .githooks/pre-commit  # when CDK source changes

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="$REPO_ROOT/source/infra"
LAMBDA_ZIP="$REPO_ROOT/deployment/regional-s3-assets/lambda.zip"
OUTPUT_DIR="$REPO_ROOT/deployment/cfn-templates"

# ---------------------------------------------------------------------------
# Validate prerequisites
# ---------------------------------------------------------------------------
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is required but not found in PATH." >&2
  exit 1
fi

if [ ! -d "$INFRA_DIR/node_modules" ]; then
  echo "INFO: node_modules not found — running npm install in $INFRA_DIR"
  npm install --prefix "$INFRA_DIR" --silent
fi

# Lambda zip must exist so CDK can reference the asset path. If it is absent
# we create an empty placeholder so synth succeeds; a real build is still
# required before actually deploying.
if [ ! -f "$LAMBDA_ZIP" ]; then
  echo "WARNING: $LAMBDA_ZIP not found — creating empty placeholder for synth."
  mkdir -p "$(dirname "$LAMBDA_ZIP")"
  # CDK uses fromAsset which requires a non-empty zip
  echo "placeholder" | zip -q - > "$LAMBDA_ZIP"
fi

# ---------------------------------------------------------------------------
# Synthesize
# ---------------------------------------------------------------------------
mkdir -p "$OUTPUT_DIR"

echo "Synthesizing CDK stacks..."

# Stacks require several env vars that the build pipeline normally injects.
# Provide sensible defaults for local/hook runs; values are only embedded in
# metadata and do not affect the resource definitions.
export SOLUTION_ID="${SOLUTION_ID:-SO0217}"
export SOLUTION_VERSION="${SOLUTION_VERSION:-v0.0.0-local}"
export SOLUTION_NAME="${SOLUTION_NAME:-Account Assessment for AWS Organizations}"
export SOLUTION_TRADEMARKEDNAME="${SOLUTION_TRADEMARKEDNAME:-account-assessment-for-aws-organizations}"
export DIST_OUTPUT_BUCKET="${DIST_OUTPUT_BUCKET:-local-build}"

cd "$INFRA_DIR"

# Build TypeScript first so cdk synth sees up-to-date JS
npm run build --silent

# Synth all stacks into a temp directory, then copy .template.json files out
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT

./node_modules/.bin/cdk synth '*' --output "$STAGING_DIR" --quiet 2>/dev/null || \
  ./node_modules/.bin/cdk synth '*' --output "$STAGING_DIR"

# Copy and rename *.template.json → *.template
for f in "$STAGING_DIR"/*.template.json; do
  [ -f "$f" ] || continue
  base="$(basename "$f" .template.json)"
  dest="$OUTPUT_DIR/${base}.template"
  cp "$f" "$dest"
  echo "  wrote $dest"
done

echo "Done. Templates are in $OUTPUT_DIR/"
