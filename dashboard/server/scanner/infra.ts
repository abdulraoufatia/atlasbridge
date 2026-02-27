/**
 * Infrastructure-as-Code security analysis — scans Terraform and CloudFormation
 * files for common misconfigurations. Code-level analysis only, no cloud API calls.
 */

import fs from "fs";
import path from "path";
import type { InfraFinding, InfraScanResult } from "@shared/schema";

// ---------------------------------------------------------------------------
// Terraform checks
// ---------------------------------------------------------------------------

interface TfCheck {
  pattern: RegExp;
  check: string;
  severity: InfraFinding["severity"];
  detail: string;
  remediation: string;
}

const TF_CHECKS: TfCheck[] = [
  {
    pattern: /acl\s*=\s*"public-read"/,
    check: "public-s3-bucket",
    severity: "critical",
    detail: "S3 bucket has public-read ACL, exposing data to the internet",
    remediation: 'Set acl = "private" or remove the acl argument and use bucket policies',
  },
  {
    pattern: /acl\s*=\s*"public-read-write"/,
    check: "public-write-s3-bucket",
    severity: "critical",
    detail: "S3 bucket has public-read-write ACL, allowing anyone to modify data",
    remediation: 'Set acl = "private" and use bucket policies for access control',
  },
  {
    pattern: /cidr_blocks\s*=\s*\[\s*"0\.0\.0\.0\/0"\s*\]/,
    check: "open-security-group",
    severity: "high",
    detail: "Security group allows ingress from 0.0.0.0/0 (entire internet)",
    remediation: "Restrict CIDR blocks to specific IP ranges or use security group references",
  },
  {
    pattern: /ipv6_cidr_blocks\s*=\s*\[\s*"::\s*\/0"\s*\]/,
    check: "open-security-group-ipv6",
    severity: "high",
    detail: "Security group allows ingress from ::/0 (entire IPv6 internet)",
    remediation: "Restrict IPv6 CIDR blocks to specific ranges",
  },
  {
    pattern: /storage_encrypted\s*=\s*false/,
    check: "unencrypted-rds",
    severity: "high",
    detail: "RDS instance has storage encryption disabled",
    remediation: "Set storage_encrypted = true to enable encryption at rest",
  },
  {
    pattern: /encrypted\s*=\s*false/,
    check: "unencrypted-ebs",
    severity: "medium",
    detail: "EBS volume has encryption disabled",
    remediation: "Set encrypted = true to enable EBS encryption at rest",
  },
  {
    pattern: /"Action"\s*:\s*"\*"/,
    check: "overly-permissive-iam",
    severity: "critical",
    detail: 'IAM policy uses "Action": "*" which grants all permissions',
    remediation: "Follow least-privilege principle — specify only required actions",
  },
  {
    pattern: /"Resource"\s*:\s*"\*"/,
    check: "wildcard-iam-resource",
    severity: "high",
    detail: 'IAM policy uses "Resource": "*" which applies to all resources',
    remediation: "Scope resources to specific ARN patterns",
  },
  {
    pattern: /is_multi_region_trail\s*=\s*false/,
    check: "single-region-cloudtrail",
    severity: "medium",
    detail: "CloudTrail is configured for single region only",
    remediation: "Set is_multi_region_trail = true for comprehensive audit logging",
  },
  {
    pattern: /enable_log_file_validation\s*=\s*false/,
    check: "no-cloudtrail-log-validation",
    severity: "medium",
    detail: "CloudTrail log file validation is disabled",
    remediation: "Set enable_log_file_validation = true to detect log tampering",
  },
  {
    pattern: /publicly_accessible\s*=\s*true/,
    check: "public-rds",
    severity: "critical",
    detail: "RDS instance is publicly accessible from the internet",
    remediation: "Set publicly_accessible = false and use VPC security groups",
  },
  {
    pattern: /server_side_encryption_configuration\s*\{[^}]*\}/,
    check: "s3-encryption-check",
    severity: "low",
    detail: "S3 encryption configuration found (informational)",
    remediation: "Verify AES-256 or aws:kms encryption is configured",
  },
];

