# Copyright 2026 EvoderDev
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Offline rule-based fallback resolution engine for TermiMind.
Provides zero-latency, deterministic solutions for common shell, git,
Python, Node, Docker, and filesystem command failures without requiring an LLM or API keys.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from termimind.core.environment import EnvironmentContext
from termimind.core.shell_capturer import FailureRecord


@dataclass
class ResolutionResult:
    """Standardized solution proposal returned by resolution engines."""

    command: str
    explanation: str
    confidence: float
    engine: str = "local_fallback"
    alternatives: List[str] = field(default_factory=list)


# Popular Python module name to PyPI package name mappings
PYTHON_MODULE_MAPPING = {
    "cv2": "opencv-python",
    "pil": "pillow",
    "image": "pillow",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "dotenv": "python-dotenv",
    "psycopg2": "psycopg2-binary",
    "crypto": "pycryptodome",
    "dateutil": "python-dateutil",
    "jwt": "pyjwt",
    "serial": "pyserial",
    "magic": "python-magic",
    "openpyxl": "openpyxl",
    "matplotlib": "matplotlib",
    "pandas": "pandas",
    "numpy": "numpy",
    "requests": "requests",
    "rich": "rich",
    "flask": "flask",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
}

# Common shell command typos
COMMON_TYPOS = {
    "sl": "ls",
    "cd..": "cd ..",
    "claer": "clear",
    "clrear": "clear",
    "gerp": "grep",
    "grpe": "grep",
    "mdkir": "mkdir",
    "mkdr": "mkdir",
    "cot": "cat",
    "cta": "cat",
    "pwoershell": "powershell",
    "pyhton": "python",
    "pytohn": "python",
    "pyhton3": "python3",
    "ptthon": "python",
}

# Git sub-command typos
GIT_SUBCOMMAND_TYPOS = {
    "cmmit": "commit",
    "comit": "commit",
    "commt": "commit",
    "chekcout": "checkout",
    "chechout": "checkout",
    "checout": "checkout",
    "brnach": "branch",
    "barnch": "branch",
    "stauts": "status",
    "staus": "status",
    "stat": "status",
    "psuh": "push",
    "pussh": "push",
    "plul": "pull",
    "pulll": "pull",
    "dif": "diff",
    "difff": "diff",
    "stsh": "stash",
    "rebaes": "rebase",
}


