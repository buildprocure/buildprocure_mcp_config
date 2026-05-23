"""
Config Tools
Read-only access to loaded MCP YAML configuration.
"""

from __future__ import annotations

from typing import Any

from utils.config_manager import ConfigManager


class ConfigTool:
    """Expose loaded config metadata and values as MCP tools."""

    def __init__(self, config: ConfigManager | None = None) -> None:
        self.config = config or ConfigManager()

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_available_configs",
                "description": "List available YAML configs and readable load errors",
            },
            {
                "name": "get_config",
                "description": "Get one loaded config by name",
            },
        ]

    def list_available_configs(self) -> dict[str, Any]:
        return self.config.list_available_configs()

    def get_config(self, config_name: str) -> dict[str, Any]:
        return self.config.get_config(config_name)
