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
Interactive Rich UI prompt renderer for TermiMind.
Provides styled diagnostic presentation, single-key action dispatch (Enter to run),
clipboard synchronization, and in-place command execution.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from termimind.core.sandbox import RiskLevel, SandboxResult
from termimind.core.shell_capturer import FailureRecord
from termimind.engine.local_fallback import ResolutionResult

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def copy_to_clipboard(text: str) -> bool:
    """Copies text to the system clipboard across platforms."""
    system = platform.system()
    try:
        if system == "Windows":
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE, shell=True)
            proc.communicate(input=text.encode("utf-8"))
            return proc.returncode == 0
        elif system == "Darwin":
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-8"))
            return proc.returncode == 0
        else:
            # Linux / BSD
            if shutil.which("wl-copy"):
                proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                proc.communicate(input=text.encode("utf-8"))
                return proc.returncode == 0
            elif shutil.which("xclip"):
                proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                proc.communicate(input=text.encode("utf-8"))
                return proc.returncode == 0
    except Exception:
        return False
    return False


def get_single_keypress() -> str:
    """Reads a single keypress from standard input without requiring Enter."""
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        return "\r" if not line.strip() else line.strip()[0]

    system = platform.system()
    if system == "Windows":
        try:
            import msvcrt
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                return "enter"
            if ch in ("\x1b", "\x03"):  # Esc or Ctrl+C
                return "esc"
            return ch.lower()
        except Exception:
            try:
                val = input().strip()
                return "enter" if not val else val[0].lower()
            except (KeyboardInterrupt, EOFError):
                return "esc"
    else:
        # Unix/macOS
        try:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                ch = sys.stdin.read(1)
                if ch in ("\r", "\n"):
                    return "enter"
                if ch in ("\x1b", "\x03"):
                    return "esc"
                return ch.lower()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            try:
                val = input().strip()
                return "enter" if not val else val[0].lower()
            except (KeyboardInterrupt, EOFError):
                return "esc"


