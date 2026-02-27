import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "fs";
import path from "path";
import os from "os";

describe("infra scanner", () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "infra-scan-test-"));
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it("returns empty for repo with no IaC files", async () => {
    fs.writeFileSync(path.join(tempDir, "README.md"), "# Hello");
    const { scanInfraAsCode } = await import("../scanner/infra");
    const result = scanInfraAsCode(tempDir);
    expect(result.totalFindings).toBe(0);
    expect(result.findings).toEqual([]);
  });

  it("detects public S3 bucket in terraform", async () => {
    const tfContent = `
resource "aws_s3_bucket" "public_data" {
  bucket = "my-public-bucket"
  acl    = "public-read"
}
`;
    fs.writeFileSync(path.join(tempDir, "main.tf"), tfContent);

    const { scanInfraAsCode } = await import("../scanner/infra");
    const result = scanInfraAsCode(tempDir);

    expect(result.totalFindings).toBeGreaterThanOrEqual(1);
    const finding = result.findings.find((f) => f.check.includes("public") || f.check.includes("S3") || f.detail.includes("public"));
    expect(finding).toBeDefined();
  });

  it("detects open security group in terraform", async () => {
    const tfContent = `
resource "aws_security_group" "open" {
  name = "too-open"

  ingress {
    from_port   = 22
    to_port     = 22
    cidr_blocks = ["0.0.0.0/0"]
  }
}
`;
    fs.writeFileSync(path.join(tempDir, "network.tf"), tfContent);

    const { scanInfraAsCode } = await import("../scanner/infra");
    const result = scanInfraAsCode(tempDir);

    expect(result.totalFindings).toBeGreaterThanOrEqual(1);
    const sgFinding = result.findings.find((f) => f.detail.includes("0.0.0.0/0") || f.check.includes("security") || f.check.includes("open"));
    expect(sgFinding).toBeDefined();
  });

  it("detects overly permissive IAM in terraform", async () => {
    const tfContent = `
resource "aws_iam_policy" "admin" {
  name = "admin-access"
  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "*",
    "Resource": "*"
  }]
}
EOF
}
`;
    fs.writeFileSync(path.join(tempDir, "iam.tf"), tfContent);

    const { scanInfraAsCode } = await import("../scanner/infra");
    const result = scanInfraAsCode(tempDir);

    const iamFinding = result.findings.find((f) => f.detail.includes("*") || f.check.includes("IAM") || f.check.includes("permissive"));
    expect(iamFinding).toBeDefined();
  });

  it("scans CloudFormation files", async () => {
    const cfnContent = `
AWSTemplateFormatVersion: "2010-09-09"
Resources:
  PublicBucket:
    Type: AWS::S3::Bucket
    Properties:
      AccessControl: PublicRead
      BucketName: my-public-bucket
`;
    fs.writeFileSync(path.join(tempDir, "template.yaml"), cfnContent);

    const { scanInfraAsCode } = await import("../scanner/infra");
    const result = scanInfraAsCode(tempDir);

    expect(result.filesScanned).toBeGreaterThanOrEqual(1);
    const finding = result.findings.find((f) => f.detail.includes("public") || f.detail.includes("Public"));
    expect(finding).toBeDefined();
  });

  it("skips .git and node_modules directories", async () => {
    fs.mkdirSync(path.join(tempDir, ".git"), { recursive: true });
    fs.mkdirSync(path.join(tempDir, "node_modules", "pkg"), { recursive: true });
    fs.writeFileSync(path.join(tempDir, ".git", "main.tf"), 'acl = "public-read"');
    fs.writeFileSync(path.join(tempDir, "node_modules", "pkg", "main.tf"), 'acl = "public-read"');

    const { scanInfraAsCode } = await import("../scanner/infra");
    const result = scanInfraAsCode(tempDir);

    expect(result.totalFindings).toBe(0);
  });

  it("includes scannedAt timestamp", async () => {
    const { scanInfraAsCode } = await import("../scanner/infra");
    const result = scanInfraAsCode(tempDir);
    expect(result.scannedAt).toBeDefined();
    expect(new Date(result.scannedAt).getTime()).toBeGreaterThan(0);
  });
});
