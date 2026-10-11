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
TermiMind: AI-powered, sandbox-protected terminal command fixer.
Captures terminal errors across Bash, Zsh, and PowerShell,
providing safe single-key [Enter] executable fixes via LLM and local heuristic engines.
"""

__version__ = "1.0.0"
__author__ = "EvoderDev"
__license__ = "Apache-2.0"

from termimind.config import TermiMindConfig, get_config
from termimind.core.sandbox import RiskLevel, SandboxEvaluator, SandboxResult
from termimind.core.environment import EnvironmentContext, get_environment
from termimind.core.shell_capturer import ShellCapturer, FailureRecord
from termimind.core.shell_listener import ShellHookListener
from termimind.engine.local_fallback import LocalFallbackEngine
from termimind.engine.resolver import CommandResolver, ResolutionResult

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "TermiMindConfig",
    "get_config",
    "RiskLevel",
    "SandboxEvaluator",
    "SandboxResult",
    "EnvironmentContext",
    "get_environment",
    "ShellCapturer",
    "FailureRecord",
    "ShellHookListener",
    "LocalFallbackEngine",
    "CommandResolver",
    "ResolutionResult",
]
