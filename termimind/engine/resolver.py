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
Central command resolution coordinator for TermiMind.
Coordinates LLM queries (Gemini, OpenAI, Anthropic, Ollama) with offline fallback heuristics
and integrates sandbox security inspection before returning proposals.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

import requests

from termimind.config import TermiMindConfig
from termimind.core.environment import EnvironmentContext
from termimind.core.sandbox import RiskLevel, SandboxEvaluator, SandboxResult
from termimind.core.shell_capturer import FailureRecord
from termimind.engine.local_fallback import LocalFallbackEngine, ResolutionResult

logger = logging.getLogger("termimind.resolver")


SYSTEM_PROMPT = """You are TermiMind, an expert shell and terminal command diagnostic AI.
Your goal is to inspect a failed terminal command and its error output, then provide an immediate, safe, exact command to fix the issue.

RULES:
1. Return ONLY a single valid JSON object. Do not add markdown commentary outside the JSON.
2. The JSON must match this exact schema:
{
  "command": "string - the exact corrected terminal command to run",
  "explanation": "string - 1 to 2 concise sentences explaining what failed and how this command fixes it",
  "confidence": 0.0 to 1.0 (float),
  "alternatives": ["optional alternative command 1", "optional alternative command 2"]
}
3. The command must match the user's OS and Shell precisely.
4. NEVER propose destructive commands like 'rm -rf /', raw disk formatting, or downloading arbitrary scripts piped to bash/iex.
5. Focus on the most common root causes: typos, missing packages, uncommitted git states, incorrect flags, or missing environment variables.
"""


