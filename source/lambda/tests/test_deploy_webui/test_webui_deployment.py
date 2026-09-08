#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  SPDX-License-Identifier: Apache-2.0
import json
from io import BytesIO
from os import environ
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from moto import mock_aws
from mypy_boto3_s3 import S3ServiceResource

from aws.services.s3 import S3
from aws.utils.boto3_session import Boto3Session
from deploy_webui.deploy_webui import WebUIDeployer, lambda_handler


def describe_webui_deploy():
    webui_src_path = "account-assessment/v1.2.3/webui/"
    config = {
        "SrcBucket": "solutionBucket",
        "SrcPath": webui_src_path,
        "WebUIBucket": "myConsoleBucket",
        "AwsUserPoolsId": "myUserPoolId",
        "AwsUserPoolsWebClientId": "myWebClient",
        "AwsCognitoIdentityPoolId": "myCognitoIdp",
        "AwsAppsyncGraphqlEndpoint": "myAppSyncEndpoint",
        "AwsContentDeliveryBucket": "myCDNBucket",
        "AwsContentDeliveryUrl": "muCDNUrl",
        "AwsCognitoDomainPrefix": ""
    }
    environ['CONFIG'] = json.dumps(config)
    environ['AWS_ACCESS_KEY_ID'] = 'testing'
    environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    environ['AWS_SECURITY_TOKEN'] = 'testing'
    environ['AWS_SESSION_TOKEN'] = 'testing'

    @mock_aws
    def test_webui_files_are_copied_and_config_is_generated():
        # ARRANGE
        web_ui_deployer = WebUIDeployer()
        s3_resource: S3ServiceResource = Boto3Session('s3').get_resource()

        source_bucket = s3_resource.create_bucket(Bucket=config['SrcBucket'])
        webui_bucket = s3_resource.create_bucket(Bucket=config['WebUIBucket'])

        filenames_from_manifest = ["index.html", "static/css/main.b4f55c7e.css", "static/js/main.c838e191.js"]
        for key in filenames_from_manifest:
            source_bucket.put_object(
                Key=webui_src_path + key
            )
        some_other_filename = "other-solution/other-file.js"
        source_bucket.put_object(
            Key=some_other_filename
        )

        S3().write_json_as_file(
            source_bucket.name,
            webui_src_path + 'webui-manifest.json',
            {'files':filenames_from_manifest}
        )

        # ACT
        web_ui_deployer.deploy()

        # ASSERT
        objects_in_console_bucket = webui_bucket.objects.all()
        keys = list(object.key for object in objects_in_console_bucket)
        assert "index.html" in keys
        assert "static/css/main.b4f55c7e.css" in keys
        assert "static/js/main.c838e191.js" in keys
        assert some_other_filename not in keys

        generated_config_filename = "aws-exports-generated.json"
        assert generated_config_filename in keys

    @mock_aws
    def test_lambda_handler_throws_no_such_bucket():
        # ARRANGE

        # ASSERT
        with pytest.raises(Exception):
            # ACT
            lambda_handler({"RequestType": "Update", "ResourceProperties": config}, {})

    @mock_aws
    def test_webui_archive_is_extracted_and_config_is_generated():
        # ARRANGE
        archive_config = {
            **config,
            "SourceType": "archive",
            "SrcPath": "assets/webui.zip",
            "awsExports": {"Auth": {"region": "us-east-1"}},
        }
        environ['CONFIG'] = json.dumps(archive_config)
        web_ui_deployer = WebUIDeployer()
        s3_resource: S3ServiceResource = Boto3Session('s3').get_resource()

        source_bucket = s3_resource.create_bucket(Bucket=archive_config['SrcBucket'])
        webui_bucket = s3_resource.create_bucket(Bucket=archive_config['WebUIBucket'])

        archive_buffer = BytesIO()
        with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("index.html", "<html></html>")
            archive.writestr("assets/app.js", "console.log('ready')")
            archive.writestr("webui-manifest.json", "{}")
        source_bucket.put_object(
            Key=archive_config['SrcPath'],
            Body=archive_buffer.getvalue(),
        )

        # ACT
        web_ui_deployer.deploy()

        # ASSERT
        keys = [object_summary.key for object_summary in webui_bucket.objects.all()]
        assert "index.html" in keys
        assert "assets/app.js" in keys
        assert "aws-exports-generated.json" in keys
        assert "webui-manifest.json" not in keys
