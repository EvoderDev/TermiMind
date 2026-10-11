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
Shell failure context capturer for TermiMind.
Stores and recovers terminal execution errors, exit codes, working directories,
and cleans ANSI escape codes for downstream parsing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from termimind.config import get_default_config_dir
from termimind.core.environment import detect_shell


# Regular expression to strip ANSI color and formatting escape codes
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def clean_ansi(text: str) -> str:
    """Removes terminal ANSI color and styling escape sequences."""
    if not text:
        return ""
    return ANSI_ESCAPE_RE.sub("", text).strip()


@dataclass
class FailureRecord:
    """Represents a captured failed terminal command and its diagnostics."""

    command: str
    exit_code: int
    stderr: str
    stdout: str = ""
    cwd: str = ""
    shell: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FailureRecord:
        """Instantiate record safely from dictionary."""
        return cls(
            command=data.get("command", "").strip(),
            exit_code=int(data.get("exit_code", 1)),
            stderr=clean_ansi(data.get("stderr", "")),
            stdout=clean_ansi(data.get("stdout", "")),
            cwd=data.get("cwd", os.getcwd()),
            shell=data.get("shell", ""),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


class ShellCapturer:
    """Handles saving, loading, and inferring failure records across shells."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or get_default_config_dir()
        self.state_file = self.storage_dir / "last_failure.json"

    def ensure_dir(self) -> None:
        """Ensures persistence directory exists."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: FailureRecord) -> None:
        """Persists the failed command event to the session state file."""
        self.ensure_dir()
        record.stderr = clean_ansi(record.stderr)
        record.stdout = clean_ansi(record.stdout)
        if not record.timestamp:
            record.timestamp = datetime.now(timezone.utc).isoformat()
        if not record.shell:
            record.shell = detect_shell()
        if not record.cwd:
            record.cwd = os.getcwd()

        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            # Fallback to temp directory if config dir is unwritable
            temp_file = Path(os.environ.get("TEMP", "/tmp")) / "termimind_last_failure.json"
            try:
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)
                self.state_file = temp_file
            except Exception:
                pass

    def load(self) -> Optional[FailureRecord]:
        """Loads the most recent failed command record."""
        # 1. Primary config state file
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return FailureRecord.from_dict(data)
            except Exception:
                pass

        # 2. Check temp location fallback
        temp_file = Path(os.environ.get("TEMP", "/tmp")) / "termimind_last_failure.json"
        if temp_file.exists():
            try:
                with open(temp_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return FailureRecord.from_dict(data)
            except Exception:
                pass

        return None

    def clear(self) -> None:
        """Removes the stored failure record after resolution."""
        if self.state_file.exists():
            try:
                self.state_file.unlink()
            except Exception:
                pass

        temp_file = Path(os.environ.get("TEMP", "/tmp")) / "termimind_last_failure.json"
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass

    def capture_from_shell_history(self) -> Optional[FailureRecord]:
        """Fallback to inspect recent shell history when hooks haven't written state."""
        shell = detect_shell()
        recent_cmd = ""

        if shell == "powershell":
            # Check PSReadLine history path
            appdata = os.environ.get("APPDATA")
            if appdata:
                hist_path = Path(appdata) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt"
                if hist_path.exists():
                    try:
                        lines = [line.strip() for line in hist_path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
                        if lines:
                            # Skip termimind / tm invocations
                            for line in reversed(lines):
                                if not line.startswith(("tm", "termimind")):
                                    recent_cmd = line
                                    break
                    except Exception:
                        pass
        else:
            # Check ~/.bash_history or ~/.zsh_history
            home = Path.home()
            history_candidates = [
                home / ".bash_history",
                home / ".zsh_history",
                home / ".history",
            ]
            for candidate in history_candidates:
                if candidate.exists():
                    try:
                        lines = [line.strip() for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
                        if lines:
                            for line in reversed(lines):
                                # Zsh history format: ": 1600000000:0;command"
                                if ";" in line and line.startswith(":"):
                                    line = line.split(";", 1)[1].strip()
                                if not line.startswith(("tm", "termimind")):
                                    recent_cmd = line
                                    break
                            if recent_cmd:
                                break
                    except Exception:
                        pass

        if recent_cmd:
            return FailureRecord(
                command=recent_cmd,
                exit_code=1,
                stderr="[Inferred from shell history. Exit status non-zero.]",
                cwd=os.getcwd(),
                shell=shell,
            )

        return None

    def read_piped_stdin(self) -> Optional[str]:
        """Reads piped stderr/stdout from stdin if available."""
        if not sys.stdin.isatty():
            try:
                return sys.stdin.read().strip()
            except Exception:
                return None
        return None
