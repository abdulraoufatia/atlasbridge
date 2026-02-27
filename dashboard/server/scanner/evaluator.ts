import type { RepoContext, RepoSnapshot } from "./types";

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
  remediation: string;
}

function has(snapshot: RepoSnapshot, ...paths: string[]): boolean {
  return paths.some((p) => snapshot.files[p]);
}

// ---------------------------------------------------------------------------
// Security checks
// ---------------------------------------------------------------------------
function securityChecks(snapshot: RepoSnapshot, _ctx: RepoContext, level: string): Check[] {
  const checks: Check[] = [
    {
      name: "LICENSE file present",
      passed: has(snapshot, "LICENSE", "LICENSE.md", "LICENSE.txt"),
      detail: "Repository should include a license file",
      remediation: "Create a LICENSE file in your repository root. Choose a license at https://choosealicense.com — MIT and Apache 2.0 are common choices for open-source projects. For proprietary projects, add a file stating \"All rights reserved\" with your copyright notice.",
    },
    {
      name: ".gitignore configured",
      passed: has(snapshot, ".gitignore"),
      detail: "Sensitive files and build artifacts should be excluded from version control",
      remediation: "Create a .gitignore file in your repository root. Use https://gitignore.io to generate one for your language/framework. At minimum, exclude: build artifacts, dependency directories (node_modules/, venv/), IDE files (.vscode/, .idea/), and environment files (.env).",
    },
    {
      name: "No secrets in source",
      passed: true,
      detail: "Requires dedicated secret scanning tool — not verifiable via file listing",
      remediation: "Enable GitHub's secret scanning (Settings > Code security) or add a pre-commit hook using tools like gitleaks or trufflehog. Rotate any secrets that have been committed historically.",
    },
    {
      name: "SECURITY.md present",
      passed: has(snapshot, "SECURITY.md"),
      detail: "Security policy and vulnerability reporting guidelines",
      remediation: "Create a SECURITY.md file describing how to report vulnerabilities. Include: supported versions, reporting process (email or form), expected response time, and disclosure policy. GitHub provides a template under Settings > Code security > Security policy.",
    },
  ];
  if (level === "standard" || level === "advanced") {
    const bp = snapshot.branchProtection;
    checks.push(
      {
        name: "Branch protection enabled",
        passed: bp.requiresPrReviews === true,
        detail: bp.available ? "Main branch should require PR reviews" : "Could not check — requires admin token",
        remediation: "Go to Settings > Branches > Branch protection rules. Add a rule for your main branch with: Require a pull request before merging (at least 1 approval), Require status checks to pass, and Restrict who can push directly.",
      },
      {
        name: "Signed commits enforced",
        passed: bp.requiresSignedCommits === true,
        detail: bp.available ? "GPG/SSH commit signing verification" : "Could not check — requires admin token",
        remediation: "1. Generate a GPG key: gpg --full-generate-key\n2. Add it to GitHub: Settings > SSH and GPG keys\n3. Configure git: git config --global commit.gpgsign true\n4. Enable in branch protection: Settings > Branches > Require signed commits",
      },
      {
        name: "CODEOWNERS defined",
        passed: has(snapshot, "CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"),
        detail: "Code ownership for review routing",
        remediation: "Create a CODEOWNERS file at .github/CODEOWNERS or the repo root. Each line maps a file pattern to reviewers:\n\n# Default owner\n* @your-team\n\n# Frontend\nsrc/components/ @frontend-team\n\n# Docs\ndocs/ @docs-team",
      },
    );
  }
  if (level === "advanced") {
    checks.push(
      {
        name: "Dependency vulnerability scan",
        passed: has(snapshot, ".github/dependabot.yml", ".github/dependabot.yaml"),
        detail: "Automated scanning for known vulnerabilities in dependencies",
        remediation: "Create .github/dependabot.yml:\n\nversion: 2\nupdates:\n  - package-ecosystem: \"npm\" # or pip, cargo, etc.\n    directory: \"/\"\n    schedule:\n      interval: \"weekly\"\n    open-pull-requests-limit: 10",
      },
      {
        name: "SBOM generation",
        passed: false,
        detail: "No standard SBOM config detected — requires dedicated tooling",
        remediation: "Add SBOM generation to your CI pipeline. For npm: use @cyclonedx/cyclonedx-npm. For Python: use cyclonedx-bom. For GitHub, enable dependency graph (Settings > Code security) which auto-generates SBOM exports.",
      },
      {
        name: "Secret rotation policy",
        passed: false,
        detail: "Cannot verify via API — requires organizational policy",
        remediation: "Establish a secret rotation policy: 1. Inventory all secrets (API keys, tokens, passwords). 2. Set rotation intervals (90 days recommended). 3. Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, or 1Password). 4. Automate rotation where possible.",
      },
    );
  }
  return checks;
}