class TermiMindUI:
    """Main Rich UI controller for command presentation and interactive execution."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def render_proposal(
        self,
        record: FailureRecord,
        resolution: ResolutionResult,
        sandbox: SandboxResult,
    ) -> None:
        """Draws the diagnostic panel, proposal, and safety badge."""
        self.console.print()

        # Header bar
        header_text = Text()
        header_text.append(" [TermiMind] ", style="bold black on bright_cyan")
        header_text.append(f"  v1.0.0 | {resolution.engine}", style="dim")
        self.console.print(header_text)
        self.console.print()

        # Context Grid: Failed Command and Safety Badge
        grid = Table.grid(expand=True)
        grid.add_column(ratio=7)
        grid.add_column(ratio=3, justify="right")

        failed_text = Text()
        failed_text.append("Failed: ", style="bold red")
        failed_text.append(f"{record.command} ", style="bold white")
        failed_text.append(f"(exit code: {record.exit_code})", style="dim red")

        safety_badge = sandbox.badge
        grid.add_row(failed_text, safety_badge)
        self.console.print(grid)

        # Truncated stderr preview if available
        if record.stderr:
            stderr_preview = record.stderr.strip()
            if len(stderr_preview) > 280:
                stderr_preview = stderr_preview[:280] + "..."
            self.console.print(Panel(
                Text(stderr_preview, style="dim white"),
                title="[red]Terminal Error Output[/red]",
                title_align="left",
                border_style="dim red",
                padding=(0, 1),
            ))

        # Proposed Fix Syntax Highlighted Box
        syntax = Syntax(
            resolution.command,
            "bash" if platform.system() != "Windows" else "powershell",
            theme="monokai",
            line_numbers=False,
            word_wrap=True,
        )

        fix_panel = Panel(
            syntax,
            title="[bold green]Suggested Safe Fix[/bold green]",
            title_align="left",
            border_style="bright_green" if sandbox.is_allowed else "bold red",
            padding=(0, 2),
        )
        self.console.print(fix_panel)

        # Explanation & Diagnostics
        info_text = Text()
        info_text.append("[*] Explanation: ", style="bold cyan")
        info_text.append(f"{resolution.explanation}\n", style="white")
        info_text.append("[#] Sandbox: ", style="bold yellow")
        info_text.append(f"{sandbox.reason}", style="dim yellow")
        self.console.print(info_text)
        self.console.print()

    def prompt_user_action(
        self,
        resolution: ResolutionResult,
        sandbox: SandboxResult,
    ) -> str:
        """Prompts the user with available single-key choices."""
        # If blocked by sandbox, user cannot execute via Enter
        if not sandbox.is_allowed:
            self.console.print(
                "[bold red][!] This command is strictly blocked by TermiMind's sandbox safety policy and cannot be executed.[/bold red]"
            )
            self.console.print(
                "[dim]([bold white]c[/bold white]: copy to clipboard | [bold white]q[/bold white]: exit)[/dim] "
            )
            key = get_single_keypress()
            if key == "c":
                return "copy"
            return "cancel"

        # Action bar
        prompt_text = Text()
        prompt_text.append("-> [", style="dim")
        prompt_text.append("Enter", style="bold green")
        prompt_text.append("] Run fix  ", style="dim")

        prompt_text.append("[", style="dim")
        prompt_text.append("e", style="bold yellow")
        prompt_text.append("] Edit  ", style="dim")

        prompt_text.append("[", style="dim")
        prompt_text.append("c", style="bold cyan")
        prompt_text.append("] Copy  ", style="dim")

        if resolution.alternatives:
            prompt_text.append("[", style="dim")
            prompt_text.append("a", style="bold magenta")
            prompt_text.append("] Alt  ", style="dim")

        prompt_text.append("[", style="dim")
        prompt_text.append("q", style="bold red")
        prompt_text.append("] Cancel: ", style="dim")

        self.console.print(prompt_text, end="")
        key = get_single_keypress()
        self.console.print()

        if key in ("enter", "\r", "\n"):
            # If double confirmation required by high risk
            if sandbox.requires_double_confirmation:
                self.console.print(
                    "[bold dark_orange][!] This command has high risk impact. Are you sure? [y/N]: [/bold dark_orange]",
                    end="",
                )
                conf = get_single_keypress()
                self.console.print()
                if conf != "y":
                    return "cancel"
            return "execute"
        elif key == "e":
            return "edit"
        elif key == "c":
            return "copy"
        elif key == "a" and resolution.alternatives:
            return "alternative"
        else:
            return "cancel"

    def prompt_edit_command(self, initial_command: str) -> Optional[str]:
        """Allows inline editing of the proposed fix."""
        try:
            self.console.print("[dim]Edit command and press Enter:[/dim]")
            edited = input(f"> {initial_command}\r> ")
            if not edited.strip():
                return initial_command
            return edited.strip()
        except (KeyboardInterrupt, EOFError):
            return None

    def execute(self, command: str, cwd: Optional[str] = None) -> int:
        """Executes the command in the native shell environment."""
        self.console.print(f"[bold green]>> Running:[/bold green] [white]{command}[/white]")
        self.console.print("[dim]------------------------------------------------[/dim]")

        work_dir = cwd or os.getcwd()
        is_win = platform.system() == "Windows"

        try:
            if is_win:
                # Use powershell if available, else cmd.exe
                shell_cmd = ["powershell.exe", "-NoProfile", "-Command", command]
                proc = subprocess.run(shell_cmd, cwd=work_dir)
            else:
                proc = subprocess.run(command, shell=True, executable="/bin/bash", cwd=work_dir)

            self.console.print("[dim]------------------------------------------------[/dim]")
            if proc.returncode == 0:
                self.console.print("[bold green][OK] Command executed successfully![/bold green]\n")
            else:
                self.console.print(f"[bold yellow]Command finished with exit code {proc.returncode}[/bold yellow]\n")
            return proc.returncode
        except Exception as e:
            self.console.print(f"[bold red]Execution failed: {e}[/bold red]\n")
            return 1
