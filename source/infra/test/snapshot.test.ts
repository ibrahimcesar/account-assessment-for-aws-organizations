// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import '@aws-cdk/assert/jest';
import {App} from 'aws-cdk-lib';
import {AccountAssessmentHubStack, AccountAssessmentHubStackProps} from "../lib/account-assessment-hub-stack";
import {Template} from "aws-cdk-lib/assertions";
import {existsSync} from "fs";
import {mkdirSync, rmSync, writeFileSync} from "node:fs";
import * as path from "node:path";
import {OrgManagementAccountStack} from "../lib/org-management-account-stack";
import {SpokeStack} from "../lib/account-assessment-spoke-stack";


export const props: AccountAssessmentHubStackProps = {
  solutionBucketName: 'solutions',
  solutionId: 'SO0217',
  solutionName: 'account-assessment-for-aws-organizations',
  solutionProvider: 'AWS Solutions',
  solutionTradeMarkName: 'account-assessment-for-aws-organizations',
  solutionVersion: 'v1.0.0'
};

const lambdaAssetPath = path.resolve(
  __dirname,
  '../../../deployment/regional-s3-assets/lambda.zip'
);
let createdMockLambdaAsset = false;

beforeAll(() => {
  if (!existsSync(lambdaAssetPath)) {
    mkdirSync(path.dirname(lambdaAssetPath), {recursive: true});
    writeFileSync(lambdaAssetPath, '');
    createdMockLambdaAsset = true;
  }
});

afterAll(() => {
  if (createdMockLambdaAsset) {
    rmSync(lambdaAssetPath, {force: true});
  }
});

/*
 * Regression test.
 * Compares the synthesized cfn template from the cdk project with the snapshot in git.
 *
 * Only update the snapshot after making sure that the differences are intended. (Deployment and extensive manual testing)
 */
test('hub stack synth doesnt crash', () => {
  // GIVEN
  const app = new App();

  // WHEN
  const stack = new AccountAssessmentHubStack(
    app,
    'AccountAssessment-HubStack',
    props
  );
  const template = Template.fromStack(stack).toJSON();
  overwriteS3Keys(template);

  // THEN
  expect(template).toMatchSnapshot();
});

test('org management stack synth doesnt crash', () => {
  // GIVEN
  const app = new App();

  // WHEN
  const stack = new OrgManagementAccountStack(
    app,
    'AccountAssessment-OrgMgmtStack',
    props
  );
  const template = Template.fromStack(stack);

  // THEN
  expect(template).toMatchSnapshot();
});

test('spoke stack synth doesnt crash', () => {
  // GIVEN
  const app = new App();

  // WHEN
  const stack = new SpokeStack(
    app,
    'AccountAssessment-SpokeStack',
    props
  );
  const template = Template.fromStack(stack);

  // THEN
  expect(template).toMatchSnapshot();
});

test('installer hub stack reads release assets from the provided bucket', () => {
  // GIVEN
  const app = new App();

  // WHEN
  const stack = new AccountAssessmentHubStack(
    app,
    'AccountAssessment-InstallerHubStack',
    {
      ...props,
      solutionBucketName: undefined,
      useInstallerAssets: true
    }
  );
  const template = Template.fromStack(stack);

  // THEN
  template.hasParameter('AssetBucketName', {
    Description: 'Name of the private S3 bucket containing the GitHub release assets.',
    Type: 'String'
  });
  template.hasParameter('SendAnonymousData', {
    AllowedValues: ['Yes', 'No'],
    Default: 'Yes',
    Description: 'Send anonymized operational metrics to AWS.',
    Type: 'String'
  });
  template.hasResourceProperties('AWS::Lambda::Function', {
    Code: {
      S3Bucket: {Ref: 'AssetBucketName'},
      S3Key: 'account-assessment-for-aws-organizations/v1.0.0/lambda.zip'
    }
  });
  expect(JSON.stringify(template.toJSON())).toContain(
    'account-assessment-for-aws-organizations/v1.0.0/webui.zip'
  );
});


function overwriteS3Keys(obj: any, value: string = 'foo.zip'): void {
  if (Array.isArray(obj)) {
    obj.forEach(element => {
      if (typeof element === "object" && element !== null) {
        overwriteS3Keys(element, value);
      }
    });
  } else if (typeof obj === "object" && obj !== null) {
    Object.keys(obj).forEach(key => {
      if (key === "S3Key") {
        obj[key] = value;
      } else if (typeof obj[key] === "object" && obj[key] !== null) {
        overwriteS3Keys(obj[key], value);
      }
    });
  }
}