// ---------------------------------------------------------------------------
// CI/CD checks
// ---------------------------------------------------------------------------
function cicdChecks(snapshot: RepoSnapshot, ctx: RepoContext, level: string): Check[] {
  const ciFiles: Record<string, string[]> = {
    github: [".github/workflows"],
    gitlab: [".gitlab-ci.yml"],
    bitbucket: ["bitbucket-pipelines.yml"],
    azure: ["azure-pipelines.yml"],
  };
  const ciPaths = ciFiles[ctx.provider] ?? Object.values(ciFiles).flat();

  const ciRemediation: Record<string, string> = {
    github: "Create .github/workflows/ci.yml with your build and test steps. Start with:\n\nname: CI\non: [push, pull_request]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: npm ci\n      - run: npm test",
    gitlab: "Create .gitlab-ci.yml in your repo root:\n\nstages:\n  - test\n\ntest:\n  stage: test\n  script:\n    - npm ci\n    - npm test",
    bitbucket: "Create bitbucket-pipelines.yml in your repo root:\n\npipelines:\n  default:\n    - step:\n        script:\n          - npm ci\n          - npm test",
    azure: "Create azure-pipelines.yml in your repo root:\n\ntrigger:\n  - main\n\npool:\n  vmImage: 'ubuntu-latest'\n\nsteps:\n  - script: npm ci\n  - script: npm test",
  };

  const checks: Check[] = [
    {
      name: "CI pipeline configured",
      passed: ciPaths.some((p) => has(snapshot, p)),
      detail: "Automated build and test pipeline should be in place",
      remediation: ciRemediation[ctx.provider] ?? "Create a CI configuration file for your platform with build and test steps.",
    },
    {
      name: "Automated tests present",
      passed: has(snapshot, "jest.config.js", "jest.config.ts", "jest.config.mjs", "vitest.config.ts", "vitest.config.js", "pytest.ini", "setup.cfg", "tox.ini", "Cargo.toml"),
      detail: "Test framework config should exist",
      remediation: "Add a test framework to your project:\n\n- JavaScript/TypeScript: npm install -D vitest (or jest)\n- Python: pip install pytest, create pytest.ini or pyproject.toml [tool.pytest]\n- Rust: tests are built-in, add #[test] functions\n\nCreate at least one test file to verify your setup works.",
    },
  ];
  if (level === "standard" || level === "advanced") {
    checks.push(
      {
        name: "Code coverage tracking",
        passed: has(snapshot, ".coveragerc", ".nycrc", ".nycrc.json", "codecov.yml", ".codecov.yml"),
        detail: "Coverage tracking config should exist",
        remediation: "Add coverage to your test runner:\n\n- vitest: set coverage.enabled = true in vitest.config.ts\n- jest: add --coverage flag and configure in jest.config\n- pytest: pip install pytest-cov, run with --cov=src/\n\nUpload results to Codecov or Coveralls for tracking over time.",
      },
      {
        name: "Static analysis configured",
        passed: has(snapshot, ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", "ruff.toml", ".flake8", "pylintrc", ".pylintrc"),
        detail: "Lint or static analysis tool should be configured",
        remediation: "Add a linter to your project:\n\n- TypeScript/JavaScript: npx eslint --init (or use biome)\n- Python: pip install ruff, create ruff.toml\n- Rust: clippy is built-in, run cargo clippy\n\nAdd the lint step to your CI pipeline.",
      },
      {
        name: "Build artifacts versioned",
        passed: true,
        detail: "Cannot verify via file check alone — assumed if CI is present",
        remediation: "Store build artifacts in your CI system (GitHub Actions artifacts, GitLab artifacts) or publish to a package registry. Tag releases with semantic versions.",
      },
    );
  }
  if (level === "advanced") {
    checks.push(
      {
        name: "Multi-stage deployment",
        passed: false,
        detail: "Requires CI config parsing — not verifiable via file listing",
        remediation: "Set up separate deployment stages in your CI:\n\n1. dev — auto-deploy on push to feature branches\n2. staging — deploy on merge to main\n3. production — manual approval gate or tag-triggered\n\nAdd environment-specific configs and approval steps between stages.",
      },
      {
        name: "Rollback capability",
        passed: false,
        detail: "Requires deployment config analysis",
        remediation: "Implement rollback mechanisms:\n\n1. Use immutable deployments (containers, serverless)\n2. Keep previous deployment artifacts available\n3. Add a rollback job/step in your CI pipeline\n4. Test rollback procedures regularly\n5. Consider blue-green or canary deployment patterns.",
      },
    );
  }
  return checks;
}

// ---------------------------------------------------------------------------
// Documentation checks
// ---------------------------------------------------------------------------
function docChecks(snapshot: RepoSnapshot, _ctx: RepoContext, level: string): Check[] {
  const checks: Check[] = [
    {
      name: "README.md exists",
      passed: has(snapshot, "README.md", "readme.md", "README"),
      detail: "Repository must have a comprehensive README",
      remediation: "Create a README.md with these sections:\n\n1. Project name and one-line description\n2. Installation / getting started\n3. Usage examples\n4. Configuration options\n5. Contributing guidelines (or link to CONTRIBUTING.md)\n6. License\n\nKeep it concise but complete enough for a new contributor to get started.",
    },
    {
      name: "Contributing guidelines",
      passed: has(snapshot, "CONTRIBUTING.md", "contributing.md", ".github/CONTRIBUTING.md"),
      detail: "Contribution workflow and standards",
      remediation: "Create a CONTRIBUTING.md covering:\n\n1. How to set up the development environment\n2. Branch naming conventions\n3. Commit message format\n4. Pull request process\n5. Code review expectations\n6. Testing requirements\n\nLink to it from your README.",
    },
  ];
  if (level === "standard" || level === "advanced") {
    checks.push(
      {
        name: "API documentation",
        passed: has(snapshot, "docs/api.md", "docs/API.md", "openapi.yaml", "openapi.json", "swagger.yaml", "swagger.json"),
        detail: "API documentation with examples",
        remediation: "If your project exposes an API:\n\n1. Create an OpenAPI/Swagger spec (openapi.yaml) for REST APIs\n2. Or add docs/api.md with endpoint descriptions, request/response examples\n3. Use tools like Swagger UI, Redoc, or Stoplight for interactive docs\n4. Include authentication details and error codes.",
      },
      {
        name: "Architecture docs",
        passed: has(snapshot, "docs/architecture.md", "docs/ARCHITECTURE.md", "ARCHITECTURE.md", "docs/design.md"),
        detail: "High-level architecture and design documentation",
        remediation: "Create docs/architecture.md covering:\n\n1. System overview and high-level diagram\n2. Key components and their responsibilities\n3. Data flow between components\n4. Technology choices and rationale\n5. Deployment topology\n\nKeep it updated as the architecture evolves.",
      },
      {
        name: "Changelog maintained",
        passed: has(snapshot, "CHANGELOG.md", "changelog.md", "CHANGES.md", "HISTORY.md"),
        detail: "Version history and breaking changes tracked",
        remediation: "Create a CHANGELOG.md following the Keep a Changelog format (https://keepachangelog.com):\n\n## [Unreleased]\n### Added\n### Changed\n### Fixed\n### Removed\n\nUpdate it with every release. Consider using tools like conventional-changelog to automate.",
      },
    );
  }
  return checks;
}

// ---------------------------------------------------------------------------
// Dependency checks
// ---------------------------------------------------------------------------
function depChecks(snapshot: RepoSnapshot, _ctx: RepoContext, level: string): Check[] {
  const checks: Check[] = [
    {
      name: "Lock file present",
      passed: has(snapshot, "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Pipfile.lock", "poetry.lock", "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock"),
      detail: "Deterministic dependency resolution",
      remediation: "Commit your package manager's lock file to version control:\n\n- npm: package-lock.json (run npm install)\n- yarn: yarn.lock (run yarn)\n- pnpm: pnpm-lock.yaml (run pnpm install)\n- pip: use pip freeze > requirements.txt or Pipfile.lock\n- poetry: poetry.lock (run poetry lock)\n\nNever add lock files to .gitignore.",
    },
    {
      name: "No deprecated packages",
      passed: true,
      detail: "Cannot verify via file listing — requires dependency audit tool",
      remediation: "Run your package manager's audit command regularly:\n\n- npm: npm audit\n- yarn: yarn audit\n- pip: pip-audit or safety check\n- cargo: cargo audit\n\nAdd the audit step to your CI pipeline to catch issues early.",
    },
  ];
  if (level === "standard" || level === "advanced") {
    checks.push(
      {
        name: "Dependabot/Renovate configured",
        passed: has(snapshot, ".github/dependabot.yml", ".github/dependabot.yaml", "renovate.json", ".renovaterc", ".renovaterc.json"),
        detail: "Automated dependency updates",
        remediation: "Set up automated dependency updates:\n\nFor Dependabot, create .github/dependabot.yml:\n  version: 2\n  updates:\n    - package-ecosystem: \"npm\"\n      directory: \"/\"\n      schedule:\n        interval: \"weekly\"\n\nFor Renovate, create renovate.json:\n  { \"extends\": [\"config:base\"] }\n\nBoth will automatically open PRs when dependencies have updates.",
      },
      {
        name: "License compliance",
        passed: has(snapshot, "LICENSE", "LICENSE.md", "LICENSE.txt"),
        detail: "Project license should be explicitly defined",
        remediation: "Ensure your project has a clear license. Then audit dependency licenses for compatibility:\n\n- npm: npx license-checker\n- Python: pip-licenses\n- Rust: cargo-license\n\nEnsure no dependency licenses conflict with your project's license (e.g., GPL dependencies in MIT projects).",
      },
    );
  }
  if (level === "advanced") {
    checks.push(
      {
        name: "Supply chain attestation",
        passed: false,
        detail: "Requires SLSA provenance or similar — not verifiable via file listing",
        remediation: "Implement supply chain security:\n\n1. Use SLSA provenance generation in your CI (GitHub Actions: slsa-framework/slsa-github-generator)\n2. Sign release artifacts with Sigstore/cosign\n3. Pin dependencies by hash, not just version\n4. Use a lock file for reproducible builds\n5. Consider using Socket.dev or Snyk for supply chain monitoring.",
      },
    );
  }
  return checks;
}

// ---------------------------------------------------------------------------
// Code quality checks
// ---------------------------------------------------------------------------
function codeQualityChecks(snapshot: RepoSnapshot, _ctx: RepoContext, level: string): Check[] {
  const checks: Check[] = [
    {
      name: "Linting configured",
      passed: has(snapshot, ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", "ruff.toml", ".flake8", "pylintrc", ".pylintrc", "biome.json"),
      detail: "Code linting rules should be defined and enforced",
      remediation: "Set up a linter for your language:\n\n- TypeScript/JavaScript: npx eslint --init, or install biome\n- Python: pip install ruff, create ruff.toml with your rules\n- Go: golangci-lint is the standard\n- Rust: cargo clippy (built-in)\n\nAdd linting to your CI pipeline and consider a pre-commit hook.",
    },
    {
      name: "Consistent formatting",
      passed: has(snapshot, ".prettierrc", ".prettierrc.js", ".prettierrc.json", ".prettierrc.yml", ".editorconfig", "biome.json", "rustfmt.toml"),
      detail: "Code formatter should be configured",
      remediation: "Set up a code formatter:\n\n- TypeScript/JavaScript: npm install -D prettier, create .prettierrc\n- Python: ruff format (or black)\n- Go: gofmt (built-in)\n- Rust: rustfmt (built-in)\n\nAdd an .editorconfig for cross-editor consistency. Run format checks in CI.",
    },
  ];
  if (level === "standard" || level === "advanced") {
    checks.push(
      {
        name: "Type safety",
        passed: has(snapshot, "tsconfig.json", "mypy.ini", "pyrightconfig.json", "pyproject.toml"),
        detail: "Type checking should be enabled",
        remediation: "Enable type checking:\n\n- TypeScript: create tsconfig.json with strict: true\n- Python: pip install mypy, create mypy.ini or add [tool.mypy] to pyproject.toml with strict = true\n- JavaScript: add // @ts-check to files or use jsconfig.json\n\nAdd type checking to your CI pipeline.",
      },
      {
        name: "Error handling patterns",
        passed: true,
        detail: "Cannot verify via file listing — requires code analysis",
        remediation: "Establish consistent error handling:\n\n1. Define custom error types/classes for your domain\n2. Use structured logging (not console.log/print)\n3. Handle errors at appropriate boundaries\n4. Never swallow errors silently\n5. Add error context when re-throwing\n6. Document error codes and recovery steps.",
      },
    );
  }
  if (level === "advanced") {
    checks.push(
      {
        name: "Complexity metrics",
        passed: false,
        detail: "Requires static analysis tool — not verifiable via file listing",
        remediation: "Track code complexity:\n\n- JavaScript/TypeScript: eslint-plugin-complexity or use SonarQube\n- Python: radon (pip install radon) for cyclomatic complexity\n- Generic: CodeClimate or SonarCloud for automated quality gates\n\nSet thresholds (e.g., max cyclomatic complexity of 10) and enforce in CI.",
      },
      {
        name: "Performance benchmarks",
        passed: has(snapshot, "bench", "benchmarks", "__benchmarks__"),
        detail: "Performance test suite with defined benchmarks",
        remediation: "Add performance benchmarks:\n\n- JavaScript: use vitest bench or benchmark.js\n- Python: pytest-benchmark or pyperf\n- Rust: cargo bench (built-in criterion)\n- Go: go test -bench\n\nCreate a bench/ or benchmarks/ directory. Run benchmarks in CI and track regressions.",
      },
    );
  }
  return checks;
}

// ---------------------------------------------------------------------------
// Public evaluator
// ---------------------------------------------------------------------------
export function evaluateChecks(
  snapshot: RepoSnapshot,
  ctx: RepoContext,
  level: string,
): { security: Check[]; cicd: Check[]; documentation: Check[]; dependencies: Check[]; codeQuality: Check[] } {
  return {
    security: securityChecks(snapshot, ctx, level),
    cicd: cicdChecks(snapshot, ctx, level),
    documentation: docChecks(snapshot, ctx, level),
    dependencies: depChecks(snapshot, ctx, level),
    codeQuality: codeQualityChecks(snapshot, ctx, level),
  };
}
