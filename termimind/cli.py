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
TermiMind Command Line Interface.
Entrypoint for `termimind` and `tm` commands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from termimind import __author__, __license__, __version__
from termimind.config import get_config, get_config_manager
from termimind.core.environment import get_environment
from termimind.core.sandbox import RiskLevel, SandboxEvaluator
from termimind.core.shell_capturer import FailureRecord, ShellCapturer
from termimind.engine.resolver import CommandResolver
from termimind.ui.prompt_render import TermiMindUI, copy_to_clipboard

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

console = Console(safe_box=True)


def handle_fix(args: argparse.Namespace) -> int:
    """Handles the primary command diagnosis and fix workflow."""
    config = get_config()
    capturer = ShellCapturer()
    ui = TermiMindUI(console)

    if args.local:
        config.prefer_local = True

    # If called from automatic shell hook and auto-trigger is disabled, exit silently
    if getattr(args, "from_hook", False) and not config.auto_trigger:
        return 0

    record: Optional[FailureRecord] = None

    # 1. Check explicit arguments
    if args.command:
        record = FailureRecord(
            command=args.command,
            exit_code=args.exit_code,
            stderr=args.stderr or "",
        )
    else:
        # 2. Check piped stdin
        piped_err = capturer.read_piped_stdin()
        if piped_err:
            history_rec = capturer.capture_from_shell_history()
            cmd = history_rec.command if history_rec else "unknown-command"
            record = FailureRecord(
                command=cmd,
                exit_code=1,
                stderr=piped_err,
            )

    # 3. Check persistent failure record written by hook
    if not record:
        record = capturer.load()

    # 4. Fallback to shell history
    if not record:
        record = capturer.capture_from_shell_history()

    if not record or not record.command:
        console.print("[yellow]No recent command failure detected.[/yellow]")
        console.print("[dim]Run a failing command or use 'tm fix --command \"<cmd>\" --stderr \"<err>\"'[/dim]")
        return 0

    env = get_environment()
    resolver = CommandResolver(config)

    resolution, sandbox = resolver.resolve(record, env)

    # In dry-run mode, display fix and return
    if args.dry_run:
        ui.render_proposal(record, resolution, sandbox)
        console.print(f"[bold cyan]Fix command:[/bold cyan] {resolution.command}")
        return 0

    # In auto-confirm (--yes) mode
    if args.yes:
        if not sandbox.is_allowed:
            console.print("[bold red]Cannot auto-execute: Command is blocked by sandbox safety policy.[/bold red]")
            return 1
        return ui.execute(resolution.command, cwd=record.cwd)

    # Interactive flow
    current_resolution = resolution
    while True:
        ui.render_proposal(record, current_resolution, sandbox)
        action = ui.prompt_user_action(current_resolution, sandbox)

        if action == "execute":
            exit_code = ui.execute(current_resolution.command, cwd=record.cwd)
            capturer.clear()
            return exit_code

        elif action == "edit":
            edited_cmd = ui.prompt_edit_command(current_resolution.command)
            if edited_cmd:
                sandbox_eval = SandboxEvaluator(
                    safety_mode=config.safety_mode,
                    custom_blocked=config.blocked_patterns,
                ).evaluate(edited_cmd)
                current_resolution.command = edited_cmd
                sandbox = sandbox_eval

        elif action == "copy":
            if copy_to_clipboard(current_resolution.command):
                console.print("[bold green][OK] Copied fix to clipboard![/bold green]\n")
            else:
                console.print(f"[dim]Command to copy:[/dim] [white]{current_resolution.command}[/white]\n")
            return 0

        elif action == "alternative":
            if current_resolution.alternatives:
                alt = current_resolution.alternatives.pop(0)
                current_resolution.alternatives.append(current_resolution.command)
                current_resolution.command = alt
                sandbox = SandboxEvaluator(
                    safety_mode=config.safety_mode,
                    custom_blocked=config.blocked_patterns,
                ).evaluate(alt)

        else:  # cancel
            console.print("[dim]Fix dismissed.[/dim]")
            return 0


def handle_record(args: argparse.Namespace) -> int:
    """Stores a failure event from shell hooks."""
    capturer = ShellCapturer()
    record = FailureRecord(
        command=args.command or "",
        exit_code=args.exit_code,
        stderr=args.stderr or "",
        stdout=args.stdout or "",
        cwd=args.cwd or "",
        shell=args.shell or "",
    )
    capturer.save(record)
    return 0


