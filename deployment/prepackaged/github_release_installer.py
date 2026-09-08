# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import hashlib
import io
import json
import mimetypes
import os
from pathlib import PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

import boto3
from botocore.exceptions import ClientError


MAX_PAYLOAD_BYTES = 250 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
USER_AGENT = "account-assessment-for-aws-organizations-installer"


def _send_response(event, context, status, data, physical_resource_id, reason=None):
    response_body = json.dumps(
        {
            "Status": status,
            "Reason": reason or f"See CloudWatch Logs: {context.log_stream_name}",
            "PhysicalResourceId": physical_resource_id,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "NoEcho": False,
            "Data": data,
        }
    ).encode("utf-8")
    request = Request(
        event["ResponseURL"],
        data=response_body,
        method="PUT",
        headers={
            "content-type": "",
            "content-length": str(len(response_body)),
        },
    )
    with urlopen(request, timeout=30) as response:
        response.read()


def _download_release_payload(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_PAYLOAD_BYTES:
            raise ValueError("GitHub release payload exceeds the installer size limit.")
        payload = response.read(MAX_PAYLOAD_BYTES + 1)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("GitHub release payload exceeds the installer size limit.")
    return payload


def _validate_checksum(payload, expected_sha256):
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256.lower() != expected_sha256.lower():
        raise ValueError(
            f"GitHub release payload checksum mismatch: expected "
            f"{expected_sha256}, received {actual_sha256}."
        )


def _stage_release_payload(s3_client, bucket_name, payload, hub_template_key):
    try:
        archive = ZipFile(io.BytesIO(payload))
    except BadZipFile as error:
        raise ValueError("GitHub release payload is not a valid ZIP archive.") from error

    with archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        uncompressed_size = sum(member.file_size for member in members)
        if uncompressed_size > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("GitHub release payload expands beyond the installer size limit.")

        staged_keys = set()
        for member in members:
            member_path = PurePosixPath(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Unsafe path in GitHub release payload: {member.filename}")

            key = member_path.as_posix()
            put_object_args = {
                "Bucket": bucket_name,
                "Key": key,
                "Body": archive.read(member),
            }
            content_type, _ = mimetypes.guess_type(key)
            if key.endswith(".template"):
                content_type = "application/json"
            if content_type:
                put_object_args["ContentType"] = content_type

            s3_client.put_object(**put_object_args)
            staged_keys.add(key)

    if hub_template_key not in staged_keys:
        raise ValueError(
            f"GitHub release payload does not contain {hub_template_key}."
        )


def _empty_bucket(s3_client, bucket_name):
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                s3_client.delete_objects(
                    Bucket=bucket_name,
                    Delete={"Objects": objects, "Quiet": True},
                )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "NoSuchBucket":
            raise


def _physical_resource_id(event):
    if event.get("PhysicalResourceId"):
        return event["PhysicalResourceId"]
    stack_identifier = event["StackId"].rsplit("/", 1)[-1]
    return f"github-release-assets-{stack_identifier}"


def handler(event, context):
    physical_resource_id = _physical_resource_id(event)
    try:
        properties = event["ResourceProperties"]
        bucket_name = properties["BucketName"]
        s3_client = boto3.client("s3")

        if event["RequestType"] == "Delete":
            _empty_bucket(s3_client, bucket_name)
            _send_response(
                event,
                context,
                "SUCCESS",
                {},
                physical_resource_id,
            )
            return

        payload = _download_release_payload(properties["ReleaseUrl"])
        _validate_checksum(payload, properties["ReleaseSha256"])
        _stage_release_payload(
            s3_client,
            bucket_name,
            payload,
            properties["HubTemplateKey"],
        )

        region = os.environ["AWS_REGION"]
        url_suffix = properties["UrlSuffix"]
        template_key = properties["HubTemplateKey"]
        template_url = (
            f"https://{bucket_name}.s3.{region}.{url_suffix}/"
            f"{quote(template_key, safe='/')}"
        )
        _send_response(
            event,
            context,
            "SUCCESS",
            {"HubTemplateUrl": template_url},
            physical_resource_id,
        )
    except Exception as error:
        print(f"Installer failed: {type(error).__name__}: {error}")
        _send_response(
            event,
            context,
            "FAILED",
            {},
            physical_resource_id,
            reason=f"{type(error).__name__}: {str(error)[:900]}",
        )
