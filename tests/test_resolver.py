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
Unit tests for TermiMind Resolver and fallback coordinator.
"""

from termimind.config import TermiMindConfig
from termimind.core.environment import EnvironmentContext, GitInfo
from termimind.core.sandbox import RiskLevel
from termimind.core.shell_capturer import FailureRecord
from termimind.engine.resolver import CommandResolver


def test_resolver_falls_back_to_local_when_no_llm():
    cfg = TermiMindConfig(llm_provider="local", prefer_local=True)
    resolver = CommandResolver(cfg)

    record = FailureRecord(
        command="sl",
        exit_code=127,
        stderr="sl: command not found",
    )
    env = EnvironmentContext(
        os_name="Linux",
        os_release="6.5",
        is_windows=False,
        is_linux=True,
        is_macos=False,
        is_wsl=False,
        shell_name="bash",
        cwd="/tmp",
        is_root=False,
    )

    resolution, sandbox = resolver.resolve(record, env)
    assert resolution.command == "ls"
    assert sandbox.risk_level == RiskLevel.SAFE
    assert sandbox.is_allowed is True


def test_resolver_parses_json_response():
    cfg = TermiMindConfig()
    resolver = CommandResolver(cfg)

    sample_json = """
    ```json
    {
        "command": "git pull origin main",
        "explanation": "Update local branch from remote before continuing.",
        "confidence": 0.96,
        "alternatives": ["git fetch"]
    }
    ```
    """
    res = resolver._parse_json_response(sample_json, engine="mock_gemini")
    assert res is not None
    assert res.command == "git pull origin main"
    assert res.confidence == 0.96
    assert "git fetch" in res.alternatives
