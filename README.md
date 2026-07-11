# Guidance for Account Assessment for AWS Organizations

Account Assessment for AWS Organizations programmatically scans all AWS accounts in an AWS Organization for identity-based and resource-based policies with Organization-based conditions.

## Table of Contents

- [Guidance for Account Assessment for AWS Organizations](#guidance-for-account-assessment-for-aws-organizations)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
    - [Cost](#cost)
      - [Sample Cost Table](#sample-cost-table)
  - [Prerequisites](#prerequisites)
    - [Operating System](#operating-system)
    - [AWS account requirements](#aws-account-requirements)
    - [Supported Regions](#supported-regions)
  - [Deployment Steps](#deployment-steps)
  - [Deployment Validation](#deployment-validation)
  - [Running the Guidance](#running-the-guidance)
  - [Next Steps](#next-steps)
  - [Cleanup](#cleanup)
  - [FAQ, known issues, additional considerations, and limitations](#faq-known-issues-additional-considerations-and-limitations)
    - [Known issues](#known-issues)
    - [Additional considerations](#additional-considerations)
  - [Revisions](#revisions)
  - [Notices](#notices)
  - [Authors](#authors)

## Overview

This Guidance helps AWS Organizations customers identify accounts and policies that use
[Organization-based conditions](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-organization)
(`aws:PrincipalOrgID`, `aws:PrincipalOrgPaths`, `aws:ResourceOrgID`, etc.) in their IAM and resource-based policies.
Because these conditions tie access decisions to organizational membership, it is critical to understand their scope
before restructuring an Organization, migrating accounts, or conducting a security audit.

The Guidance deploys a **hub-and-spoke** architecture:

- The **hub stack** hosts a web UI (served via Amazon CloudFront), a REST API (Amazon API Gateway), authentication
  (Amazon Cognito), and coordination logic (AWS Lambda + AWS Step Functions backed by Amazon DynamoDB).
- One or more **spoke stacks** are deployed to every account you want to scan. Each spoke stack grants the hub the
  cross-account permissions it needs to read policies in that account.
- An optional **Org Management account stack** enables scans of AWS Organizations metadata (Trusted Access,
  Delegated Administrators).

Scan results are surfaced in the web UI and stored in DynamoDB for further analysis.

![Architecture diagram](docs/architecture.png)

**Architecture flow:**

1. The client browser requests the web interface from Amazon CloudFront.
2. CloudFront serves the static web interface from an Amazon S3 bucket.
3. The client authenticates with Amazon Cognito.
4. Authenticated API requests pass through AWS WAF for IP-based access control.
5. AWS WAF forwards allowed requests to Amazon API Gateway.
6. Amazon Cognito authorizes the API Gateway request.
7. API Gateway invokes AWS Lambda to process the request.
8. Lambda reads from and writes job state to Amazon DynamoDB.
9. Lambda calls AWS Organizations in the Management account to retrieve organization metadata (accounts, OUs, and organization structure).
10. Amazon EventBridge triggers scheduled Lambda invocations for recurring assessments.
11. Lambda starts an AWS Step Functions state machine to orchestrate the assessment.
12. Step Functions invokes spoke-account AWS Lambda functions for each target account.
13. Spoke-account Lambda assumes a cross-account IAM role to read policies (S3 bucket policies, IAM policies, SNS topic policies, and other service policies) in each spoke account.
14. Spoke-account Lambda writes findings back to Amazon DynamoDB in the hub account.

### Cost

You are responsible for the cost of the AWS services used while running this Guidance. As of July 2026, the cost for
running this Guidance with the default settings in the US East (N. Virginia) Region is approximately **$11 per
month** for an AWS Organization with up to 50 accounts and 30 daily scans.

We recommend creating a [Budget](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
through [AWS Cost Explorer](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/) to help manage costs.
Prices are subject to change. For full details, refer to the pricing webpage for each AWS service used in this Guidance.

#### Sample Cost Table

The following table provides a sample cost breakdown for deploying this Guidance with default parameters in the
US East (N. Virginia) Region for one month (50 accounts, 30 scans per month).

| AWS Service | Dimensions | Cost [USD] |
| --- | --- | --- |
| Amazon API Gateway | 50,000 REST API calls per month | $0.18 |
| AWS Lambda | 500,000 invocations, avg 2 s, 256 MB | $1.25 |
| AWS Step Functions | 60 executions × 500 state transitions | $0.75 |
| Amazon DynamoDB | On-demand, ~1 GB storage, 10 M read/write units | $2.50 |
| Amazon Cognito | Up to 50 monthly active users | $0.00 |
| Amazon CloudFront | 1 GB data transfer + 100,000 requests | $0.10 |
| Amazon S3 | 1 GB storage (WebUI assets) | $0.02 |
| AWS WAF | 1 web ACL + 50,000 requests | $6.00 |
| **Total estimate** | | **~$10.80 / month** |

## Prerequisites

### Operating System

These deployment instructions work on **macOS, Linux, or Windows** with the AWS CLI installed.

| Tool | Minimum version | Install |
| --- | --- | --- |
| AWS CLI | 2.x | [aws.amazon.com/cli](https://aws.amazon.com/cli/) |
| Git | 2.x | [git-scm.com](https://git-scm.com/) |

### AWS account requirements

- An active [AWS Organizations](https://aws.amazon.com/organizations/) with at least one management account.
- AWS CLI configured with credentials for the hub account, each spoke account you want to scan, and optionally
  the Org Management account. The deploying IAM principal must have permissions to create IAM roles, Lambda
  functions, DynamoDB tables, API Gateway, Cognito User Pools, CloudFront distributions, and S3 buckets.
- In your **Org Management Account**, enable Resource Access Manager sharing with the AWS Organization before
  deployment: *AWS Console → Resource Access Manager → Settings → Enable sharing with AWS Organizations*.

### Supported Regions

This Guidance can be deployed in any AWS Region that supports all of the following services: Amazon API Gateway,
AWS Lambda, Amazon DynamoDB, Amazon Cognito, Amazon CloudFront, Amazon S3, AWS Step Functions, and AWS WAF.

## Deployment Steps

The pre-built CloudFormation templates are included in the repository under `deployment/cfn-templates/`.
No build tools are required.

Throughout these steps, `--profile` refers to a named AWS CLI profile in your `~/.aws/config` file that provides
credentials for the target account. Replace `<PROFILE_HUB>`, `<PROFILE_SPOKE>`, and `<PROFILE_ORG_MGMT>` with the
profile names configured for each respective account. If you use a single default profile or environment variable
credentials, you can omit the `--profile` flag entirely.

The following parameter values are shared across all three stacks:

| Parameter | Description |
| --- | --- |
| `DeploymentNamespace` | Short prefix (3–10 lowercase alphanumeric chars, no leading/trailing hyphen) — must be the same value in all stacks |
| `UserEmail` | Email address for the initial Cognito admin user (hub stack only) |
| `AllowListedIPRanges` | Comma-separated CIDR blocks allowed to access the API. Use `0.0.0.0/1,128.0.0.0/1` to allow all IPs (hub stack only) |
| `OrganizationID` | Your AWS Organizations ID, format `o-xxxxxxxxxx` (hub stack only) |
| `HubAccountId` | AWS account ID where the hub stack is deployed (spoke and org-mgmt stacks only) |

1. **Deploy the hub stack**

   **Option A — AWS Console** (no CLI or cloning required):
   1. Download [account-assessment-for-aws-organizations-hub.template](deployment/cfn-templates/account-assessment-for-aws-organizations-hub.template) from this repository.
   2. Sign in to the hub account and open the [CloudFormation console](https://console.aws.amazon.com/cloudformation).
   3. Choose **Create stack → With new resources**.
   4. Upload the downloaded template file.
   5. Fill in the parameter values from the table above and complete the wizard.
   6. Acknowledge the IAM capabilities checkbox and choose **Create stack**.

   **Option B — AWS CLI:**

   ```bash
   git clone https://github.com/aws-solutions/account-assessment-for-aws-organizations.git
   cd account-assessment-for-aws-organizations
   ```

   ```bash
   aws cloudformation deploy \
     --template-file deployment/cfn-templates/account-assessment-for-aws-organizations-hub.template \
     --stack-name account-assessment-for-aws-organizations-hub \
     --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
     --parameter-overrides \
         DeploymentNamespace=<NAMESPACE> \
         UserEmail=<EMAIL> \
         AllowListedIPRanges=<IP-RANGES> \
         OrganizationID=<ORG_ID> \
     --profile <PROFILE_HUB>
   ```

2. **Deploy the spoke stack to all target accounts**

   The spoke stack must be deployed to every account you want to scan. AWS CloudFormation StackSets is the
   recommended approach for deploying to multiple accounts at once, especially for large organizations.

   **Option A — AWS Console (StackSet, recommended for multiple accounts):**
   1. Download [account-assessment-for-aws-organizations-spoke.template](deployment/cfn-templates/account-assessment-for-aws-organizations-spoke.template) from this repository.
   2. In the **Org Management account** (or a delegated administrator account), open the
      [CloudFormation console](https://console.aws.amazon.com/cloudformation) and choose **StackSets → Create StackSet**.
   3. Upload the downloaded template file.
   4. Set `DeploymentNamespace` to the same value used for the hub stack, and `HubAccountId` to the hub account ID.
   5. Choose **Service-managed permissions** to automatically deploy to all current and future accounts in selected
      OUs, or **Self-managed permissions** to target specific account IDs.
   6. Select the target OUs or accounts and Regions, then complete the wizard.

   **Option B — AWS Console (single account):**
   Repeat the same single-stack console steps from step 1 in each spoke account, uploading
   `deployment/cfn-templates/account-assessment-for-aws-organizations-spoke.template`.

   **Option C — AWS CLI (single account):**

   ```bash
   aws cloudformation deploy \
     --template-file deployment/cfn-templates/account-assessment-for-aws-organizations-spoke.template \
     --stack-name account-assessment-for-aws-organizations-spoke \
     --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
     --parameter-overrides \
         DeploymentNamespace=<NAMESPACE> \
         HubAccountId=<HUB_ACCOUNT_ID> \
     --profile <PROFILE_SPOKE>
   ```

3. **Deploy the Org Management account stack** (optional — enables Trusted Access and Delegated Admin scans)

   **Option A — AWS Console:** repeat the same console steps in the Org Management account, uploading
   `deployment/cfn-templates/account-assessment-for-aws-organizations-org-management.template`.

   **Option B — AWS CLI:**

   ```bash
   aws cloudformation deploy \
     --template-file deployment/cfn-templates/account-assessment-for-aws-organizations-org-management.template \
     --stack-name account-assessment-for-aws-organizations-org-management \
     --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
     --parameter-overrides \
         DeploymentNamespace=<NAMESPACE> \
         HubAccountId=<HUB_ACCOUNT_ID> \
     --profile <PROFILE_ORG_MGMT>
   ```

## Contributing / Customization

If you are modifying the source code, the following tools are required to rebuild the CloudFormation templates.

### Developer prerequisites

| Tool | Minimum version | Install |
| --- | --- | --- |
| Node.js | 22.x | [nodejs.org](https://nodejs.org/) |
| Python | 3.12 | [python.org](https://www.python.org/) |
| Poetry v2 | 2.x | `pip install poetry && poetry self add poetry-plugin-export` |
| AWS CDK | 2.1021.0 | `npm install -g aws-cdk` |
| AWS CLI | 2.x | [aws.amazon.com/cli](https://aws.amazon.com/cli/) |

### Set up the development environment

```bash
# Install git hooks — regenerates cfn-templates/ automatically on commit
chmod +x scripts/setup-hooks.sh && ./scripts/setup-hooks.sh

# Install dependencies
cd source/infra && npm install && cd ../..
cd source/webui && npm install && cd ../..
```

### Rebuild assets and templates

```bash
# Build Lambda zip
cd deployment && ./build-lambdas.sh && cd ..

# Build WebUI
cd source/webui
GENERATE_SOURCEMAP=false INLINE_RUNTIME_CHUNK=false npm run build
mv dist webui && mv webui ../../deployment/regional-s3-assets/
cd ../..

# Regenerate CloudFormation templates (also triggered automatically by the pre-commit hook)
./scripts/generate-cfn-templates.sh
```

### Run unit tests

```bash
cd source && chmod +x run-all-tests.sh && ./run-all-tests.sh && cd ..
```

## Deployment Validation

1. Open the [AWS CloudFormation console](https://console.aws.amazon.com/cloudformation) in the hub account and
   verify that the stack `account-assessment-for-aws-organizations-hub` shows status `CREATE_COMPLETE`.

2. Verify hub stack outputs via the CLI:

   ```bash
   aws cloudformation describe-stacks \
     --stack-name account-assessment-for-aws-organizations-hub \
     --query "Stacks[0].Outputs" \
     --profile <PROFILE_HUB>
   ```

   You should see output keys for the CloudFront distribution URL and the Cognito User Pool ID.

3. Verify each spoke stack:

   ```bash
   aws cloudformation describe-stacks \
     --stack-name account-assessment-for-aws-organizations-spoke \
     --query "Stacks[0].StackStatus" \
     --output text \
     --profile <PROFILE_SPOKE>
   ```

   Expected output: `CREATE_COMPLETE`

4. Confirm you received a Cognito welcome email with temporary credentials at the `UserEmail` address you provided.

## Running the Guidance

1. Retrieve the Web UI URL from the hub stack outputs:

   ```bash
   aws cloudformation describe-stacks \
     --stack-name account-assessment-for-aws-organizations-hub \
     --query "Stacks[0].Outputs[?OutputKey=='WebUIUrl'].OutputValue" \
     --output text \
     --profile <PROFILE_HUB>
   ```

2. Open the URL in a browser. Sign in with the email address and temporary password from the Cognito welcome email.
   You will be prompted to set a new password on first login.

3. In the Web UI choose **New Assessment** and select the scan types to run:

   | Scan type | What it finds |
   | --- | --- |
   | **Trusted Access** | AWS services with Trusted Access enabled in your Organization |
   | **Delegated Administrators** | Accounts registered as delegated admins for AWS services |
   | **Resource-Based Policies** | Supported AWS services with Organization-based conditions in resource policies |
   | **Policy Explorer** | Broad scan of IAM and resource policies across all scoped accounts |

4. Choose **Start** to begin the scan. A 50-account Organization typically completes in under 10 minutes.

5. When the scan completes, results appear in the Web UI. Each finding shows the account, service, resource ARN,
   and the policy statement containing the Organization-based condition.

6. Use the **Export** button to download findings as a CSV for further analysis.

## Next Steps

- **Schedule recurring scans** — integrate the API with an Amazon EventBridge Scheduler rule to run assessments
  automatically (e.g., daily or weekly).
- **Add more spoke accounts** — re-run deployment step 8 for any account added to your Organization.
- **Restrict the IP allowlist** — update `AllowListedIPRanges` to your corporate IP ranges instead of the
  open default.
- **Enforce MFA** — set the `MultiFactorAuthentication` CloudFormation parameter to `ON` to require MFA for all
  Cognito users.
- **Integrate findings into a SIEM** — enable DynamoDB Streams on the findings table and fan out to Amazon Kinesis
  or Amazon EventBridge for downstream ingestion.
- **Automate remediation** — use the exported findings as input to an AWS Config remediation rule or a custom
  Lambda function that removes non-compliant Organization conditions.

## Cleanup

To remove all resources deployed by this Guidance:

1. **Empty the WebUI S3 bucket** before deleting the hub stack (CloudFormation cannot delete a non-empty bucket):

   ```bash
   BUCKET=$(aws cloudformation describe-stack-resources \
     --stack-name account-assessment-for-aws-organizations-hub \
     --query "StackResources[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" \
     --output text \
     --profile <PROFILE_HUB>)

   aws s3 rm s3://$BUCKET --recursive --profile <PROFILE_HUB>
   ```

2. **Delete the hub stack**:

   ```bash
   aws cloudformation delete-stack \
     --stack-name account-assessment-for-aws-organizations-hub \
     --profile <PROFILE_HUB>

   aws cloudformation wait stack-delete-complete \
     --stack-name account-assessment-for-aws-organizations-hub \
     --profile <PROFILE_HUB>
   ```

3. **Delete each spoke stack** (repeat for every spoke account):

   ```bash
   aws cloudformation delete-stack \
     --stack-name account-assessment-for-aws-organizations-spoke \
     --profile <PROFILE_SPOKE>
   ```

4. **Delete the Org Management stack** (if deployed):

   ```bash
   aws cloudformation delete-stack \
     --stack-name account-assessment-for-aws-organizations-org-management \
     --profile <PROFILE_ORG_MGMT>
   ```

5. **Delete CDK bootstrap resources** (optional — only if CDK is not used for other workloads in these accounts):

   ```bash
   aws cloudformation delete-stack --stack-name CDKToolkit --profile <PROFILE_HUB>
   ```

> **Note:** The WebUI hosting bucket and CloudFront access-log bucket are retained with `RemovalPolicy.RETAIN`
> after stack deletion to prevent accidental data loss. Delete them manually from the S3 console if no longer needed.

## FAQ, known issues, additional considerations, and limitations

### Known issues

- If you redeploy with a different `DeploymentNamespace`, resources from the previous deployment are not
  automatically cleaned up. Delete the old stacks before redeploying with a new namespace.
- The Cognito welcome email may be delayed up to 5 minutes after stack creation completes.

### Additional considerations

- This Guidance creates a publicly accessible Amazon CloudFront distribution. Access to the underlying API
  Gateway is restricted by the IP allowlist you provide at deploy time.
- DynamoDB items are automatically expired based on the `DynamoTimeToLive` parameter (default: 90 days). Adjust
  this value during deployment if you need longer retention.
- Each account in your AWS Organization that you want to scan requires its own spoke stack deployment. Accounts
  without a spoke stack will not be included in assessment results.
- This Guidance collects operational metrics to help improve the Guidance over time. Data collection is subject to
  the [AWS Privacy Notice](https://aws.amazon.com/privacy/).

For feedback, questions, or suggestions, please use the
[issues tab](https://github.com/aws-solutions/account-assessment-for-aws-organizations/issues) under this repository.

## Revisions

| Version | Date | Description |
| --- | --- | --- |
| 1.1.11 | 2026-05-19 | Security dependency updates |
| 1.1.10 | 2026-04-08 | Security dependency updates |
| 1.1.9 | 2026-03-11 | Added missing IAM permission; security dependency updates |

See [CHANGELOG.md](CHANGELOG.md) for the full revision history.

## Notices

Customers are responsible for making their own independent assessment of the information in this Guidance.
This Guidance: (a) is for informational purposes only, (b) represents AWS current product offerings and practices,
which are subject to change without notice, and (c) does not create any commitments or assurances from AWS and its
affiliates, suppliers or licensors. AWS products or services are provided "as is" without warranties,
representations, or conditions of any kind, whether express or implied. AWS responsibilities and liabilities to
its customers are controlled by AWS agreements, and this Guidance is not part of, nor does it modify, any agreement
between AWS and its customers.

## Authors

This Guidance was built by the AWS Solutions Development team.

For contributions, see [CONTRIBUTING.md](CONTRIBUTING.md).
