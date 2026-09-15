// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import {readFileSync} from 'fs';
import * as path from 'path';

const SETTING_PATTERN = /^([A-Z_][A-Z0-9_]*)=(.*)$/;

export const SOLUTION_CONFIG_RELATIVE_PATH = path.join('deployment', 'solution_config');

/**
 * Reads deployment/solution_config, the single source of truth for the solution
 * id, names, and version. The file is shell syntax so the build scripts can
 * source it directly; this parser understands the subset it uses, which is
 * KEY='value', KEY="value", and KEY=value.
 *
 * Keeping the version here rather than in cdk.json matters because
 * SOLUTION_VERSION reaches the deployed stack: it is set as a Lambda
 * environment variable that feeds the operational metrics payload and the
 * boto3 user agent, it forms the S3 key prefix for the release assets, and it
 * is the Web UI custom resource fingerprint that triggers a redeploy on
 * upgrade. A stale copy would silently misreport the version and skip the Web
 * UI refresh.
 */
export function readSolutionConfig(repoRoot: string): Record<string, string> {
  const configPath = path.join(repoRoot, SOLUTION_CONFIG_RELATIVE_PATH);

  let contents: string;
  try {
    contents = readFileSync(configPath, 'utf-8');
  } catch (error) {
    throw new Error(
      `Unable to read the solution configuration at ${configPath}: ${(error as Error).message}`
    );
  }

  const settings: Record<string, string> = {};
  for (const line of contents.split('\n')) {
    const trimmed = line.trim();
    if (trimmed === '' || trimmed.startsWith('#')) {
      continue;
    }
    const match = SETTING_PATTERN.exec(trimmed);
    if (!match) {
      continue;
    }
    settings[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
  }
  return settings;
}
