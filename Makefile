SHELL := /bin/bash

BUILD_IMAGE ?= account-assessment-build:local
BUILD_PLATFORM ?= linux/amd64
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)
REPO_ROOT := $(CURDIR)

DOCKER_BASE = docker run --rm \
	--platform "$(BUILD_PLATFORM)" \
	--user "$(HOST_UID):$(HOST_GID)" \
	--env HOME=/tmp \
	--env CI=true \
	--env SKIP_ASSET_BUILD \
	--env SOLUTION_ID \
	--env SOLUTION_NAME \
	--env SOLUTION_TRADEMARKEDNAME \
	--env SOLUTION_VERSION \
	--env RELEASE_REPOSITORY \
	--env AWS_ACCESS_KEY_ID \
	--env AWS_SECRET_ACCESS_KEY \
	--env AWS_SESSION_TOKEN \
	--env AWS_PROFILE \
	--env AWS_REGION \
	--env AWS_DEFAULT_REGION \
	--volume "$(REPO_ROOT):/workspace" \
	--workdir /workspace

AWS_CONFIG_DIR ?= $(HOME)/.aws
ifneq ($(wildcard $(AWS_CONFIG_DIR)),)
DOCKER_AWS_CONFIG = --volume "$(AWS_CONFIG_DIR):/tmp/.aws:ro" \
	--env AWS_SDK_LOAD_CONFIG=1
endif

DOCKER_RUN = $(DOCKER_BASE) "$(BUILD_IMAGE)"
DOCKER_RUN_AWS = $(DOCKER_BASE) $(DOCKER_AWS_CONFIG) "$(BUILD_IMAGE)"

.PHONY: image build test synth package cdk deploy distribution clean

image:
	docker build --platform "$(BUILD_PLATFORM)" --tag "$(BUILD_IMAGE)" .

build: image
	$(DOCKER_RUN) ./deployment/build-assets.sh

test: image
	$(DOCKER_RUN) ./source/run-all-tests.sh

synth: image
	$(DOCKER_RUN) ./deployment/cdk.sh synth '*' --output /workspace/deployment/cdk.out

package: image
	@test -n "$(VERSION)" || (echo "Usage: make package VERSION=<release-version>"; exit 2)
	$(DOCKER_RUN) ./deployment/package-release.sh "$(VERSION)"

cdk: image
	@test -n "$(CDK_ARGS)" || (echo "Usage: make cdk CDK_ARGS='<cdk command and arguments>'"; exit 2)
	$(DOCKER_RUN_AWS) ./deployment/cdk.sh $(CDK_ARGS)

deploy: image
	@test -n "$(STACK)" || (echo "Usage: make deploy STACK=<stack-name> CDK_ARGS='<cdk arguments>'"; exit 2)
	$(DOCKER_RUN_AWS) ./deployment/cdk.sh deploy "$(STACK)" $(CDK_ARGS)

distribution: image
	@test -n "$(DIST_BUCKET)" || (echo "Usage: make distribution DIST_BUCKET=<bucket-base-name> VERSION=<version>"; exit 2)
	@test -n "$(VERSION)" || (echo "Usage: make distribution DIST_BUCKET=<bucket-base-name> VERSION=<version>"; exit 2)
	$(DOCKER_RUN) ./deployment/build-s3-dist.sh "$(DIST_BUCKET)" account-assessment-for-aws-organizations "$(VERSION)"

clean:
	./deployment/clean.sh
