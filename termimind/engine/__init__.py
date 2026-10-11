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
TermiMind Engine Module.
Coordinates the LLM resolver with offline local fallback pattern matching.
"""

from termimind.engine.local_fallback import LocalFallbackEngine
from termimind.engine.resolver import CommandResolver, ResolutionResult

__all__ = [
    "LocalFallbackEngine",
    "CommandResolver",
    "ResolutionResult",
]