class LocalFallbackEngine:
    """Heuristic engine evaluating errors against known patterns."""

    def resolve(self, record: FailureRecord, env: EnvironmentContext) -> Optional[ResolutionResult]:
        """Runs the failed record through all heuristic checks."""
        cmd = record.command.strip()
        stderr = record.stderr.strip()
        stdout = record.stdout.strip()
        full_output = f"{stderr}\n{stdout}".strip()

        # 1. Shell command typo check
        typo_res = self._check_shell_typo(cmd)
        if typo_res:
            return typo_res

        # 2. Git errors and typos
        git_res = self._check_git_issues(cmd, full_output, env)
        if git_res:
            return git_res

        # 3. Python and pip module errors
        python_res = self._check_python_issues(cmd, full_output, env)
        if python_res:
            return python_res

        # 4. Node.js / NPM / PNPM package issues
        node_res = self._check_node_issues(cmd, full_output, env)
        if node_res:
            return node_res

        # 5. Docker issues
        docker_res = self._check_docker_issues(cmd, full_output, env)
        if docker_res:
            return docker_res

        # 6. File not found / typo in referenced file
        file_res = self._check_missing_file_typos(cmd, full_output, env)
        if file_res:
            return file_res

        # 7. Permission denied / sudo suggestion
        perm_res = self._check_permission_issues(cmd, full_output, env)
        if perm_res:
            return perm_res

        return None

    def _check_shell_typo(self, cmd: str) -> Optional[ResolutionResult]:
        """Detects simple shell command mistypes."""
        tokens = cmd.split()
        if not tokens:
            return None

        first = tokens[0].lower()
        if first in COMMON_TYPOS:
            fixed_first = COMMON_TYPOS[first]
            fixed_cmd = f"{fixed_first} {' '.join(tokens[1:])}".strip()
            return ResolutionResult(
                command=fixed_cmd,
                explanation=f"Corrected common typo '{first}' -> '{fixed_first}'.",
                confidence=0.95,
                engine="local_fallback",
            )
        return None

    def _check_git_issues(
        self, cmd: str, output: str, env: EnvironmentContext
    ) -> Optional[ResolutionResult]:
        """Resolves common Git errors."""
        tokens = cmd.split()
        if not tokens or tokens[0].lower() != "git":
            return None

        # A. Git sub-command typo check: e.g. "git cmmit -m ..."
        if len(tokens) >= 2:
            sub = tokens[1].lower()
            if sub in GIT_SUBCOMMAND_TYPOS:
                fixed_sub = GIT_SUBCOMMAND_TYPOS[sub]
                fixed_cmd = f"git {fixed_sub} {' '.join(tokens[2:])}".strip()
                return ResolutionResult(
                    command=fixed_cmd,
                    explanation=f"Corrected Git subcommand typo '{sub}' -> '{fixed_sub}'.",
                    confidence=0.98,
                    engine="local_fallback",
                )

        # B. Not a git repository
        if "fatal: not a git repository" in output:
            return ResolutionResult(
                command="git init",
                explanation="Directory is not a git repository. Initialize git repo first.",
                confidence=0.95,
                engine="local_fallback",
            )

        # C. No upstream branch
        # "fatal: The current branch <branch> has no upstream branch."
        upstream_match = re.search(
            r"The current branch (\S+) has no upstream branch", output
        )
        if upstream_match or "git push --set-upstream" in output:
            branch = upstream_match.group(1) if upstream_match else env.git_info.branch or "main"
            return ResolutionResult(
                command=f"git push --set-upstream origin {branch}",
                explanation=f"Set upstream tracking branch for '{branch}' and push.",
                confidence=0.99,
                engine="local_fallback",
            )

        # D. Need to pull before push
        if "Updates were rejected because the remote contains work" in output or "fetch first" in output:
            branch = env.git_info.branch or "main"
            return ResolutionResult(
                command=f"git pull --rebase origin {branch}",
                explanation="Remote contains changes. Rebase latest commits from remote before pushing.",
                confidence=0.92,
                engine="local_fallback",
                alternatives=[f"git pull origin {branch}"],
            )

        # E. Pathspec did not match any file(s)
        pathspec_match = re.search(r"pathspec '([^']+)' did not match any file", output)
        if pathspec_match and len(tokens) >= 3 and tokens[1] in ("checkout", "switch"):
            target = pathspec_match.group(1)
            # Suggest creating the new branch
            return ResolutionResult(
                command=f"git checkout -b {target}",
                explanation=f"Branch '{target}' does not exist yet. Create and switch to new branch.",
                confidence=0.88,
                engine="local_fallback",
                alternatives=[f"git switch -c {target}"],
            )

        return None

    def _check_python_issues(
        self, cmd: str, output: str, env: EnvironmentContext
    ) -> Optional[ResolutionResult]:
        """Resolves missing Python packages and interpreter errors."""
        # A. ModuleNotFoundError: No module named 'xyz'
        mod_match = re.search(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", output)
        if not mod_match:
            mod_match = re.search(r"ImportError:\s+No module named ['\"]?([a-zA-Z0-9_\.]+)['\"]?", output)

        if mod_match:
            raw_module = mod_match.group(1).split(".")[0].lower()
            pkg_name = PYTHON_MODULE_MAPPING.get(raw_module, raw_module)

            pip_cmd = "pip"
            if "python3" in env.available_tools and not env.is_windows:
                pip_cmd = "pip3"
            elif env.virtual_env:
                pip_cmd = "pip"

            return ResolutionResult(
                command=f"{pip_cmd} install {pkg_name}",
                explanation=f"Missing Python package. Install '{pkg_name}' (imported as '{raw_module}').",
                confidence=0.95,
                engine="local_fallback",
                alternatives=[f"python -m pip install {pkg_name}"],
            )

        # B. Python command not found
        if any(term in output.lower() for term in ["python: command not found", "the term 'python' is not recognized"]):
            if "python3" in env.available_tools:
                fixed_cmd = re.sub(r"^python\b", "python3", cmd)
                return ResolutionResult(
                    command=fixed_cmd,
                    explanation="'python' not found in PATH, but 'python3' is available.",
                    confidence=0.90,
                    engine="local_fallback",
                )
            if "py" in env.available_tools:
                fixed_cmd = re.sub(r"^python\b", "py", cmd)
                return ResolutionResult(
                    command=fixed_cmd,
                    explanation="'python' not found in PATH, but Windows Python Launcher 'py' is available.",
                    confidence=0.90,
                    engine="local_fallback",
                )

        return None

    def _check_node_issues(
        self, cmd: str, output: str, env: EnvironmentContext
    ) -> Optional[ResolutionResult]:
        """Resolves Node.js and NPM package manager issues."""
        # A. Cannot find module 'xyz'
        mod_match = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", output)
        if mod_match:
            module_name = mod_match.group(1)
            # Avoid internal relative files like ./utils
            if not module_name.startswith((".", "/")):
                pkg_manager = "pnpm" if "pnpm" in env.available_tools and Path("pnpm-lock.yaml").exists() else "npm"
                action = "add" if pkg_manager == "pnpm" else "install"
                return ResolutionResult(
                    command=f"{pkg_manager} {action} {module_name}",
                    explanation=f"Missing Node.js package dependency '{module_name}'.",
                    confidence=0.92,
                    engine="local_fallback",
                )

        # B. Missing package.json
        if "ENOENT: no such file or directory, open 'package.json'" in output:
            return ResolutionResult(
                command="npm init -y",
                explanation="No package.json found. Initialize standard Node.js package manifest.",
                confidence=0.94,
                engine="local_fallback",
            )

        # C. NPM script typo
        # "npm error Missing script: "bulid""
        missing_script_match = re.search(r"Missing script:\s*['\"]([^'\"]+)['\"]", output)
        if missing_script_match:
            typo_script = missing_script_match.group(1)
            common_scripts = ["build", "dev", "start", "test", "lint", "format", "serve"]
            closest = difflib.get_close_matches(typo_script, common_scripts, n=1, cutoff=0.6)
            if closest:
                fixed_cmd = cmd.replace(typo_script, closest[0])
                return ResolutionResult(
                    command=fixed_cmd,
                    explanation=f"NPM script typo '{typo_script}' -> '{closest[0]}'.",
                    confidence=0.91,
                    engine="local_fallback",
                )

        return None

    def _check_docker_issues(
        self, cmd: str, output: str, env: EnvironmentContext
    ) -> Optional[ResolutionResult]:
        """Resolves Docker daemon connectivity and container errors."""
        if "Cannot connect to the Docker daemon" in output or "Is the docker daemon running?" in output:
            if env.is_linux and not env.is_wsl:
                return ResolutionResult(
                    command="sudo systemctl start docker",
                    explanation="Docker daemon service is stopped. Start Docker system service.",
                    confidence=0.94,
                    engine="local_fallback",
                )
            return ResolutionResult(
                command="docker info",
                explanation="Docker daemon is not running. Please start Docker Desktop or the Docker service.",
                confidence=0.85,
                engine="local_fallback",
            )
        return None

    def _check_missing_file_typos(
        self, cmd: str, output: str, env: EnvironmentContext
    ) -> Optional[ResolutionResult]:
        """Fuzzy matches missing file names in arguments against directory contents."""
        has_file_err = any(
            err in output.lower()
            for err in [
                "no such file or directory",
                "cannot open file",
                "cannot find file",
                "cannot find the path specified",
                "the system cannot find the file specified",
            ]
        )
        if not has_file_err or not env.recent_files:
            return None

        clean_files = [f.rstrip("/") for f in env.recent_files]

        # 1. Try regex extraction
        extracted_missing: Optional[str] = None
        match_before = re.search(r"[:\s]([a-zA-Z0-9_\.\-]+):\s*(?:No such file or directory|cannot open file)", output, re.IGNORECASE)
        if match_before:
            extracted_missing = match_before.group(1).strip()
        else:
            match_after = re.search(r"(?:No such file or directory|cannot open file|Cannot find file)['\":\s]+([^\s'\"]+)", output, re.IGNORECASE)
            if match_after:
                extracted_missing = match_after.group(1).strip()

        candidates = [extracted_missing] if extracted_missing else []
        tokens = cmd.split()
        if len(tokens) > 1:
            for tok in tokens[1:]:
                clean_tok = tok.strip("'\"")
                if "." in clean_tok and clean_tok not in candidates:
                    candidates.append(clean_tok)

        for candidate in candidates:
            if not candidate:
                continue
            missing_name = Path(candidate).name
            matches = difflib.get_close_matches(missing_name, clean_files, n=1, cutoff=0.60)
            if matches and matches[0] != missing_name:
                fixed_cmd = cmd.replace(missing_name, matches[0])
                return ResolutionResult(
                    command=fixed_cmd,
                    explanation=f"Corrected filename typo '{missing_name}' -> '{matches[0]}'.",
                    confidence=0.89,
                    engine="local_fallback",
                )
        return None

    def _check_permission_issues(
        self, cmd: str, output: str, env: EnvironmentContext
    ) -> Optional[ResolutionResult]:
        """Detects permission denied errors and suggests privilege elevation."""
        if any(term in output.lower() for term in ["permission denied", "eacces", "operation not permitted"]):
            if not env.is_windows and not env.is_root and "sudo" in env.available_tools:
                if not cmd.startswith("sudo"):
                    return ResolutionResult(
                        command=f"sudo {cmd}",
                        explanation="Operation failed due to missing permissions. Rerun with elevated privileges (sudo).",
                        confidence=0.90,
                        engine="local_fallback",
                    )
        return None
