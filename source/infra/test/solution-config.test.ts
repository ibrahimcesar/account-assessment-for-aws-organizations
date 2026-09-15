// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import {mkdtempSync, readFileSync, rmSync, mkdirSync, writeFileSync} from 'fs';
import {tmpdir} from 'os';
import * as path from 'path';
import {readSolutionConfig, SOLUTION_CONFIG_RELATIVE_PATH} from '../lib/solution-config';

const repoRoot = path.resolve(__dirname, '../../..');

function writeConfigFixture(contents: string): string {
  const root = mkdtempSync(path.join(tmpdir(), 'solution-config-'));
  mkdirSync(path.join(root, 'deployment'), {recursive: true});
  writeFileSync(path.join(root, SOLUTION_CONFIG_RELATIVE_PATH), contents);
  return root;
}

test('reads the solution identity and version from the checked-in config', () => {
  const settings = readSolutionConfig(repoRoot);

  expect(settings.SOLUTION_ID).toBe('SO0217');
  expect(settings.SOLUTION_NAME).toBe('Account Assessment for AWS Organizations');
  expect(settings.SOLUTION_TRADEMARKEDNAME).toBe('account-assessment-for-aws-organizations');
  expect(settings.SOLUTION_VERSION).toMatch(/^v\d+\.\d+\.\d+$/);
});

test('parses quoted, unquoted, and commented shell settings', () => {
  const root = writeConfigFixture(
    [
      '# a comment',
      '',
      "SOLUTION_ID='SO0217'",
      'SOLUTION_NAME="Account Assessment for AWS Organizations"',
      'SOLUTION_VERSION=v9.9.9',
      '  SOLUTION_TRADEMARKEDNAME=account-assessment-for-aws-organizations  ',
      'not a setting',
    ].join('\n')
  );

  try {
    expect(readSolutionConfig(root)).toEqual({
      SOLUTION_ID: 'SO0217',
      SOLUTION_NAME: 'Account Assessment for AWS Organizations',
      SOLUTION_VERSION: 'v9.9.9',
      SOLUTION_TRADEMARKEDNAME: 'account-assessment-for-aws-organizations',
    });
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

test('fails loudly when the config is missing rather than silently defaulting', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'solution-config-missing-'));

  try {
    expect(() => readSolutionConfig(root)).toThrow(/Unable to read the solution configuration/);
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});

/*
 * Regression guard. SOLUTION_VERSION reaches the deployed stack as a Lambda
 * environment variable, as the release asset S3 key prefix, and as the Web UI
 * custom resource fingerprint. A second copy in cdk.json would go stale and
 * silently misreport the version, so the identity settings must live only in
 * deployment/solution_config.
 */
test('cdk.json does not duplicate the solution identity or version', () => {
  const cdkJson = JSON.parse(
    readFileSync(path.join(repoRoot, 'source/infra/cdk.json'), 'utf-8')
  );

  for (const key of ['solution_id', 'solution_name', 'solution_trademarked_name', 'solution_version']) {
    expect(cdkJson.context).not.toHaveProperty(key);
  }
});
