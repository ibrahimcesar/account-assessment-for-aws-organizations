// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import {Construct} from "constructs";
import * as cdk from "aws-cdk-lib";
import {CustomResource} from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import {Code, Runtime} from "aws-cdk-lib/aws-lambda";
import {CognitoAuthenticationResources} from "./cognito-authenticator";
import {Bucket, IBucket} from "aws-cdk-lib/aws-s3";
import {Distribution} from "aws-cdk-lib/aws-cloudfront";
import {Asset} from "aws-cdk-lib/aws-s3-assets";
import {PolicyStatement} from "aws-cdk-lib/aws-iam";

type WebUIDeployerProps = {
  region: string,
  apiGatewayUrl: string,
  deploymentBucket: IBucket,
  cloudFront: Distribution,
  auth: CognitoAuthenticationResources,
  deploymentSourceBucket?: IBucket,
  deploymentSourceBucketName?: string,
  deploymentSourcePath?: string,
  deploymentSourceType?: 'archive' | 'prefix',
  localWebUiAssetPath?: string,
  assetCode: Code,
  solutionVersion: string,
  stackId: string,
  sendAnonymousData: string
};

export class WebUIDeployer extends Construct {

  constructor(scope: Construct, id: string, {
    region,
    apiGatewayUrl,
    deploymentBucket,
    cloudFront,
    auth,
    deploymentSourceBucket: providedDeploymentSourceBucket,
    deploymentSourceBucketName,
    deploymentSourcePath,
    deploymentSourceType,
    localWebUiAssetPath,
    assetCode,
    solutionVersion,
    stackId,
    sendAnonymousData
  }: WebUIDeployerProps) {
    super(scope, id);

    let deploymentSourceBucket: IBucket;
    let sourceBucketName: string;
    let sourcePath: string;
    let sourceType: 'archive' | 'prefix';
    let sourceFingerprint: string;

    if (localWebUiAssetPath) {
      const webUiAsset = new Asset(this, 'LocalWebUIAsset', {
        path: localWebUiAssetPath
      });
      deploymentSourceBucket = webUiAsset.bucket;
      sourceBucketName = webUiAsset.s3BucketName;
      sourcePath = webUiAsset.s3ObjectKey;
      sourceType = 'archive';
      sourceFingerprint = webUiAsset.assetHash;
    } else if (providedDeploymentSourceBucket && deploymentSourcePath) {
      deploymentSourceBucket = providedDeploymentSourceBucket;
      sourceBucketName = deploymentSourceBucket.bucketName;
      sourcePath = deploymentSourcePath;
      sourceType = deploymentSourceType ?? 'prefix';
      sourceFingerprint = solutionVersion;
    } else if (deploymentSourceBucketName && deploymentSourcePath) {
      deploymentSourceBucket = Bucket.fromBucketAttributes(this, 'SolutionRegionalBucket', {
        bucketName: deploymentSourceBucketName + '-' + region
      });
      sourceBucketName = deploymentSourceBucket.bucketName;
      sourcePath = deploymentSourcePath;
      sourceType = 'prefix';
      sourceFingerprint = solutionVersion;
    } else {
      throw new Error(
        'WebUI deployment requires either localWebUiAssetPath or distribution bucket configuration.'
      );
    }

    const webuiAmplifyConfig = {
      API: {
        endpoints: [
          {
            name: "AccountAssessmentApi",
            endpoint: apiGatewayUrl
          }
        ]
      },
      loggingLevel: 'INFO',
      Auth: {
        region: region,
        userPoolId: auth.userPool.userPoolId,
        userPoolWebClientId: auth.userPoolClient.userPoolClientId,
        mandatorySignIn: true,
        oauth: {
          domain: auth.oauthDomain,
          scope: ["openid", "profile", "email", "aws.cognito.signin.user.admin", "account-assessment-api/api"],
          redirectSignIn: `https://${cloudFront.distributionDomainName}/`,
          redirectSignOut: `https://${cloudFront.distributionDomainName}/`,
          responseType: "code",
          clientId: auth.userPoolClient.userPoolClientId,
        }
      }
    };
    const webUiDeploymentConfig = {
      SourceType: sourceType,
      SrcBucket: sourceBucketName,
      SrcPath: sourcePath,
      WebUIBucket: deploymentBucket.bucketName,
      awsExports: webuiAmplifyConfig
    };

    const webUIDeploymentFunction = new lambda.Function(this, 'DeployWebUI', {
      runtime: Runtime.PYTHON_3_12,
      tracing: lambda.Tracing.ACTIVE,
      code: assetCode,
      handler: 'deploy_webui/deploy_webui.lambda_handler',
      timeout: cdk.Duration.minutes(5),
      environment: {
        LOG_LEVEL: 'INFO',
        CONFIG: JSON.stringify(webUiDeploymentConfig),
        POWERTOOLS_SERVICE_NAME: 'DeployWebUI',
        SOLUTION_VERSION: solutionVersion,
        STACK_ID: stackId,
        SEND_ANONYMOUS_DATA: sendAnonymousData
      }
    });
    deploymentBucket.grantPut(webUIDeploymentFunction);
    deploymentSourceBucket.grantRead(webUIDeploymentFunction);
    webUIDeploymentFunction.addToRolePolicy(new PolicyStatement({
      actions: ['organizations:DescribeOrganization'],
      resources: ['*']
    }));

    new CustomResource(this, 'WebUIDeploymentResource', {
      serviceToken: webUIDeploymentFunction.functionArn,
      serviceTimeout: cdk.Duration.minutes(5),
      properties:{
        SolutionVersion: solutionVersion,
        SourceFingerprint: sourceFingerprint
      }
    });
  }

}
