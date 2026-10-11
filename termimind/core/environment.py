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
Environment context inspector for TermiMind.
Discovers host OS, active shell, working directory files, git state, and installed tools.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GitInfo:
    """Git repository metadata for the current working directory."""

    is_repo: bool = False
    branch: str = ""
    is_dirty: bool = False
    has_remote: bool = False
    remote_branch: str = ""


@dataclass
class EnvironmentContext:
    """Comprehensive environment snapshot for command analysis."""

    os_name: str
    os_release: str
    is_windows: bool
    is_linux: bool
    is_macos: bool
    is_wsl: bool
    shell_name: str
    cwd: str
    is_root: bool
    available_tools: List[str] = field(default_factory=list)
    recent_files: List[str] = field(default_factory=list)
    git_info: GitInfo = field(default_factory=GitInfo)
    virtual_env: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert environment context to dictionary."""
        data = asdict(self)
        return data

    def format_summary(self) -> str:
        """Produces a short, readable summary for diagnosis and LLM context."""
        parts = [
            f"OS: {self.os_name} ({self.os_release})",
            f"Shell: {self.shell_name}",
            f"CWD: {self.cwd}",
            f"User: {'Root/Admin' if self.is_root else 'Standard'}",
        ]
        if self.git_info.is_repo:
            dirty = " [dirty]" if self.git_info.is_dirty else ""
            parts.append(f"Git: branch '{self.git_info.branch}'{dirty}")
        if self.virtual_env:
            parts.append(f"Venv: {Path(self.virtual_env).name}")
        return " | ".join(parts)


def detect_wsl() -> bool:
    """Checks whether the execution is occurring inside Windows Subsystem for Linux."""
    if platform.system().lower() != "linux":
        return False
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            content = f.read().lower()
            return "microsoft" in content or "wsl" in content
    except Exception:
        return False


def detect_shell() -> str:
    """Infers the calling shell based on environment variables and parent process."""
    # Check explicitly passed or environment shell variables
    shell_env = os.environ.get("TERMIMIND_SHELL")
    if shell_env:
        return shell_env.lower()

    # PowerShell environment indicators
    if os.environ.get("PSExecutionPolicyPreference") or os.environ.get("PSModulePath"):
        return "powershell"

    shell_path = os.environ.get("SHELL", "")
    if shell_path:
        base = Path(shell_path).name.lower()
        if "zsh" in base:
            return "zsh"
        if "bash" in base:
            return "bash"
        if "fish" in base:
            return "fish"

    if platform.system() == "Windows":
        return "powershell"

    return "bash"


def detect_is_admin() -> bool:
    """Checks if current process has root/administrator privileges."""
    if platform.system() == "Windows":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:
            return False
    else:
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except Exception:
            return False


def inspect_git(cwd: Path) -> GitInfo:
    """Extracts git status in the target directory."""
    if not shutil.which("git"):
        return GitInfo(is_repo=False)

    try:
        # Check if inside git work tree
        rev_parse = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
        )
        if rev_parse.returncode != 0:
            return GitInfo(is_repo=False)

        # Get current branch
        branch_proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
        )
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""

        # Check status for dirty flag
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
        )
        is_dirty = bool(status_proc.stdout.strip())

        # Check upstream
        upstream_proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
        )
        has_remote = upstream_proc.returncode == 0
        remote_branch = upstream_proc.stdout.strip() if has_remote else ""

        return GitInfo(
            is_repo=True,
            branch=branch,
            is_dirty=is_dirty,
            has_remote=has_remote,
            remote_branch=remote_branch,
        )
    except Exception:
        return GitInfo(is_repo=False)


def scan_recent_files(cwd: Path, limit: int = 30) -> List[str]:
    """Retrieves file names in directory for typo matching."""
    try:
        items: List[str] = []
        for entry in cwd.iterdir():
            if entry.name.startswith("."):
                continue
            name = entry.name + ("/" if entry.is_dir() else "")
            items.append(name)
            if len(items) >= limit:
                break
        return items
    except Exception:
        return []


def check_available_tools() -> List[str]:
    """Detects presence of key CLI developer tools in PATH."""
    candidate_tools = [
        "python", "python3", "py", "pip", "pip3", "poetry",
        "node", "npm", "pnpm", "yarn", "bun",
        "git", "docker", "docker-compose",
        "cargo", "rustc", "go",
        "sudo", "systemctl", "curl", "wget",
        "pwsh", "powershell", "bash", "zsh"
    ]
    found: List[str] = []
    for tool in candidate_tools:
        if shutil.which(tool):
            found.append(tool)
    return found


def get_environment(cwd: Optional[Path] = None) -> EnvironmentContext:
    """Builds and returns the full EnvironmentContext."""
    work_dir = (cwd or Path.cwd()).resolve()
    system = platform.system()
    is_win = system == "Windows"
    is_lin = system == "Linux"
    is_mac = system == "Darwin"
    is_wsl = detect_wsl()

    venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_PREFIX")

    return EnvironmentContext(
        os_name=system,
        os_release=platform.release(),
        is_windows=is_win,
        is_linux=is_lin,
        is_macos=is_mac,
        is_wsl=is_wsl,
        shell_name=detect_shell(),
        cwd=str(work_dir),
        is_root=detect_is_admin(),
        available_tools=check_available_tools(),
        recent_files=scan_recent_files(work_dir),
        git_info=inspect_git(work_dir),
        virtual_env=venv,
    )
