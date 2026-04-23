"""
Configuration Manager
Loads and manages MCP configurations
"""

import os
import yaml
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages MCP configuration"""
    
    def __init__(self):
        self.config_dir = "configs"
        self.configs = {}
        self._load_configs()
    
    def _load_configs(self):
        """Load all configuration files"""
        for config_file in os.listdir(self.config_dir):
            if config_file.endswith(".yaml"):
                config_path = os.path.join(self.config_dir, config_file)
                with open(config_path, 'r') as f:
                    self.configs[config_file] = yaml.safe_load(f)
                logger.info(f"Loaded configuration: {config_file}")
    
    def get_config(self, config_name):
        """Get a specific configuration"""
        return self.configs.get(config_name, {})