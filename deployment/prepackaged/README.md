# GitHub-backed CloudFormation installer

The release pipeline publishes four deployment artifacts:

- A small hub installer CloudFormation template.
- A checksummed payload ZIP containing the hub template, Lambda package, and Web UI package.
- A standalone organization-management CloudFormation template.
- A standalone spoke CloudFormation template.

Users upload the installer template directly in the CloudFormation console. Its inline custom resource downloads the
version-pinned payload from GitHub Releases, verifies its SHA-256 checksum, and stages it in a private bucket created
in the user's account. The installer then deploys the hub as a nested stack.

The installer requires no local toolchain. Docker, Node.js, npm, GNU Make, the AWS CLI, and a source checkout are all
maintainer-only dependencies.

The installer exposes the guidance's anonymized operational metrics choice as an optional CloudFormation parameter.

The application continues to use its own S3 bucket for Web UI hosting. The installer bucket is private, belongs to the
user's account, and is deleted with the installer stack after its objects are removed.