def handle_sandbox(args: argparse.Namespace) -> int:
    """Tests a command against sandbox security rules."""
    config = get_config()
    evaluator = SandboxEvaluator(
        safety_mode=config.safety_mode,
        custom_blocked=config.blocked_patterns,
    )
    result = evaluator.evaluate(args.command)

    console.print()
    console.print(f"[bold]Command:[/bold] {args.command}")
    console.print(f"[bold]Rating:[/bold]  {result.badge}")
    console.print(f"[bold]Allowed:[/bold] {'[green]Yes[/green]' if result.is_allowed else '[red]No[/red]'}")
    console.print(f"[bold]Reason:[/bold]  {result.reason}")
    if result.matched_pattern:
        console.print(f"[dim]Matched Pattern: {result.matched_pattern}[/dim]")
    console.print()
    return 0 if result.is_allowed else 1


def handle_config(args: argparse.Namespace) -> int:
    """Manages TermiMind settings."""
    cfg_mgr = get_config_manager()
    cfg = cfg_mgr.get()

    if args.action == "list" or not args.action:
        console.print("\n[bold cyan]TermiMind Configuration Settings:[/bold cyan]")
        for k, v in cfg.to_dict().items():
            if k == "api_key" and v:
                display_v = v[:4] + "..." + v[-4:] if len(v) > 8 else "********"
            else:
                display_v = str(v)
            console.print(f"  [bold white]{k}:[/bold white] [dim]{display_v}[/dim]")
        console.print(f"\n[dim]Config path: {cfg_mgr.config_file}[/dim]\n")
        return 0

    if args.action == "get":
        if not args.key:
            console.print("[red]Error: key name is required for get.[/red]")
            return 1
        val = getattr(cfg, args.key, None)
        if val is None:
            console.print(f"[red]Unknown configuration key: {args.key}[/red]")
            return 1
        console.print(str(val))
        return 0

    if args.action == "set":
        if not args.key or args.value is None:
            console.print("[red]Error: key and value are required for set.[/red]")
            return 1
        if cfg_mgr.set_value(args.key, args.value):
            console.print(f"[green][OK] Set '{args.key}' to '{args.value}'[/green]")
            return 0
        else:
            console.print(f"[red]Failed to set unknown key: {args.key}[/red]")
            return 1

    return 0


def handle_hook(args: argparse.Namespace) -> int:
    """Displays or installs shell hooks."""
    shell = args.shell.lower()
    hooks_dir = Path(__file__).resolve().parent.parent / "hooks"

    hook_map = {
        "bash": hooks_dir / "termimind.bash",
        "zsh": hooks_dir / "termimind.zsh",
        "powershell": hooks_dir / "termimind.ps1",
        "ps1": hooks_dir / "termimind.ps1",
    }

    if shell not in hook_map:
        console.print(f"[red]Unsupported shell '{shell}'. Supported: bash, zsh, powershell[/red]")
        return 1

    hook_file = hook_map[shell]
    if not hook_file.exists():
        console.print(f"[red]Hook script not found at {hook_file}[/red]")
        return 1

    content = hook_file.read_text(encoding="utf-8")
    if args.print:
        sys.stdout.write(content)
        return 0

    console.print(f"\n[bold cyan]TermiMind Hook Setup for {shell.capitalize()}:[/bold cyan]")
    if shell in ("powershell", "ps1"):
        console.print(f"Add the following line to your PowerShell profile ([dim]$PROFILE[/dim]):")
        console.print(f"[bold green]. \"{hook_file}\"[/bold green]")
    elif shell == "bash":
        console.print("Add the following line to your [dim]~/.bashrc[/dim]:")
        console.print(f"[bold green]source \"{hook_file}\"[/bold green]")
    elif shell == "zsh":
        console.print("Add the following line to your [dim]~/.zshrc[/dim]:")
        console.print(f"[bold green]source \"{hook_file}\"[/bold green]")
    console.print()
    return 0


