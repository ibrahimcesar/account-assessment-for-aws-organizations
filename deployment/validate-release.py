#!/usr/bin/env python3
#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def file_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(file_path: Path) -> dict:
    with file_path.open(encoding="utf-8") as source:
        return json.load(source)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate generated GitHub release deployment artifacts."
    )
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--hub-template-key", required=True)
    parser.add_argument("--org-template", required=True, type=Path)
    parser.add_argument("--spoke-template", required=True, type=Path)
    parser.add_argument("--asset-prefix", required=True)
    args = parser.parse_args()

    installer = load_json(args.installer)
    load_json(args.org_template)
    load_json(args.spoke_template)

    if args.installer.stat().st_size > 51_200:
        raise ValueError(
            "Installer template exceeds the direct CloudFormation upload limit."
        )

    release_properties = installer["Resources"]["ReleaseAssets"]["Properties"]
    expected_sha256 = file_sha256(args.payload)
    if release_properties["ReleaseSha256"] != expected_sha256:
        raise ValueError("Installer checksum does not match the release payload.")
    if not release_properties["ReleaseUrl"].startswith(
        "https://github.com/"
    ):
        raise ValueError("Installer release URL is not hosted on GitHub.")
    if not release_properties["ReleaseUrl"].endswith(
        f"/{args.payload.name}"
    ):
        raise ValueError("Installer release URL does not match the payload name.")
    if release_properties["HubTemplateKey"] != args.hub_template_key:
        raise ValueError("Installer references an unexpected hub template key.")

    nested_parameters = installer["Resources"]["SolutionStack"]["Properties"][
        "Parameters"
    ]
    if nested_parameters.get("AssetBucketName") != {"Ref": "ArtifactBucket"}:
        raise ValueError("Installer does not pass its private asset bucket.")

    with ZipFile(args.payload) as archive:
        archive_names = set(archive.namelist())
        required_names = {
            args.hub_template_key,
            f"{args.asset_prefix}/lambda.zip",
            f"{args.asset_prefix}/webui.zip",
        }
        missing_names = required_names - archive_names
        if missing_names:
            raise ValueError(
                f"Release payload is missing: {sorted(missing_names)}"
            )
        hub_template_bytes = archive.read(args.hub_template_key)
        if len(hub_template_bytes) > 1_000_000:
            raise ValueError(
                "Hub template exceeds the nested CloudFormation template limit."
            )
        hub_template = json.loads(hub_template_bytes.decode("utf-8"))

    hub_parameters = hub_template.get("Parameters", {})
    if "AssetBucketName" not in hub_parameters:
        raise ValueError("Hub template does not accept the installer asset bucket.")
    for removed_parameter in ("OrganizationID", "ManagementAccountId"):
        if removed_parameter in hub_parameters:
            raise ValueError(
                f"Hub template still exposes {removed_parameter}."
            )

    serialized_hub = json.dumps(hub_template)
    if f"{args.asset_prefix}/lambda.zip" not in serialized_hub:
        raise ValueError("Hub template does not reference the packaged Lambda.")
    if f"{args.asset_prefix}/webui.zip" not in serialized_hub:
        raise ValueError("Hub template does not reference the packaged Web UI.")
    if "organizations:DescribeOrganization" not in serialized_hub:
        raise ValueError("Hub template cannot discover the organization ID.")

    print("Release artifacts are valid.")


if __name__ == "__main__":
    main()
