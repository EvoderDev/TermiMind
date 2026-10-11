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
TermiMind Shell Hook Listener.
Monitors shell execution events, captures failed command records dispatched by
Bash, Zsh, and PowerShell hooks, and automatically orchestrates diagnosis and repair.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from rich.console import Console

from termimind.config import TermiMindConfig, get_config
from termimind.core.environment import get_environment
from termimind.core.sandbox import RiskLevel, SandboxEvaluator
from termimind.core.shell_capturer import FailureRecord, ShellCapturer
from termimind.engine.resolver import CommandResolver, ResolutionResult
from termimind.ui.prompt_render import TermiMindUI

logger = logging.getLogger("termimind.listener")


@dataclass
class ListenerEvent:
    """Represents a detected shell hook failure event."""
    timestamp: float
    record: FailureRecord
    source: str = "hook_state_file"


class ShellHookListener:
    """
    Continuous listener that monitors shell hook failure records,
    notifies the developer, and coordinates command repairs.
    """

    def __init__(
        self,
        config: Optional[TermiMindConfig] = None,
        console: Optional[Console] = None,
        storage_dir: Optional[Path] = None,
    ):
        self.config = config or get_config()
        self.console = console or Console(safe_box=True)
        self.capturer = ShellCapturer(storage_dir=storage_dir)
        self.ui = TermiMindUI(self.console)
        self.resolver = CommandResolver(self.config)
        self._last_processed_mtime: float = 0.0
        self._running: bool = False

    def process_latest_failure(
        self,
        auto_fix: bool = False,
        dry_run: bool = False,
        interactive: bool = True,
    ) -> Optional[int]:
        """
        Reads the most recent failure event recorded by shell hooks and processes a fix.
        Returns the exit code if executed, or None if no new failure.
        """
        record = self.capturer.load()
        if not record or not record.command:
            return None

        # Check file timestamp to avoid reprocessing the same event repeatedly
        state_file = self.capturer.state_file
        if state_file.exists():
            try:
                mtime = state_file.stat().st_mtime
                if mtime <= self._last_processed_mtime:
                    return None
                self._last_processed_mtime = mtime
            except Exception:
                pass

        self.console.print(
            f"\n[bold yellow]⚡ Shell Hook Event Detected:[/bold yellow] "
            f"[dim]Command '{record.command}' exited with code {record.exit_code}[/dim]"
        )

        env = get_environment()
        resolution, sandbox = self.resolver.resolve(record, env)

        if dry_run:
            self.ui.render_proposal(record, resolution, sandbox)
            self.console.print(f"[bold cyan]Fix command:[/bold cyan] {resolution.command}\n")
            return 0

        if auto_fix:
            if not sandbox.is_allowed:
                self.console.print(
                    "[bold red]Cannot auto-execute: Command is blocked by sandbox safety policy.[/bold red]"
                )
                return 1
            self.console.print(f"[bold green]Auto-executing fix:[/bold green] {resolution.command}")
            exit_code = self.ui.execute(resolution.command, cwd=record.cwd)
            self.capturer.clear()
            return exit_code

        if interactive:
            self.ui.render_proposal(record, resolution, sandbox)
            action = self.ui.prompt_user_action(resolution, sandbox)
            if action == "execute":
                exit_code = self.ui.execute(resolution.command, cwd=record.cwd)
                self.capturer.clear()
                return exit_code
            elif action == "copy":
                from termimind.ui.prompt_render import copy_to_clipboard
                copy_to_clipboard(resolution.command)
                self.console.print("[bold green][OK] Copied fix to clipboard![/bold green]\n")
                return 0
            else:
                self.console.print("[dim]Fix dismissed.[/dim]")
                return 0

        return 0

    def start_listening(
        self,
        poll_interval: float = 0.5,
        auto_fix: bool = False,
        dry_run: bool = False,
        interactive: bool = True,
        max_events: Optional[int] = None,
        process_existing: bool = True,
    ) -> None:
        """
        Starts the event polling loop. Blocks until KeyboardInterrupt or max_events reached.
        """
        self._running = True
        event_count = 0

        # Only prime initial mtime if explicitly ignoring existing state
        if not process_existing and self.capturer.state_file.exists():
            try:
                self._last_processed_mtime = self.capturer.state_file.stat().st_mtime
            except Exception:
                pass

        self.console.print("\n[bold cyan]╔══════════════════════════════════════════════════════════╗[/bold cyan]")
        self.console.print("[bold cyan]║          TermiMind Shell Hook Listener Active           ║[/bold cyan]")
        self.console.print("[bold cyan]╚══════════════════════════════════════════════════════════╝[/bold cyan]")
        self.console.print(f"[dim]Monitoring shell hook state at: {self.capturer.state_file}[/dim]")
        self.console.print(
            f"[dim]Mode: {'Auto-Fix' if auto_fix else 'Dry-Run' if dry_run else 'Interactive'} | "
            f"Poll: {poll_interval}s[/dim]\n"
            "[dim]Press Ctrl+C to terminate listener.[/dim]\n"
        )

        try:
            while self._running:
                if self.capturer.state_file.exists():
                    exit_code = self.process_latest_failure(
                        auto_fix=auto_fix,
                        dry_run=dry_run,
                        interactive=interactive,
                    )
                    if exit_code is not None:
                        event_count += 1
                        if max_events and event_count >= max_events:
                            break
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.console.print("\n[dim]TermiMind Shell Hook Listener stopped by user.[/dim]")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stops the active listener loop."""
        self._running = False
