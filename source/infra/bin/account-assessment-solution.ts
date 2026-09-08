// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import * as cdk from 'aws-cdk-lib';
import {DefaultStackSynthesizer, IAspect} from 'aws-cdk-lib';
import {existsSync} from 'fs';
import * as path from 'path';
import 'source-map-support/register';
import * as lambda from "aws-cdk-lib/aws-lambda";
import {AccountAssessmentHubStack, AccountAssessmentHubStackProps} from "../lib/account-assessment-hub-stack";
import {OrgManagementAccountStack} from "../lib/org-management-account-stack";
import {SpokeStack} from "../lib/account-assessment-spoke-stack";
import {IConstruct} from "constructs";
import {CfnPolicy} from "aws-cdk-lib/aws-iam";
import {addCfnSuppressRules} from "@aws-solutions-constructs/core";

const app = new cdk.App();

function getSetting(envVariableName: string, contextName: string, fallback?: string): string {
  const value = process.env[envVariableName] ?? app.node.tryGetContext(contextName) ?? fallback;
  if (value == undefined || value === '') {
    throw new Error(`Missing required setting ${envVariableName} or CDK context ${contextName}`);
  }
  return value;
}

const SOLUTION_VERSION = getSetting('SOLUTION_VERSION', 'solution_version');
const SOLUTION_NAME = getSetting('SOLUTION_NAME', 'solution_name');
const SOLUTION_ID = getSetting('SOLUTION_ID', 'solution_id', 'SO0217');
const SOLUTION_TMN = getSetting(
  'SOLUTION_TRADEMARKEDNAME',
  'solution_trademarked_name',
  'account-assessment-for-aws-organizations'
);
const SOLUTION_PROVIDER = 'AWS Solution Development';
const ASSET_MODE = getSetting('ASSET_MODE', 'asset_mode', 'local').toLowerCase();

if (!['local', 'distribution', 'installer'].includes(ASSET_MODE)) {
  throw new Error(
    `Unsupported ASSET_MODE '${ASSET_MODE}'. Expected 'local', 'distribution', or 'installer'.`
  );
}

const solutionBucketName = ASSET_MODE === 'distribution'
  ? getSetting('DIST_OUTPUT_BUCKET', 'distribution_bucket')
  : undefined;
const localWebUiAssetPath = ASSET_MODE === 'local'
  ? path.resolve(__dirname, '../../../deployment/regional-s3-assets/webui')
  : undefined;

if (localWebUiAssetPath && !existsSync(localWebUiAssetPath)) {
  throw new Error(
    `Local WebUI asset not found at ${localWebUiAssetPath}. Run deployment/build-assets.sh before CDK.`
  );
}

const accountAssessmentHubStackProperties: AccountAssessmentHubStackProps = {
  solutionId: SOLUTION_ID,
  solutionTradeMarkName: SOLUTION_TMN,
  solutionProvider: SOLUTION_PROVIDER,
  solutionBucketName,
  localWebUiAssetPath,
  useInstallerAssets: ASSET_MODE === 'installer',
  solutionName: SOLUTION_NAME,
  solutionVersion: SOLUTION_VERSION,
  description: '(' + SOLUTION_ID + ') - The AWS CloudFormation hub template' +
    ' for deployment of the ' + SOLUTION_NAME + ', Version: ' + SOLUTION_VERSION,
  synthesizer: new DefaultStackSynthesizer({
    generateBootstrapVersionRule: false
  })
}

new AccountAssessmentHubStack(
  app,
  'account-assessment-for-aws-organizations-hub',
  accountAssessmentHubStackProperties
);

new OrgManagementAccountStack(
  app,
  'account-assessment-for-aws-organizations-org-management',
  {
    description: '(' + SOLUTION_ID + 'm) - The AWS CloudFormation org management template' +
      ' for deployment of the ' + SOLUTION_NAME + ', Version: ' + SOLUTION_VERSION,
    synthesizer: new DefaultStackSynthesizer({
      generateBootstrapVersionRule: false
    })
  }
);

new SpokeStack(
  app,
  'account-assessment-for-aws-organizations-spoke',
  {
    description: '(' + SOLUTION_ID + 's) - The AWS CloudFormation spoke template' +
      ' for deployment of the ' + SOLUTION_NAME + ', Version: ' + SOLUTION_VERSION,
    synthesizer: new DefaultStackSynthesizer({
      generateBootstrapVersionRule: false
    })
  }
);

/**
 * Since all lambda functions are traced with xray,
 * and xray:PutTraceSegments requires a policy with resource *,
 * we have to suppress cfn nag warning W12 for every lambda function.
 */
class SuppressCfnNagW12ForLambdaFunctions implements IAspect {
  visit(node: IConstruct): void {
    if (node instanceof lambda.Function) {
      const cfnPolicy = node.node.tryFindChild('ServiceRole')
        ?.node.findChild('DefaultPolicy')
        .node.findChild('Resource') as CfnPolicy;
      cfnPolicy && addCfnSuppressRules(cfnPolicy, [{
        id: 'W12',
        reason: 'Resource * is necessary for xray:PutTraceSegments and xray:PutTelemetryRecords.'
      }]);
    }
  }
}

cdk.Aspects.of(app).add(new SuppressCfnNagW12ForLambdaFunctions());

app.synth();
