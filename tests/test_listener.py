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

from pathlib import Path
from unittest.mock import MagicMock

from termimind.core.shell_capturer import FailureRecord
from termimind.core.shell_listener import ShellHookListener


def test_listener_no_failure(tmp_path: Path):
    listener = ShellHookListener(storage_dir=tmp_path)
    res = listener.process_latest_failure(dry_run=True)
    assert res is None


def test_listener_detects_and_processes_failure(tmp_path: Path):
    listener = ShellHookListener(storage_dir=tmp_path)
    record = FailureRecord(
        command="git staus",
        exit_code=1,
        stderr="git: 'staus' is not a git command. See 'git --help'.",
    )
    listener.capturer.save(record)

    exit_code = listener.process_latest_failure(dry_run=True)
    assert exit_code == 0


def test_listener_max_events(tmp_path: Path):
    listener = ShellHookListener(storage_dir=tmp_path)
    record = FailureRecord(
        command="pylintt my_file.py",
        exit_code=1,
        stderr="command not found: pylintt",
    )
    listener.capturer.save(record)

    # Run listener for exactly 1 event
    listener.start_listening(poll_interval=0.01, dry_run=True, max_events=1)
    assert not listener._running
