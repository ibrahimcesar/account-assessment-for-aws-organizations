# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest


INSTALLER_PATH = (
    Path(__file__).resolve().parents[4]
    / "deployment"
    / "prepackaged"
    / "github_release_installer.py"
)


def load_installer():
    spec = importlib.util.spec_from_file_location(
        "github_release_installer",
        INSTALLER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_payload(files):
    payload = BytesIO()
    with ZipFile(payload, "w", compression=ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return payload.getvalue()


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        return self.pages


class FakeS3:
    def __init__(self, pages=None):
        self.objects = {}
        self.deleted = []
        self.pages = pages or []

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs

    def get_paginator(self, operation_name):
        assert operation_name == "list_objects_v2"
        return FakePaginator(self.pages)

    def delete_objects(self, **kwargs):
        self.deleted.append(kwargs)


def test_release_payload_is_verified_and_staged():
    installer = load_installer()
    hub_template_key = "templates/hub.template"
    payload = create_payload(
        {
            hub_template_key: "{}",
            "solution/v1/lambda.zip": b"lambda",
        }
    )
    fake_s3 = FakeS3()

    installer._validate_checksum(
        payload,
        hashlib.sha256(payload).hexdigest(),
    )
    installer._stage_release_payload(
        fake_s3,
        "asset-bucket",
        payload,
        hub_template_key,
    )

    assert set(fake_s3.objects) == {
        hub_template_key,
        "solution/v1/lambda.zip",
    }
    assert fake_s3.objects[hub_template_key]["ContentType"] == "application/json"


def test_release_payload_rejects_unsafe_paths():
    installer = load_installer()
    payload = create_payload(
        {
            "templates/hub.template": "{}",
            "../unexpected": "unsafe",
        }
    )

    with pytest.raises(ValueError, match="Unsafe path"):
        installer._stage_release_payload(
            FakeS3(),
            "asset-bucket",
            payload,
            "templates/hub.template",
        )


def test_release_payload_rejects_checksum_mismatch():
    installer = load_installer()

    with pytest.raises(ValueError, match="checksum mismatch"):
        installer._validate_checksum(b"payload", "0" * 64)


def test_installer_empties_staging_bucket():
    installer = load_installer()
    fake_s3 = FakeS3(
        pages=[
            {"Contents": [{"Key": "one"}, {"Key": "two"}]},
            {},
        ]
    )

    installer._empty_bucket(fake_s3, "asset-bucket")

    assert fake_s3.deleted == [
        {
            "Bucket": "asset-bucket",
            "Delete": {
                "Objects": [{"Key": "one"}, {"Key": "two"}],
                "Quiet": True,
            },
        }
    ]


def test_handler_returns_staged_hub_template_url(monkeypatch):
    installer = load_installer()
    hub_template_key = "templates/hub.template"
    payload = create_payload({hub_template_key: "{}"})
    fake_s3 = FakeS3()
    responses = []

    def create_client(service):
        assert service == "s3"
        return fake_s3

    def capture_response(
        event,
        context,
        status,
        data,
        physical_resource_id,
        reason=None,
    ):
        responses.append(
            {
                "status": status,
                "data": data,
                "physical_resource_id": physical_resource_id,
                "reason": reason,
            }
        )

    monkeypatch.setattr(installer.boto3, "client", create_client)
    monkeypatch.setattr(
        installer,
        "_download_release_payload",
        lambda url: payload,
    )
    monkeypatch.setattr(
        installer,
        "_send_response",
        capture_response,
    )
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    installer.handler(
        {
            "RequestType": "Create",
            "StackId": "arn:aws:cloudformation:us-east-1:123456789012:"
                       "stack/installer/stack-id",
            "RequestId": "request-id",
            "LogicalResourceId": "ReleaseAssets",
            "ResponseURL": "https://example.com/response",
            "ResourceProperties": {
                "BucketName": "asset-bucket",
                "ReleaseUrl": "https://github.com/example/payload.zip",
                "ReleaseSha256": hashlib.sha256(payload).hexdigest(),
                "HubTemplateKey": hub_template_key,
                "UrlSuffix": "amazonaws.com",
            },
        },
        object(),
    )

    assert responses == [
        {
            "status": "SUCCESS",
            "data": {
                "HubTemplateUrl": (
                    "https://asset-bucket.s3.us-east-1.amazonaws.com/"
                    "templates/hub.template"
                )
            },
            "physical_resource_id": "github-release-assets-stack-id",
            "reason": None,
        }
    ]