def handle_listen(args: argparse.Namespace) -> int:
    """Runs the shell hook listener loop that monitors for failed command events."""
    from termimind.core.shell_listener import ShellHookListener

    config = get_config()
    listener = ShellHookListener(config=config, console=console)
    listener.start_listening(
        poll_interval=args.interval,
        auto_fix=args.auto_fix,
        dry_run=args.dry_run,
        interactive=not args.auto_fix,
        max_events=1 if args.once else None,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Constructs the argument parser for TermiMind CLI."""
    parser = argparse.ArgumentParser(
        prog="termimind",
        description="TermiMind: AI-powered, sandbox-protected terminal command fixer.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"TermiMind {__version__} (Apache 2.0 - {__author__})")

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # fix subcommand
    fix_p = subparsers.add_parser("fix", help="Diagnose and propose fix for terminal command failure")
    fix_p.add_argument("-c", "--command", help="Failing command line")
    fix_p.add_argument("-e", "--stderr", help="Captured stderr message")
    fix_p.add_argument("-x", "--exit-code", type=int, default=1, help="Command return code")
    fix_p.add_argument("-y", "--yes", action="store_true", help="Auto-run fix without confirmation")
    fix_p.add_argument("-d", "--dry-run", action="store_true", help="Display fix only without prompt")
    fix_p.add_argument("--local", action="store_true", help="Force offline local heuristic engine")
    fix_p.add_argument("--from-hook", action="store_true", help="Invoked from shell hook event")

    # record subcommand
    rec_p = subparsers.add_parser("record", help="Record failure context from shell hooks")
    rec_p.add_argument("-c", "--command", required=True, help="Executed command")
    rec_p.add_argument("-x", "--exit-code", type=int, default=1, help="Exit code")
    rec_p.add_argument("-e", "--stderr", default="", help="Error message")
    rec_p.add_argument("-o", "--stdout", default="", help="Standard output")
    rec_p.add_argument("--cwd", default="", help="Working directory")
    rec_p.add_argument("--shell", default="", help="Active shell")

    # listen subcommand
    lst_p = subparsers.add_parser("listen", help="Monitor shell hooks and automatically trigger command repair")
    lst_p.add_argument("--auto-fix", action="store_true", help="Automatically execute safe proposed fixes")
    lst_p.add_argument("-d", "--dry-run", action="store_true", help="Display diagnoses without interactive prompt")
    lst_p.add_argument("-i", "--interval", type=float, default=0.5, help="Polling interval in seconds (default: 0.5)")
    lst_p.add_argument("--once", action="store_true", help="Process at most one event then exit")

    # sandbox subcommand
    sb_p = subparsers.add_parser("sandbox", help="Evaluate command safety with the sandbox")
    sb_p.add_argument("command", help="Command string to evaluate")

    # config subcommand
    cfg_p = subparsers.add_parser("config", help="View or modify TermiMind configuration")
    cfg_p.add_argument("action", nargs="?", default="list", choices=["list", "get", "set"], help="Action to perform")
    cfg_p.add_argument("key", nargs="?", help="Configuration key")
    cfg_p.add_argument("value", nargs="?", help="New value for configuration key")

    # hook subcommand
    hk_p = subparsers.add_parser("hook", help="Inspect and install shell hooks")
    hk_p.add_argument("shell", choices=["bash", "zsh", "powershell", "ps1"], help="Shell type")
    hk_p.add_argument("-p", "--print", action="store_true", help="Print raw hook script to stdout")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint dispatcher."""
    parser = build_parser()
    args_list = argv if argv is not None else sys.argv[1:]

    # If invoked without any subcommand (e.g. `tm` or `termimind`), default to `fix`
    if not args_list or args_list[0] not in ["fix", "record", "listen", "sandbox", "config", "hook", "-h", "--help", "-v", "--version"]:
        args_list = ["fix"] + args_list

    try:
        args = parser.parse_args(args_list)
        if args.subcommand == "fix" or not args.subcommand:
            return handle_fix(args)
        elif args.subcommand == "record":
            return handle_record(args)
        elif args.subcommand == "listen":
            return handle_listen(args)
        elif args.subcommand == "sandbox":
            return handle_sandbox(args)
        elif args.subcommand == "config":
            return handle_config(args)
        elif args.subcommand == "hook":
            return handle_hook(args)
        return 0
    except KeyboardInterrupt:
        console.print("\n[dim]TermiMind operation cancelled by user.[/dim]")
        return 130
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