class CommandResolver:
    """Orchestrates LLM and rule-based diagnostic engines."""

    def __init__(self, config: TermiMindConfig):
        self.config = config
        self.local_engine = LocalFallbackEngine()
        self.sandbox = SandboxEvaluator(
            safety_mode=config.safety_mode,
            custom_blocked=config.blocked_patterns,
        )

    def resolve(
        self, record: FailureRecord, env: EnvironmentContext
    ) -> Tuple[ResolutionResult, SandboxResult]:
        """Resolves the failure and evaluates sandbox safety."""
        # 1. If prefer_local is enabled or provider is local, prioritize offline engine
        if self.config.prefer_local or self.config.llm_provider == "local":
            local_res = self.local_engine.resolve(record, env)
            if local_res:
                sandbox_res = self.sandbox.evaluate(local_res.command)
                return local_res, sandbox_res

        # 2. Try LLM resolution if provider is configured or auto-detected
        llm_res = self._try_llm_resolve(record, env)
        if llm_res:
            sandbox_res = self.sandbox.evaluate(llm_res.command)
            # If LLM proposed a blocked command, discard and fall back
            if sandbox_res.risk_level == RiskLevel.BLOCKED:
                logger.warning(f"LLM proposed a blocked command: {llm_res.command}")
            else:
                return llm_res, sandbox_res

        # 3. Fall back to local rule-based engine
        local_res = self.local_engine.resolve(record, env)
        if local_res:
            sandbox_res = self.sandbox.evaluate(local_res.command)
            return local_res, sandbox_res

        # 4. Ultimate generic fallback if no rule matched
        generic_res = ResolutionResult(
            command=f"{record.command} --help",
            explanation="Could not automatically resolve this error. Check command documentation or manual.",
            confidence=0.30,
            engine="generic_fallback",
        )
        sandbox_res = self.sandbox.evaluate(generic_res.command)
        return generic_res, sandbox_res

    def _try_llm_resolve(
        self, record: FailureRecord, env: EnvironmentContext
    ) -> Optional[ResolutionResult]:
        """Attempts resolution via configured LLM provider."""
        provider = self._determine_provider()
        if not provider or provider in ("none", "local"):
            return None

        prompt = self._build_prompt(record, env)

        try:
            if provider == "gemini":
                return self._call_gemini(prompt)
            if provider == "openai":
                return self._call_openai_compatible(prompt, base_url=self.config.api_base or "https://api.openai.com/v1")
            if provider == "ollama":
                base_url = self.config.api_base or "http://localhost:11434/v1"
                return self._call_openai_compatible(prompt, base_url=base_url, is_ollama=True)
            if provider == "anthropic":
                return self._call_anthropic(prompt)
        except Exception as e:
            logger.debug(f"LLM resolution failed with provider {provider}: {e}")
            return None

        return None

    def _determine_provider(self) -> Optional[str]:
        """Infers active LLM provider based on config and available keys."""
        cfg_provider = self.config.llm_provider.lower()
        if cfg_provider not in ("auto", ""):
            return cfg_provider

        # Auto detection based on available keys
        if self.config.api_key:
            if self.config.api_key.startswith("AIzaSy"):
                return "gemini"
            if self.config.api_key.startswith("sk-ant-"):
                return "anthropic"
            if self.config.api_key.startswith("sk-"):
                return "openai"

        # Check API base indicating local Ollama
        if self.config.api_base and "11434" in self.config.api_base:
            return "ollama"

        return None

    def _build_prompt(self, record: FailureRecord, env: EnvironmentContext) -> str:
        """Constructs context-rich diagnostic prompt."""
        recent_files_str = ", ".join(env.recent_files[:15]) if env.recent_files else "none"
        git_branch_str = env.git_info.branch if env.git_info.is_repo else "Not a git repo"
        stdout_section = f"Stdout Output:\n{record.stdout[:1000]}\n" if record.stdout else ""
        return (
            f"--- ENVIRONMENT ---\n"
            f"OS: {env.os_name} ({env.os_release})\n"
            f"Shell: {env.shell_name}\n"
            f"CWD: {env.cwd}\n"
            f"Files in CWD: {recent_files_str}\n"
            f"Git Branch: {git_branch_str}\n\n"
            f"--- FAILED EXECUTION ---\n"
            f"Failed Command: {record.command}\n"
            f"Exit Code: {record.exit_code}\n"
            f"Stderr Output:\n{record.stderr[:2000]}\n"
            f"{stdout_section}\n"
            f"Suggest the exact fix."
        )

    def _call_gemini(self, prompt: str) -> Optional[ResolutionResult]:
        """Calls Google Gemini REST API."""
        api_key = self.config.api_key
        if not api_key:
            return None

        model = self.config.model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
                "responseMimeType": "application/json",
            },
        }

        resp = requests.post(url, json=payload, timeout=self.config.timeout_seconds)
        if resp.status_code != 200:
            return None

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return self._parse_json_response(text, engine=f"gemini ({model})")

    def _call_openai_compatible(
        self, prompt: str, base_url: str, is_ollama: bool = False
    ) -> Optional[ResolutionResult]:
        """Calls OpenAI or compatible REST API (including Ollama, vLLM, LM Studio)."""
        model = self.config.model or ("llama3" if is_ollama else "gpt-4o-mini")
        headers = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
        if resp.status_code != 200:
            return None

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return None

        text = choices[0].get("message", {}).get("content", "")
        engine_label = f"ollama ({model})" if is_ollama else f"openai ({model})"
        return self._parse_json_response(text, engine=engine_label)

    def _call_anthropic(self, prompt: str) -> Optional[ResolutionResult]:
        """Calls Anthropic Messages API."""
        api_key = self.config.api_key
        if not api_key:
            return None

        model = self.config.model or "claude-3-5-sonnet-20241022"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": model,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
        if resp.status_code != 200:
            return None

        data = resp.json()
        content = data.get("content", [])
        if not content:
            return None

        text = content[0].get("text", "")
        return self._parse_json_response(text, engine=f"anthropic ({model})")

    def _parse_json_response(self, text: str, engine: str) -> Optional[ResolutionResult]:
        """Parses model response text into ResolutionResult."""
        raw_text = text.strip()

        # Extract JSON substring between outermost braces if present
        start_idx = raw_text.find("{")
        end_idx = raw_text.rfind("}")
        json_str = raw_text[start_idx : end_idx + 1] if (start_idx != -1 and end_idx != -1 and end_idx > start_idx) else raw_text

        try:
            parsed = json.loads(json_str)
            command = parsed.get("command", "").strip()
            explanation = parsed.get("explanation", "").strip()
            confidence = float(parsed.get("confidence", 0.90))
            alternatives = parsed.get("alternatives", [])

            if not command:
                return None

            return ResolutionResult(
                command=command,
                explanation=explanation or "Suggested command fix.",
                confidence=confidence,
                engine=engine,
                alternatives=alternatives if isinstance(alternatives, list) else [],
            )
        except Exception:
            # Fallback regex extraction if JSON was slightly malformed
            cmd_match = re.search(r'"command"\s*:\s*"([^"]+)"', raw_text)
            if cmd_match:
                return ResolutionResult(
                    command=cmd_match.group(1).strip(),
                    explanation="Extracted fix from model response.",
                    confidence=0.80,
                    engine=engine,
                )
            return None
