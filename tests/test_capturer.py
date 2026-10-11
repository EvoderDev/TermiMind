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
Unit tests for TermiMind Shell Capturer and ANSI Normalizer.
"""

from pathlib import Path

from termimind.core.shell_capturer import FailureRecord, ShellCapturer, clean_ansi


def test_clean_ansi():
    colored_text = "\x1b[31mError:\x1b[0m \x1b[1mFile not found\x1b[0m"
    cleaned = clean_ansi(colored_text)
    assert cleaned == "Error: File not found"


def test_save_and_load_record(tmp_path: Path):
    capturer = ShellCapturer(storage_dir=tmp_path)
    record = FailureRecord(
        command="python missing.py",
        exit_code=2,
        stderr="\x1b[31mNo such file\x1b[0m",
        cwd="/tmp/project",
        shell="bash",
    )
    capturer.save(record)

    loaded = capturer.load()
    assert loaded is not None
    assert loaded.command == "python missing.py"
    assert loaded.exit_code == 2
    assert loaded.stderr == "No such file"
    assert loaded.cwd == "/tmp/project"


def test_clear_record(tmp_path: Path):
    capturer = ShellCapturer(storage_dir=tmp_path)
    record = FailureRecord(
        command="npm start",
        exit_code=1,
        stderr="Failed",
    )
    capturer.save(record)
    assert capturer.load() is not None

    capturer.clear()
    assert capturer.load() is None
