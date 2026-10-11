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
Sandbox and command safety evaluator for TermiMind.
Classifies commands by risk level, detects destructive operations,
and strictly blocks dangerous or malicious terminal instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class RiskLevel(str, Enum):
    """Safety classification for suggested terminal commands."""

    SAFE = "SAFE"
    CAUTION = "CAUTION"
    DANGEROUS = "DANGEROUS"
    BLOCKED = "BLOCKED"


@dataclass
class SandboxResult:
    """Outcome of command sandbox inspection."""

    is_allowed: bool
    risk_level: RiskLevel
    reason: str
    matched_pattern: Optional[str] = None
    requires_double_confirmation: bool = False

    @property
    def badge(self) -> str:
        """Visual Rich badge string."""
        if self.risk_level == RiskLevel.SAFE:
            return "[bold green][SAFE][/bold green]"
        if self.risk_level == RiskLevel.CAUTION:
            return "[bold yellow][CAUTION][/bold yellow]"
        if self.risk_level == RiskLevel.DANGEROUS:
            return "[bold dark_orange][DANGEROUS][/bold dark_orange]"
        return "[bold red][BLOCKED - PROHIBITED][/bold red]"


class SandboxEvaluator:
    """Evaluates commands against built-in and user-configured security rules."""

    # Unconditionally blocked patterns that could cause catastrophic system destruction or exfiltration
    HARD_BLOCKED_PATTERNS = [
        # Root / Home directory recursive wipe (Unix)
        (r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(?:/|/\*|~|~\*|\.\.|\.\./)(?:\s|$|[;&|])", "Catastrophic file deletion targeting root or home directory"),
        (r"\brm\s+.*-(?:recursive|no-preserve-root).*(?:/|/\*|~|~\*)(?:\s|$|[;&|])", "Recursive wipe targeting root filesystem"),
        
        # Windows drive wipe
        (r"\b(?:del|erase)\s+(?:/[a-zA-Z]+\s+)*[A-Za-z]:\\(?:\*|\*\.\*)?(?:\s|$|[;&|])", "Mass disk wipe on Windows drive root"),
        (r"\bRemove-Item\s+.*-(?:Recurse|Force)\s+.*(?:[A-Za-z]:\\(?:\*|\*\.\*)?|/(?:\s|$|[;&|]))", "Recursive forced removal of drive root in PowerShell"),
        (r"\bRemove-Item\s+.*(?:[A-Za-z]:\\(?:\*|\*\.\*)?|/(?:\s|$|[;&|])).*-(?:Recurse|Force)", "Recursive forced removal of drive root in PowerShell"),
        
        # Fork bombs
        (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", "Classic Bash fork bomb detected"),
        (r"%0\|%0", "Windows batch fork bomb detected"),
        
        # Direct raw disk writing
        (r"\bdd\s+.*of=(?:/dev/sd[a-z]|/dev/nvme[0-9]|/dev/disk)", "Direct write to raw block storage device"),
        (r"\bmkfs(?:\.[a-z0-9]+)?\s+/dev/", "Raw disk filesystem format"),
        (r"\bformat\s+[A-Za-z]:\s*/[yY]", "Unattended Windows disk format"),
        
        # Dangerous remote execution pipes
        (r"\b(?:curl|wget|fetch|irm)\s+[^|]+\|\s*(?:sudo\s+)?(?:bash|sh|zsh|ksh|iex|powershell)\b", "Arbitrary remote script piped directly into shell interpreter"),
        
        # Global insecure permissions
        (r"\bchmod\s+-[rR]\s+777\s+/\b", "Recursive global 777 permission on root directory"),
        
        # Sensitive credential harvesting / exfiltration
        (r"\bcat\s+~?/\.ssh/id_[a-zA-Z0-9_-]+\b", "Direct access to private SSH authentication key"),
        (r"\btype\s+.*\\\.ssh\\id_[a-zA-Z0-9_-]+\b", "Direct access to private SSH key on Windows"),
        (r"\bcat\s+/etc/shadow\b", "Attempt to dump system password hashes"),
    ]

    # Dangerous patterns (allowed only if user explicitly proceeds with extra warning)
    DANGEROUS_PATTERNS = [
        (r"\bgit\s+push\s+.*(?:--force|-f)\b", "Force-pushing git branches may overwrite remote commits"),
        (r"\bgit\s+reset\s+--hard\b", "Hard git reset discards all uncommitted changes"),
        (r"\bgit\s+clean\s+-[a-zA-Z]*f[a-zA-Z]*\b", "Forced git clean deletes untracked working files"),
        (r"\brm\s+-(?:r[fv]|v?rf?)\s+[a-zA-Z0-9_-]+", "Recursive directory deletion"),
        (r"\bRemove-Item\s+.*-Recurse\b", "PowerShell recursive item deletion"),
        (r"\bkill\s+-9\s+\d+\b", "Force killing system process"),
        (r"\bStop-Process\s+.*-Force\b", "PowerShell forced process termination"),
        (r"\bDROP\s+DATABASE\b", "SQL drop database statement"),
    ]

    # Caution patterns (modifies environment or configuration)
    CAUTION_PATTERNS = [
        (r"\bgit\s+stash\s+(?:drop|clear)\b", "Dropping git stash entry"),
        (r"\b(?:npm|pnpm|yarn)\s+(?:uninstall|remove)\b", "Removing package dependency"),
        (r"\bpip\s+uninstall\b", "Uninstalling Python package"),
        (r"\bchmod\s+", "Modifying file permissions"),
        (r"\bchown\s+", "Modifying file ownership"),
        (r"\bsudo\s+", "Executing with superuser privileges"),
        (r"\bdocker\s+(?:rm|rmi|system\s+prune)\b", "Removing Docker containers, images or pruning system"),
    ]

    def __init__(self, safety_mode: str = "strict", custom_blocked: Optional[List[str]] = None):
        self.safety_mode = safety_mode.lower()
        self.custom_blocked = custom_blocked or []

    def evaluate(self, command: str) -> SandboxResult:
        """Inspects a command string and returns its safety assessment."""
        cmd = command.strip()
        if not cmd:
            return SandboxResult(
                is_allowed=False,
                risk_level=RiskLevel.BLOCKED,
                reason="Empty command cannot be executed.",
            )

        # 1. Check custom user-configured blocked regexes
        for pattern in self.custom_blocked:
            try:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return SandboxResult(
                        is_allowed=False,
                        risk_level=RiskLevel.BLOCKED,
                        reason=f"Blocked by custom user safety rule matching: '{pattern}'",
                        matched_pattern=pattern,
                    )
            except re.error:
                continue

        # 2. Check hard blocked destructive patterns
        for pattern, reason in self.HARD_BLOCKED_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return SandboxResult(
                    is_allowed=False,
                    risk_level=RiskLevel.BLOCKED,
                    reason=f"CRITICAL SAFETY VIOLATION: {reason}",
                    matched_pattern=pattern,
                )

        # 3. Check dangerous patterns
        for pattern, reason in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                if self.safety_mode == "strict":
                    return SandboxResult(
                        is_allowed=True,
                        risk_level=RiskLevel.DANGEROUS,
                        reason=f"HIGH RISK: {reason}. Requires deliberate confirmation.",
                        matched_pattern=pattern,
                        requires_double_confirmation=True,
                    )
                return SandboxResult(
                    is_allowed=True,
                    risk_level=RiskLevel.DANGEROUS,
                    reason=reason,
                    matched_pattern=pattern,
                    requires_double_confirmation=False,
                )

        # 4. Check caution patterns
        for pattern, reason in self.CAUTION_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return SandboxResult(
                    is_allowed=True,
                    risk_level=RiskLevel.CAUTION,
                    reason=reason,
                    matched_pattern=pattern,
                    requires_double_confirmation=False,
                )

        # If none of the safety flags triggered, command is considered SAFE
        return SandboxResult(
            is_allowed=True,
            risk_level=RiskLevel.SAFE,
            reason="Command inspected and verified safe by sandbox policy.",
        )
