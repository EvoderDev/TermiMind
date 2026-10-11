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
TermiMind Configuration Manager.
Handles persistent settings, environment variable overrides, and default policies.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_default_config_dir() -> Path:
    """Returns the default configuration directory (~/.termimind)."""
    custom_dir = os.environ.get("TERMIMIND_CONFIG_DIR")
    if custom_dir:
        return Path(custom_dir)

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "termimind"

    return Path.home() / ".termimind"


@dataclass
class TermiMindConfig:
    """Configuration model for TermiMind."""

    # LLM Provider settings: "auto", "gemini", "openai", "anthropic", "ollama", "local"
    llm_provider: str = "auto"
    model: str = ""
    api_key: str = ""
    api_base: str = ""
    temperature: float = 0.2
    max_tokens: int = 512
    timeout_seconds: float = 8.0

    # Safety and Sandbox settings
    safety_mode: str = "strict"  # "strict", "moderate", "permissive"
    blocked_patterns: List[str] = field(default_factory=lambda: [
        r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s+(?:/|/\*|~|~\*|\.\.|\.\./)(?:\s|$|[;&|])",
        r"\b(?:del|erase)\s+(?:/[a-zA-Z]+\s+)*[A-Za-z]:\\(?:\*|\*\.\*)?(?:\s|$|[;&|])",
        r"\bRemove-Item\s+.*-(?:Recurse|Force)\s+.*(?:[A-Za-z]:\\(?:\*|\*\.\*)?|/(?:\s|$|[;&|]))",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
        r"\b(?:mkfs|dd\s+if=.*of=/dev/)",
        r"\b(?:curl|wget|irm)\s+.*\|\s*(?:bash|sh|zsh|iex|powershell)\b",
        r"\bchmod\s+-[rR]\s+777\s+/",
    ])

    # Behavior settings
    auto_trigger: bool = False
    prefer_local: bool = False
    max_history_records: int = 50
    show_explanation: bool = True
    copy_to_clipboard_on_exit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TermiMindConfig:
        """Instantiate config safely from dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigManager:
    """Manages reading and writing TermiMind configuration."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or get_default_config_dir()
        self.config_file = self.config_dir / "config.json"
        self._config: Optional[TermiMindConfig] = None

    def ensure_dir(self) -> None:
        """Ensures the configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> TermiMindConfig:
        """Loads configuration from file and applies environment overrides."""
        config_data: Dict[str, Any] = {}

        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception:
                config_data = {}

        config = TermiMindConfig.from_dict(config_data)

        # Apply environment overrides
        env_provider = os.environ.get("TERMIMIND_LLM_PROVIDER")
        if env_provider:
            config.llm_provider = env_provider.lower()

        env_key = (
            os.environ.get("TERMIMIND_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        if env_key and not config.api_key:
            config.api_key = env_key

        env_model = os.environ.get("TERMIMIND_MODEL")
        if env_model:
            config.model = env_model

        env_api_base = os.environ.get("TERMIMIND_API_BASE")
        if env_api_base:
            config.api_base = env_api_base

        env_safety = os.environ.get("TERMIMIND_SAFETY_MODE")
        if env_safety:
            config.safety_mode = env_safety.lower()

        if os.environ.get("TERMIMIND_PREFER_LOCAL", "").lower() in ("1", "true", "yes"):
            config.prefer_local = True

        if os.environ.get("TERMIMIND_AUTO_TRIGGER", "").lower() in ("1", "true", "yes"):
            config.auto_trigger = True

        self._config = config
        return config

    def save(self, config: TermiMindConfig) -> None:
        """Saves configuration to file."""
        self.ensure_dir()
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        self._config = config

    def get(self) -> TermiMindConfig:
        """Returns the active configuration instance."""
        if self._config is None:
            return self.load()
        return self._config

    def set_value(self, key: str, value: Any) -> bool:
        """Updates a specific configuration key and saves to disk."""
        cfg = self.get()
        if not hasattr(cfg, key):
            return False

        field_type = type(getattr(cfg, key))
        # Type casting for booleans and numbers
        if field_type is bool:
            if isinstance(value, str):
                parsed_val = value.lower() in ("true", "1", "yes")
            else:
                parsed_val = bool(value)
        elif field_type is int:
            parsed_val = int(value)
        elif field_type is float:
            parsed_val = float(value)
        elif field_type is list:
            if isinstance(value, str):
                parsed_val = [x.strip() for x in value.split(",") if x.strip()]
            else:
                parsed_val = list(value)
        else:
            parsed_val = str(value)

        setattr(cfg, key, parsed_val)
        self.save(cfg)
        return True


_global_config_manager = ConfigManager()


def get_config() -> TermiMindConfig:
    """Helper to retrieve active TermiMind configuration."""
    return _global_config_manager.get()


def get_config_manager() -> ConfigManager:
    """Helper to retrieve the global config manager instance."""
    return _global_config_manager
