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
Unit tests for TermiMind CLI entrypoints and argument handling.
"""

from termimind.cli import build_parser, main


def test_cli_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["fix", "--dry-run"])
    assert args.subcommand == "fix"
    assert args.dry_run is True


def test_cli_sandbox_subcommand():
    parser = build_parser()
    args = parser.parse_args(["sandbox", "rm -rf /"])
    assert args.subcommand == "sandbox"
    assert args.command == "rm -rf /"


def test_cli_dry_run_execution():
    exit_code = main(["fix", "--command", "sl", "--stderr", "sl: command not found", "--dry-run", "--local"])
    assert exit_code == 0


def test_cli_sandbox_eval_dangerous():
    # Command evaluation of rm -rf / exits with code 1 because blocked
    exit_code = main(["sandbox", "rm -rf /"])
    assert exit_code == 1


def test_cli_sandbox_eval_safe():
    exit_code = main(["sandbox", "git status"])
    assert exit_code == 0
