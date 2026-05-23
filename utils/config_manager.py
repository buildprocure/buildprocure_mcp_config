"""
Configuration Manager
Loads and manages MCP configuration files.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigManager:
    """Loads YAML configs and keeps readable validation errors."""

    def __init__(self, config_dir: str | os.PathLike[str] = "configs") -> None:
        self.config_dir = Path(config_dir)
        self.configs: dict[str, Any] = {}
        self.errors: dict[str, str] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load all YAML configuration files without failing server startup."""
        self.configs = {}
        self.errors = {}

        if not self.config_dir.exists():
            message = f"Configuration directory not found: {self.config_dir}"
            self.errors[str(self.config_dir)] = message
            logger.warning(message)
            return

        for config_path in sorted(self.config_dir.glob("*.yaml")):
            try:
                with config_path.open("r", encoding="utf-8") as handle:
                    self.configs[config_path.name] = yaml.safe_load(handle) or {}
                logger.info("Loaded configuration: %s", config_path.name)
            except yaml.YAMLError as exc:
                self.errors[config_path.name] = f"Invalid YAML: {exc}"
                logger.warning("Invalid YAML in %s: %s", config_path, exc)
            except OSError as exc:
                self.errors[config_path.name] = f"Unable to read config: {exc}"
                logger.warning("Unable to read %s: %s", config_path, exc)

    def list_available_configs(self) -> dict[str, Any]:
        """Return available configs and any load errors."""
        return {
            "configs": sorted(self.configs.keys()),
            "errors": self.errors,
            "count": len(self.configs),
        }

    def get_config(self, config_name: str) -> dict[str, Any]:
        """Get a config by exact name, adding .yaml when omitted."""
        normalized_name = config_name if config_name.endswith(".yaml") else f"{config_name}.yaml"

        if normalized_name in self.configs:
            return {
                "name": normalized_name,
                "exists": True,
                "config": self.configs[normalized_name],
                "error": None,
            }

        if normalized_name in self.errors:
            return {
                "name": normalized_name,
                "exists": False,
                "config": {},
                "error": self.errors[normalized_name],
            }

        return {
            "name": normalized_name,
            "exists": False,
            "config": {},
            "error": f"Config not found: {normalized_name}",
        }

    def get_config_value(self, config_name: str) -> Any:
        """Return only the loaded config value for internal callers."""
        return self.get_config(config_name).get("config", {})
