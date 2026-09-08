#!/usr/bin/env python3
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote


REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def file_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_template(
    installer_code: str,
    release_url: str,
    release_sha256: str,
    hub_template_key: str,
    solution_version: str,
) -> dict:
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": (
            "(SO0217) - GitHub release installer for Account Assessment "
            f"for AWS Organizations, Version: {solution_version}"
        ),
        "Metadata": {
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": [
                    {
                        "Label": {"default": "Solution setup"},
                        "Parameters": ["DeploymentNamespace"],
                    },
                    {
                        "Label": {"default": "Web UI configuration"},
                        "Parameters": ["UserEmail", "MultiFactorAuthentication"],
                    },
                    {
                        "Label": {"default": "Data configuration"},
                        "Parameters": ["DynamoTimeToLive"],
                    },
                    {
                        "Label": {"default": "Security configuration"},
                        "Parameters": ["AllowListedIPRanges"],
                    },
                ],
                "ParameterLabels": {
                    "DeploymentNamespace": {
                        "default": "Unique deployment namespace"
                    },
                    "UserEmail": {"default": "Initial Web UI user email"},
                    "MultiFactorAuthentication": {
                        "default": "Cognito multi-factor authentication"
                    },
                    "DynamoTimeToLive": {
                        "default": "DynamoDB item lifetime in days"
                    },
                    "AllowListedIPRanges": {
                        "default": "CIDR ranges allowed to access the API"
                    },
                },
            }
        },
        "Parameters": {
            "DeploymentNamespace": {
                "Description": (
                    "Prefix for resource names. Use the same value for the "
                    "hub, organization-management, and spoke stacks."
                ),
                "Type": "String",
                "MinLength": 3,
                "MaxLength": 10,
                "AllowedPattern": "^[a-z0-9][a-z0-9-]{1,8}[a-z0-9]$",
                "ConstraintDescription": (
                    "Must be 3-10 lowercase letters, numbers, or hyphens, "
                    "and cannot begin or end with a hyphen."
                ),
            },
            "UserEmail": {
                "Description": (
                    "Email address for the initial Amazon Cognito Web UI user."
                ),
                "Type": "String",
                "AllowedPattern": (
                    '^(([^<>()\\[\\]\\\\.,;:\\s@"]+'
                    '(\\.[^<>()\\[\\]\\\\.,;:\\s@"]+)*)|(".+"))@'
                    "((\\[[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}"
                    "\\.[0-9]{1,3}])|"
                    "(([a-zA-Z\\-0-9]+\\.)+[a-zA-Z]{2,}))$"
                ),
            },
            "MultiFactorAuthentication": {
                "Description": (
                    "Set to ON or OPTIONAL for the Amazon Cognito user pool."
                ),
                "Type": "String",
                "Default": "OPTIONAL",
                "AllowedValues": ["ON", "OPTIONAL"],
            },
            "DynamoTimeToLive": {
                "Description": "DynamoDB item lifetime in days.",
                "Type": "Number",
                "Default": 90,
            },
            "AllowListedIPRanges": {
                "Description": (
                    "Comma-separated CIDR ranges allowed to access the API."
                ),
                "Type": "CommaDelimitedList",
                "Default": "0.0.0.0/1,128.0.0.0/1",
            },
        },
        "Resources": {
            "ArtifactBucket": {
                "Type": "AWS::S3::Bucket",
                "DeletionPolicy": "Delete",
                "UpdateReplacePolicy": "Delete",
                "Metadata": {
                    "cfn_nag": {
                        "rules_to_suppress": [
                            {
                                "id": "W35",
                                "reason": (
                                    "This private installation staging bucket "
                                    "does not require access logging."
                                ),
                            },
                            {
                                "id": "W51",
                                "reason": (
                                    "Public access is blocked and all access is "
                                    "granted through identity policies."
                                ),
                            },
                        ]
                    }
                },
                "Properties": {
                    "BucketEncryption": {
                        "ServerSideEncryptionConfiguration": [
                            {
                                "ServerSideEncryptionByDefault": {
                                    "SSEAlgorithm": "AES256"
                                }
                            }
                        ]
                    },
                    "OwnershipControls": {
                        "Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]
                    },
                    "PublicAccessBlockConfiguration": {
                        "BlockPublicAcls": True,
                        "BlockPublicPolicy": True,
                        "IgnorePublicAcls": True,
                        "RestrictPublicBuckets": True,
                    },
                },
            },
            "InstallerRole": {
                "Type": "AWS::IAM::Role",
                "Metadata": {
                    "cfn_nag": {
                        "rules_to_suppress": [
                            {
                                "id": "W11",
                                "reason": (
                                    "CloudWatch Logs requires a wildcard log "
                                    "stream resource for this function."
                                ),
                            },
                            {
                                "id": "W28",
                                "reason": (
                                    "A predictable role name makes the required "
                                    "CAPABILITY_NAMED_IAM acknowledgement explicit."
                                ),
                            },
                        ]
                    }
                },
                "Properties": {
                    "RoleName": {
                        "Fn::Sub": (
                            "${DeploymentNamespace}-${AWS::Region}-"
                            "SO0217-Installer"
                        )
                    },
                    "AssumeRolePolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {
                                    "Service": ["lambda.amazonaws.com"]
                                },
                                "Action": ["sts:AssumeRole"],
                            }
                        ],
                    },
                    "Policies": [
                        {
                            "PolicyName": "StageGitHubReleaseAssets",
                            "PolicyDocument": {
                                "Version": "2012-10-17",
                                "Statement": [
                                    {
                                        "Effect": "Allow",
                                        "Action": [
                                            "logs:CreateLogGroup",
                                            "logs:CreateLogStream",
                                            "logs:PutLogEvents",
                                        ],
                                        "Resource": {
                                            "Fn::Sub": (
                                                "arn:${AWS::Partition}:logs:"
                                                "${AWS::Region}:${AWS::AccountId}:*"
                                            )
                                        },
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": [
                                            "s3:GetBucketLocation",
                                            "s3:ListBucket",
                                        ],
                                        "Resource": {
                                            "Fn::GetAtt": [
                                                "ArtifactBucket",
                                                "Arn",
                                            ]
                                        },
                                    },
                                    {
                                        "Effect": "Allow",
                                        "Action": [
                                            "s3:DeleteObject",
                                            "s3:GetObject",
                                            "s3:PutObject",
                                        ],
                                        "Resource": {
                                            "Fn::Sub": "${ArtifactBucket.Arn}/*"
                                        },
                                    },
                                ],
                            },
                        }
                    ],
                },
            },
            "InstallerFunction": {
                "Type": "AWS::Lambda::Function",
                "Metadata": {
                    "cfn_nag": {
                        "rules_to_suppress": [
                            {
                                "id": "W89",
                                "reason": (
                                    "The installer needs public GitHub access "
                                    "and does not access VPC resources."
                                ),
                            },
                            {
                                "id": "W92",
                                "reason": (
                                    "Reserved concurrency is unnecessary for a "
                                    "single CloudFormation custom resource."
                                ),
                            },
                        ]
                    }
                },
                "Properties": {
                    "Runtime": "python3.12",
                    "Handler": "index.handler",
                    "Role": {"Fn::GetAtt": ["InstallerRole", "Arn"]},
                    "Timeout": 900,
                    "MemorySize": 1024,
                    "EphemeralStorage": {"Size": 1024},
                    "Code": {"ZipFile": installer_code},
                },
            },
            "ReleaseAssets": {
                "Type": "Custom::GitHubReleaseAssets",
                "Properties": {
                    "ServiceToken": {
                        "Fn::GetAtt": ["InstallerFunction", "Arn"]
                    },
                    "BucketName": {"Ref": "ArtifactBucket"},
                    "ReleaseUrl": release_url,
                    "ReleaseSha256": release_sha256,
                    "HubTemplateKey": hub_template_key,
                    "UrlSuffix": {"Ref": "AWS::URLSuffix"},
                },
            },
            "SolutionStack": {
                "Type": "AWS::CloudFormation::Stack",
                "Properties": {
                    "TemplateURL": {
                        "Fn::GetAtt": [
                            "ReleaseAssets",
                            "HubTemplateUrl",
                        ]
                    },
                    "TimeoutInMinutes": 60,
                    "Parameters": {
                        "AssetBucketName": {"Ref": "ArtifactBucket"},
                        "DeploymentNamespace": {
                            "Ref": "DeploymentNamespace"
                        },
                        "UserEmail": {"Ref": "UserEmail"},
                        "MultiFactorAuthentication": {
                            "Ref": "MultiFactorAuthentication"
                        },
                        "DynamoTimeToLive": {
                            "Ref": "DynamoTimeToLive"
                        },
                        "AllowListedIPRanges": {
                            "Fn::Join": [
                                ",",
                                {"Ref": "AllowListedIPRanges"},
                            ]
                        },
                    },
                    "Tags": [
                        {
                            "Key": "Solutions:SolutionID",
                            "Value": "SO0217",
                        },
                        {
                            "Key": "Solutions:SolutionVersion",
                            "Value": solution_version,
                        },
                    ],
                },
            },
        },
        "Outputs": {
            "HubAccountId": {
                "Description": (
                    "Account ID to provide to the organization-management "
                    "and spoke stacks."
                ),
                "Value": {"Ref": "AWS::AccountId"},
            },
            "ReleaseVersion": {
                "Description": "Installed GitHub release version.",
                "Value": solution_version,
            },
            "NestedHubStackId": {
                "Description": "CloudFormation stack ID of the deployed hub.",
                "Value": {"Ref": "SolutionStack"},
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the GitHub-backed CloudFormation installer template."
    )
    parser.add_argument("--installer-code", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--release-repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--payload-name", required=True)
    parser.add_argument("--hub-template-key", required=True)
    parser.add_argument("--solution-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not REPOSITORY_PATTERN.fullmatch(args.release_repository):
        parser.error(
            "--release-repository must use the GitHub owner/repository format."
        )
    if not args.installer_code.is_file():
        parser.error(f"Installer code not found: {args.installer_code}")
    if not args.payload.is_file():
        parser.error(f"Release payload not found: {args.payload}")

    release_url = (
        f"https://github.com/{args.release_repository}/releases/download/"
        f"{quote(args.release_tag, safe='')}/"
        f"{quote(args.payload_name, safe='')}"
    )
    template = build_template(
        installer_code=args.installer_code.read_text(encoding="utf-8"),
        release_url=release_url,
        release_sha256=file_sha256(args.payload),
        hub_template_key=args.hub_template_key,
        solution_version=args.solution_version,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(template, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created {args.output}")


if __name__ == "__main__":
    main()
