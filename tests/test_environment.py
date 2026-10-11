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
Unit tests for TermiMind Environment Discovery.
"""

from pathlib import Path

from termimind.core.environment import (
    EnvironmentContext,
    GitInfo,
    check_available_tools,
    detect_shell,
    get_environment,
    scan_recent_files,
)


def test_detect_shell():
    shell = detect_shell()
    assert isinstance(shell, str)
    assert len(shell) > 0


def test_check_available_tools():
    tools = check_available_tools()
    assert isinstance(tools, list)
    # python or git should exist in standard test environments
    assert any(t in tools for t in ["python", "python3", "git", "bash", "powershell", "pwsh"])


def test_scan_recent_files(tmp_path: Path):
    (tmp_path / "app.py").write_text("print(1)")
    (tmp_path / "data.csv").write_text("a,b")
    (tmp_path / ".hidden").write_text("ignore")

    files = scan_recent_files(tmp_path)
    assert "app.py" in files
    assert "data.csv" in files
    assert ".hidden" not in files


def test_environment_summary():
    ctx = EnvironmentContext(
        os_name="Windows",
        os_release="11",
        is_windows=True,
        is_linux=False,
        is_macos=False,
        is_wsl=False,
        shell_name="powershell",
        cwd="C:\\Dev",
        is_root=False,
        available_tools=["git", "python"],
        recent_files=["main.py"],
        git_info=GitInfo(is_repo=True, branch="main", is_dirty=False),
        virtual_env=None,
    )
    summary = ctx.format_summary()
    assert "Windows" in summary
    assert "powershell" in summary
    assert "main" in summary
