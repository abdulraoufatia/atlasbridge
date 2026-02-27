/**
 * Shared pattern constants for local repository scanning.
 */

// ---------------------------------------------------------------------------
// Sensitive path patterns — files/dirs that should be flagged in safety scans
// ---------------------------------------------------------------------------

export interface SensitivePathPattern {
  pattern: RegExp;
  reason: string;
  risk: "high" | "medium" | "low";
}

export const SENSITIVE_PATH_PATTERNS: SensitivePathPattern[] = [
  // High risk — secrets / credentials
  { pattern: /^\.env($|\..*)/, reason: "Environment variables (may contain secrets)", risk: "high" },
  { pattern: /\.pem$/i, reason: "PEM certificate/private key", risk: "high" },
  { pattern: /\.p12$/i, reason: "PKCS#12 key store", risk: "high" },
  { pattern: /\.key$/i, reason: "Private key file", risk: "high" },
  { pattern: /\.keystore$/i, reason: "Java keystore", risk: "high" },
  { pattern: /^\.aws\//i, reason: "AWS credentials directory", risk: "high" },
  { pattern: /^\.ssh\//i, reason: "SSH keys directory", risk: "high" },
  { pattern: /^\.gcp\//i, reason: "GCP credentials directory", risk: "high" },
  { pattern: /secret/i, reason: "File name contains 'secret'", risk: "high" },
  { pattern: /credential/i, reason: "File name contains 'credential'", risk: "high" },
  { pattern: /^\.npmrc$/i, reason: "npm config (may contain auth tokens)", risk: "high" },
  { pattern: /^\.pypirc$/i, reason: "PyPI config (may contain auth tokens)", risk: "high" },
  { pattern: /^\.docker\/config\.json$/i, reason: "Docker credentials", risk: "high" },
  { pattern: /^\.netrc$/i, reason: "Network credentials file", risk: "high" },

  // Medium risk — config that may leak info
  { pattern: /^config\/.*\.(json|ya?ml|toml)$/i, reason: "Configuration file", risk: "medium" },
  { pattern: /^\.htpasswd$/i, reason: "HTTP password file", risk: "medium" },
  { pattern: /^\.htaccess$/i, reason: "Apache config (may expose paths)", risk: "medium" },
  { pattern: /^Dockerfile/i, reason: "Docker build config (may embed secrets)", risk: "medium" },
  { pattern: /^docker-compose.*\.ya?ml$/i, reason: "Docker Compose config", risk: "medium" },
  { pattern: /^terraform\.tfvars$/i, reason: "Terraform variables (may contain secrets)", risk: "medium" },

  // Low risk — worth noting
  { pattern: /^\.github\/workflows\/.*\.ya?ml$/i, reason: "CI workflow (review permissions)", risk: "low" },
  { pattern: /^\.gitlab-ci\.yml$/i, reason: "CI config (review permissions)", risk: "low" },
];

// ---------------------------------------------------------------------------
// Secret detection patterns — regex + type labels
// ---------------------------------------------------------------------------

export interface SecretPattern {
  name: string;
  pattern: RegExp;
}

export const SECRET_PATTERNS: SecretPattern[] = [
  { name: "generic-api-key", pattern: /sk[-_][a-zA-Z0-9]{20,}/g },
  { name: "bearer-token", pattern: /Bearer\s+[a-zA-Z0-9._\-]{20,}/g },
  { name: "github-pat", pattern: /ghp_[a-zA-Z0-9]{36}/g },
  { name: "github-oauth", pattern: /gho_[a-zA-Z0-9]{36}/g },
  { name: "github-app-token", pattern: /ghs_[a-zA-Z0-9]{36}/g },
  { name: "gitlab-pat", pattern: /glpat-[a-zA-Z0-9\-_]{20,}/g },
  { name: "slack-token", pattern: /xox[bpras]-[a-zA-Z0-9\-]+/g },
  { name: "private-key", pattern: /-----BEGIN\s+(RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----/g },
  { name: "aws-access-key", pattern: /AKIA[0-9A-Z]{16}/g },
  { name: "aws-secret-key", pattern: /(?:aws_secret_access_key|AWS_SECRET_ACCESS_KEY)[=:\s]+["']?[a-zA-Z0-9/+=]{40}["']?/g },
  { name: "gcp-service-account", pattern: /"type"\s*:\s*"service_account"/g },
  { name: "generic-password", pattern: /password[=:\s]+["']?[^\s"']{8,}["']?/gi },
  { name: "generic-secret", pattern: /secret[=:\s]+["']?[a-zA-Z0-9]{16,}["']?/gi },
  { name: "generic-token", pattern: /token[=:\s]+["']?[a-zA-Z0-9._\-]{20,}["']?/gi },
  { name: "generic-api-key-assignment", pattern: /api[_-]?key[=:\s]+["']?[a-zA-Z0-9]{16,}["']?/gi },
];

// ---------------------------------------------------------------------------
// Language detection — extension → language name
// ---------------------------------------------------------------------------

export const LANGUAGE_EXTENSIONS: Record<string, string> = {
  ".ts": "TypeScript",
  ".tsx": "TypeScript",
  ".js": "JavaScript",
  ".jsx": "JavaScript",
  ".mjs": "JavaScript",
  ".cjs": "JavaScript",
  ".py": "Python",
  ".pyw": "Python",
  ".rs": "Rust",
  ".go": "Go",
  ".java": "Java",
  ".kt": "Kotlin",
  ".kts": "Kotlin",
  ".swift": "Swift",
  ".c": "C",
  ".h": "C",
  ".cpp": "C++",
  ".cc": "C++",
  ".cxx": "C++",
  ".hpp": "C++",
  ".cs": "C#",
  ".rb": "Ruby",
  ".php": "PHP",
  ".scala": "Scala",
  ".ex": "Elixir",
  ".exs": "Elixir",
  ".erl": "Erlang",
  ".hs": "Haskell",
  ".lua": "Lua",
  ".r": "R",
  ".R": "R",
  ".dart": "Dart",
  ".zig": "Zig",
  ".nim": "Nim",
  ".v": "V",
  ".ml": "OCaml",
  ".mli": "OCaml",
  ".clj": "Clojure",
  ".cljs": "Clojure",
  ".sh": "Shell",
  ".bash": "Shell",
  ".zsh": "Shell",
  ".fish": "Shell",
  ".ps1": "PowerShell",
  ".sql": "SQL",
  ".vue": "Vue",
  ".svelte": "Svelte",
};

// ---------------------------------------------------------------------------
// Build system detection — config file → build system name
// ---------------------------------------------------------------------------

export const BUILD_SYSTEM_FILES: Record<string, string> = {
  "package.json": "npm",
  "yarn.lock": "yarn",
  "pnpm-lock.yaml": "pnpm",
  "bun.lockb": "bun",
  "Cargo.toml": "cargo",
  "pyproject.toml": "pip/poetry",
  "setup.py": "setuptools",
  "setup.cfg": "setuptools",
  "Pipfile": "pipenv",
  "requirements.txt": "pip",
  "go.mod": "go",
  "Gemfile": "bundler",
  "composer.json": "composer",
  "build.gradle": "gradle",
  "build.gradle.kts": "gradle",
  "pom.xml": "maven",
  "CMakeLists.txt": "cmake",
  "Makefile": "make",
  "meson.build": "meson",
  "BUILD": "bazel",
  "WORKSPACE": "bazel",
  "Package.swift": "swift-pm",
  "mix.exs": "mix",
  "stack.yaml": "stack",
  "cabal.project": "cabal",
  "Rakefile": "rake",
  "Justfile": "just",
  "Taskfile.yml": "task",
};

// ---------------------------------------------------------------------------
// CI platform detection — config file/dir → platform name
// ---------------------------------------------------------------------------

export const CI_CONFIG_FILES: Record<string, string> = {
  ".github/workflows": "github-actions",
  ".gitlab-ci.yml": "gitlab-ci",
  "bitbucket-pipelines.yml": "bitbucket-pipelines",
  "azure-pipelines.yml": "azure-pipelines",
  ".circleci/config.yml": "circleci",
  "Jenkinsfile": "jenkins",
  ".travis.yml": "travis-ci",
  ".drone.yml": "drone",
  "appveyor.yml": "appveyor",
  ".buildkite/pipeline.yml": "buildkite",
  "cloudbuild.yaml": "google-cloud-build",
  "taskcluster.yml": "taskcluster",
};

// ---------------------------------------------------------------------------
// Framework detection — config file → framework name
// ---------------------------------------------------------------------------

export const FRAMEWORK_INDICATORS: Record<string, string> = {
  "next.config.js": "Next.js",
  "next.config.mjs": "Next.js",
  "next.config.ts": "Next.js",
  "nuxt.config.ts": "Nuxt",
  "nuxt.config.js": "Nuxt",
  "angular.json": "Angular",
  "svelte.config.js": "SvelteKit",
  "svelte.config.ts": "SvelteKit",
  "astro.config.mjs": "Astro",
  "astro.config.ts": "Astro",
  "gatsby-config.js": "Gatsby",
  "gatsby-config.ts": "Gatsby",
  "remix.config.js": "Remix",
  "vite.config.ts": "Vite",
  "vite.config.js": "Vite",
  "webpack.config.js": "Webpack",
  "webpack.config.ts": "Webpack",
  "rollup.config.js": "Rollup",
  "tailwind.config.js": "Tailwind CSS",
  "tailwind.config.ts": "Tailwind CSS",
  "postcss.config.js": "PostCSS",
  "django-admin.py": "Django",
  "manage.py": "Django",
  "flask": "Flask",
  "fastapi": "FastAPI",
  "rails": "Rails",
  "Gemfile": "Ruby",
  "express": "Express",
  "spring": "Spring",
  "Cargo.toml": "Rust",
};

// ---------------------------------------------------------------------------
// Tool surface detection — AI/dev tool config dirs
// ---------------------------------------------------------------------------

export const TOOL_SURFACE_DIRS: Record<string, string> = {
  ".claude": "Claude Code",
  ".cursor": "Cursor",
  ".github/copilot": "GitHub Copilot",
  ".aider": "Aider",
  ".continue": "Continue",
  ".codeium": "Codeium",
  ".tabnine": "Tabnine",
  ".vscode": "VS Code",
  ".idea": "IntelliJ IDEA",
  ".fleet": "Fleet",
};

// ---------------------------------------------------------------------------
// Directories to skip during scanning
// ---------------------------------------------------------------------------

export const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  "vendor",
  "__pycache__",
  ".tox",
  ".venv",
  "venv",
  ".env",
  "env",
  "dist",
  "build",
  ".next",
  ".nuxt",
  "target",
  "out",
  ".cache",
  ".parcel-cache",
  "coverage",
  ".nyc_output",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  "egg-info",
  ".eggs",
]);

// ---------------------------------------------------------------------------
// Binary file extensions to skip during secret scanning
// ---------------------------------------------------------------------------

export const BINARY_EXTENSIONS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
  ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".avi", ".mov",
  ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
  ".woff", ".woff2", ".ttf", ".eot", ".otf",
  ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
  ".exe", ".dll", ".so", ".dylib", ".o", ".a",
  ".pyc", ".pyo", ".class", ".wasm",
  ".lock", ".lockb",
  ".sqlite", ".db",
]);

// ---------------------------------------------------------------------------
// Known license identifiers
// ---------------------------------------------------------------------------

export const LICENSE_PATTERNS: { pattern: RegExp; spdx: string; risk: "compatible" | "review" | "incompatible" }[] = [
  { pattern: /MIT License/i, spdx: "MIT", risk: "compatible" },
  { pattern: /Apache License.*2\.0/i, spdx: "Apache-2.0", risk: "compatible" },
  { pattern: /BSD\s+2-Clause/i, spdx: "BSD-2-Clause", risk: "compatible" },
  { pattern: /BSD\s+3-Clause/i, spdx: "BSD-3-Clause", risk: "compatible" },
  { pattern: /ISC License/i, spdx: "ISC", risk: "compatible" },
  { pattern: /Mozilla Public License.*2\.0/i, spdx: "MPL-2.0", risk: "review" },
  { pattern: /GNU Lesser General Public License/i, spdx: "LGPL", risk: "review" },
  { pattern: /GNU General Public License/i, spdx: "GPL", risk: "incompatible" },
  { pattern: /GNU Affero General Public License/i, spdx: "AGPL", risk: "incompatible" },
  { pattern: /Creative Commons.*Attribution/i, spdx: "CC-BY", risk: "review" },
  { pattern: /Unlicense/i, spdx: "Unlicense", risk: "compatible" },
  { pattern: /The Artistic License 2\.0/i, spdx: "Artistic-2.0", risk: "compatible" },
  { pattern: /Eclipse Public License/i, spdx: "EPL", risk: "review" },
  { pattern: /WTFPL/i, spdx: "WTFPL", risk: "compatible" },
  { pattern: /Boost Software License/i, spdx: "BSL-1.0", risk: "compatible" },
  { pattern: /CC0/i, spdx: "CC0-1.0", risk: "compatible" },
  { pattern: /All rights reserved/i, spdx: "Proprietary", risk: "incompatible" },
];
