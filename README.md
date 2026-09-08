# Account Assessment for AWS Organizations

Account Assessment for AWS Organizations programmatically scans all AWS accounts in an AWS Organization for
identity-based and resource-based policies with Organization-based conditions.

**[🚀Solution Landing Page](https://aws.amazon.com/solutions/implementations/account-assessment-for-aws-organizations)**

_Note:_ For any relevant information outside the scope of this readme, please refer to the solution landing page and
implementation guide.

## Table of content

- [Solution Overview](#solution-overview)
- [Architecture](#architecture)
- [Installation](#installing-from-a-github-release)
- [Customization](#customization)
  - [Setup](#setup)
  - [File Structure](#file-structure)
  - [Unit Test](#unit-test)
  - [Build](#build)
  - [Deploy from source](#deploy-from-source)
  - [Faster development cycles](#faster-development-cycles)
- [License](#License)

## Solution Overview

## Architecture

The default prepackaged deployment deploys the following infrastructure in your account.

<img src="./docs/architecture.png" alt="architecture diagram">

## Installing from a GitHub release

Each GitHub release includes a small CloudFormation installer template and a checksummed release payload. Deployment
users do not need Docker, Node.js, npm, GNU Make, the AWS CLI, or a source checkout.

Requirements:

- Permission to create CloudFormation stacks and the solution resources in each target account
- Outbound access from AWS Lambda to GitHub during installation

To deploy the hub:

1. Download `account-assessment-for-aws-organizations-<VERSION>-installer.template` from the GitHub release.
2. In the hub account and Region, open AWS CloudFormation and choose **Create stack**.
3. Upload the installer template, provide the namespace and initial user email, choose whether to send anonymized
   operational metrics, and acknowledge named IAM resources.
4. Create the stack.

The installer downloads the matching payload from the same GitHub release, verifies its embedded SHA-256 checksum,
stages it in a private bucket created in the hub account, and deploys the hub as a nested stack. No public or
maintainer-managed deployment bucket is used.

The Web UI deployment discovers the organization ID through AWS Organizations, and the solution discovers the
management account ID at runtime. Neither value is a deployment parameter.

The release also includes standalone organization-management and spoke templates. Upload those templates through
CloudFormation in the corresponding accounts, provide the hub account ID and the same deployment namespace, and
acknowledge named IAM resources. Deploy the spoke template in every account that the solution will assess.

The application continues to use its own S3 bucket for Web UI hosting. The installer staging bucket is private,
account-local, and deleted with the installer stack.

To upgrade, update the installer stack with the template from the new GitHub release, then update the
organization-management and spoke stacks with their matching templates. To uninstall the hub, delete the installer
stack; CloudFormation removes the nested hub and then empties and deletes the staging bucket.

***

## Customization

### Setup

This section is for maintainers building the solution from source. Deployment users should use the prepackaged
release bundle above.

The source build path requires:

- Docker with Linux AMD64 container support
- GNU Make
- AWS credentials when running deployment commands

Node.js 22, Python 3.12, Poetry, the Poetry export plugin, and AWS CDK are pinned inside the repository build image.
Repository npm commands also ignore user-level registry configuration and use the public npm registry.

### File Structure

```text
├── Dockerfile                         - pinned build and test toolchain
├── Makefile                           - build, test, synth, and deploy entry points
├── deployment/
│   ├── build-assets.sh                - builds the WebUI and Lambda deployment assets
│   ├── build-lambdas.sh               - creates the Linux/x86_64 Lambda package
│   ├── build-s3-dist.sh               - optional legacy CloudFormation distribution builder
│   ├── cdk.sh                         - builds assets and runs the local CDK application
│   ├── package-release.sh             - creates GitHub release deployment artifacts
│   ├── create-installer-template.py   - generates the CloudFormation installer
│   ├── validate-release.py            - validates generated release artifacts
│   ├── prepackaged/                   - inline installer and release documentation
│   ├── cdk-solution-helper/           - converts templates for the legacy distribution format
│   └── manifest-generator/            - creates the WebUI deployment manifest
└── source/
    ├── infra/                         - AWS CDK application and tests
    ├── lambda/                        - Python Lambda source and tests
    ├── webui/                         - React/Vite WebUI and tests
    └── run-all-tests.sh               - complete test suite
```

### Unit Test

Run all infrastructure, distribution-helper, WebUI, and Lambda tests in the pinned build environment:

```shell
make test
```

### Build

Build every local deployment asset:

```shell
make build
```

The command produces:

- `deployment/regional-s3-assets/lambda.zip`
- `deployment/regional-s3-assets/webui/`

Generate a deployable CDK cloud assembly, including its local assets:

```shell
make synth
```

The cloud assembly is written to `deployment/cdk.out/`.

Generate the artifacts attached to a GitHub release:

```shell
make package VERSION=v1.1.14
```

The release directory contains:

- The hub installer CloudFormation template
- The checksummed GitHub release payload
- The organization-management CloudFormation template
- The spoke CloudFormation template

### Deploy from source

The normal deployment path does not require a user-created distribution bucket and does not require manual
`aws s3 cp` commands. CDK synthesizes the CloudFormation stacks and publishes temporary assets through the
CDK bootstrap resources. The solution still creates and uses its own S3 bucket for WebUI hosting.

Before the first deployment to each account and Region, bootstrap CDK:

```shell
make cdk CDK_ARGS="bootstrap aws://<ACCOUNT_ID>/<REGION> --profile <PROFILE>"
```

In the AWS Organizations management account, enable Resource Access Manager sharing with the organization.

Deploy the hub stack:

```shell
make deploy \
  STACK=account-assessment-for-aws-organizations-hub \
  CDK_ARGS="--profile <PROFILE_HUB> \
    --parameters DeploymentNamespace=<NAMESPACE> \
    --parameters UserEmail=<EMAIL> \
    --parameters AllowListedIPRanges=<IP_RANGES>"
```

Deploy the organization-management stack:

```shell
make deploy \
  STACK=account-assessment-for-aws-organizations-org-management \
  CDK_ARGS="--profile <PROFILE_ORG_MGMT> \
    --parameters DeploymentNamespace=<NAMESPACE> \
    --parameters HubAccountId=<HUB_ACCOUNT_ID>"
```

Deploy the spoke stack in every account that the solution will assess:

```shell
make deploy \
  STACK=account-assessment-for-aws-organizations-spoke \
  CDK_ARGS="--profile <PROFILE_SPOKE> \
    --parameters DeploymentNamespace=<NAMESPACE> \
    --parameters HubAccountId=<HUB_ACCOUNT_ID>"
```

The same `DeploymentNamespace` must be used for all three stacks.

### Legacy distribution artifacts

Maintainers who need the historical AWS Solutions layout can still generate `global-s3-assets/` and
`regional-s3-assets/`:

```shell
make distribution DIST_BUCKET=<BUCKET_BASE_NAME> VERSION=v1.1.13
```

This publication path is separate from both the GitHub installer and the direct-CDK deployment paths.

### Faster development cycles

`make deploy` rebuilds all assets by default. After a successful `make build`, infrastructure-only changes can skip
that rebuild:

```shell
SKIP_ASSET_BUILD=true make deploy STACK=<STACK_NAME> CDK_ARGS="<CDK_ARGUMENTS>"
```

***

## Data Collection

This solution sends operational metrics to AWS (the “Data”) about the use of this solution. We use this Data to better understand how customers use this solution and related services and products. AWS’s collection of this Data is subject to the [AWS Privacy Notice](https://aws.amazon.com/privacy/).

***

## License

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

Licensed under the Apache License Version 2.0 (the "License"). You may not use this file except in compliance with the
License. A copy of the License is located at

    http://www.apache.org/licenses/

or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions and
limitations under the License.
