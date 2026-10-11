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
Unit tests for TermiMind Offline Local Fallback Engine.
"""

import pytest

from termimind.core.environment import EnvironmentContext, GitInfo
from termimind.core.shell_capturer import FailureRecord
from termimind.engine.local_fallback import LocalFallbackEngine


@pytest.fixture
def mock_env():
    return EnvironmentContext(
        os_name="Linux",
        os_release="6.5.0",
        is_windows=False,
        is_linux=True,
        is_macos=False,
        is_wsl=False,
        shell_name="bash",
        cwd="/workspace/project",
        is_root=False,
        available_tools=["git", "python", "python3", "pip", "npm"],
        recent_files=["main.py", "README.md", "package.json"],
        git_info=GitInfo(is_repo=True, branch="feature-login", is_dirty=False),
        virtual_env=None,
    )


@pytest.fixture
def engine():
    return LocalFallbackEngine()


def test_resolve_shell_typo(engine, mock_env):
    record = FailureRecord(
        command="sl -la",
        exit_code=127,
        stderr="sl: command not found",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "ls -la"
    assert "sl" in res.explanation


def test_resolve_cd_typo(engine, mock_env):
    record = FailureRecord(
        command="cd..",
        exit_code=127,
        stderr="cd..: command not found",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "cd .."


def test_resolve_git_subcommand_typo(engine, mock_env):
    record = FailureRecord(
        command="git cmmit -m 'initial'",
        exit_code=1,
        stderr="git: 'cmmit' is not a git command. See 'git --help'.",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "git commit -m 'initial'"


def test_resolve_git_no_upstream(engine, mock_env):
    record = FailureRecord(
        command="git push",
        exit_code=128,
        stderr="fatal: The current branch feature-login has no upstream branch.",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "git push --set-upstream origin feature-login"


def test_resolve_git_not_a_repo(engine, mock_env):
    record = FailureRecord(
        command="git status",
        exit_code=128,
        stderr="fatal: not a git repository (or any of the parent directories): .git",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "git init"


def test_resolve_python_missing_module_mapping(engine, mock_env):
    record = FailureRecord(
        command="python app.py",
        exit_code=1,
        stderr="ModuleNotFoundError: No module named 'cv2'",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert "opencv-python" in res.command
    assert "pip" in res.command


def test_resolve_python_yaml_mapping(engine, mock_env):
    record = FailureRecord(
        command="python script.py",
        exit_code=1,
        stderr="ModuleNotFoundError: No module named 'yaml'",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert "pyyaml" in res.command


def test_resolve_node_missing_module(engine, mock_env):
    record = FailureRecord(
        command="node server.js",
        exit_code=1,
        stderr="Error: Cannot find module 'express'",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "npm install express"


def test_resolve_npm_missing_package_json(engine, mock_env):
    record = FailureRecord(
        command="npm install axios",
        exit_code=1,
        stderr="npm ERR! code ENOENT: no such file or directory, open 'package.json'",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "npm init -y"


def test_resolve_filename_typo(engine, mock_env):
    record = FailureRecord(
        command="cat maine.py",
        exit_code=1,
        stderr="cat: maine.py: No such file or directory",
    )
    res = engine.resolve(record, mock_env)
    assert res is not None
    assert res.command == "cat main.py"