function scanTerraformFile(filePath: string, content: string): InfraFinding[] {
  const findings: InfraFinding[] = [];
  const lines = content.split("\n");
  const relativePath = filePath;

  // Extract resource blocks for context
  let currentResource = "";
  for (let i = 0; i < lines.length; i++) {
    const resourceMatch = lines[i].match(/^resource\s+"([^"]+)"\s+"([^"]+)"/);
    if (resourceMatch) {
      currentResource = `${resourceMatch[1]}.${resourceMatch[2]}`;
    }

    for (const check of TF_CHECKS) {
      // Skip informational checks (severity: low) in general scan
      if (check.severity === "low") continue;
      if (check.pattern.test(lines[i])) {
        findings.push({
          file: relativePath,
          line: i + 1,
          resource: currentResource || "unknown",
          check: check.check,
          severity: check.severity,
          detail: check.detail,
          remediation: check.remediation,
        });
      }
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// CloudFormation checks
// ---------------------------------------------------------------------------

interface CfCheck {
  pattern: RegExp;
  check: string;
  severity: InfraFinding["severity"];
  detail: string;
  remediation: string;
}

const CF_CHECKS: CfCheck[] = [
  {
    pattern: /AccessControl:\s*PublicRead/,
    check: "cf-public-s3",
    severity: "critical",
    detail: "CloudFormation S3 bucket has PublicRead access control",
    remediation: "Remove AccessControl or set to Private",
  },
  {
    pattern: /CidrIp:\s*0\.0\.0\.0\/0/,
    check: "cf-open-security-group",
    severity: "high",
    detail: "Security group ingress allows 0.0.0.0/0",
    remediation: "Restrict CidrIp to specific ranges",
  },
  {
    pattern: /PubliclyAccessible:\s*true/i,
    check: "cf-public-rds",
    severity: "critical",
    detail: "RDS instance is publicly accessible",
    remediation: "Set PubliclyAccessible to false",
  },
  {
    pattern: /StorageEncrypted:\s*false/i,
    check: "cf-unencrypted-rds",
    severity: "high",
    detail: "RDS storage encryption is disabled",
    remediation: "Set StorageEncrypted to true",
  },
  {
    pattern: /"Effect"\s*:\s*"Allow"[\s\S]*?"Action"\s*:\s*"\*"/,
    check: "cf-overly-permissive-iam",
    severity: "critical",
    detail: 'IAM policy allows "*" action',
    remediation: "Specify only required actions",
  },
];

function isCloudFormationFile(content: string): boolean {
  return content.includes("AWSTemplateFormatVersion") || content.includes("AWS::CloudFormation");
}

function scanCloudFormationFile(filePath: string, content: string): InfraFinding[] {
  const findings: InfraFinding[] = [];
  const lines = content.split("\n");

  let currentResource = "";
  for (let i = 0; i < lines.length; i++) {
    // Track resource context (indented resource type)
    const typeMatch = lines[i].match(/Type:\s*(AWS::\S+)/);
    if (typeMatch) currentResource = typeMatch[1];

    for (const check of CF_CHECKS) {
      if (check.pattern.test(lines[i])) {
        findings.push({
          file: filePath,
          line: i + 1,
          resource: currentResource || "unknown",
          check: check.check,
          severity: check.severity,
          detail: check.detail,
          remediation: check.remediation,
        });
      }
    }
  }

  return findings;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function scanInfraAsCode(repoPath: string): InfraScanResult {
  const findings: InfraFinding[] = [];
  let filesScanned = 0;

  function walkDir(dir: string) {
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory()) {
        // Skip known non-IaC directories
        if ([".git", "node_modules", ".terraform", "vendor"].includes(entry.name)) continue;
        walkDir(fullPath);
        continue;
      }

      if (!entry.isFile()) continue;

      const relativePath = path.relative(repoPath, fullPath);
      const ext = path.extname(entry.name).toLowerCase();

      // Terraform files
      if (ext === ".tf") {
        try {
          const content = fs.readFileSync(fullPath, "utf-8");
          filesScanned++;
          findings.push(...scanTerraformFile(relativePath, content));
        } catch { /* skip unreadable files */ }
        continue;
      }

      // CloudFormation files (YAML/JSON)
      if (ext === ".yaml" || ext === ".yml" || ext === ".json") {
        try {
          const content = fs.readFileSync(fullPath, "utf-8");
          if (isCloudFormationFile(content)) {
            filesScanned++;
            findings.push(...scanCloudFormationFile(relativePath, content));
          }
        } catch { /* skip unreadable files */ }
      }
    }
  }

  walkDir(repoPath);

  return {
    findings: findings.slice(0, 100),
    filesScanned,
    totalFindings: findings.length,
    criticalCount: findings.filter((f) => f.severity === "critical").length,
    highCount: findings.filter((f) => f.severity === "high").length,
    scannedAt: new Date().toISOString(),
  };
}
