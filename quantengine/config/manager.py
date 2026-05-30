"""
QuantEngine Pro - Configuration Manager
========================================
Centralized YAML configuration loading with:
- Environment variable interpolation (${VAR_NAME})
- Deep merge of config files
- Dot-notation access for nested keys
- Lazy loading and caching
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from loguru import logger


# Pattern for environment variable references: ${VAR_NAME} or ${VAR_NAME:default}
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)(?::([^}]*))?\}")


def _resolve_env_vars(value: Any) -> Any:
    """
    Recursively resolve environment variable references in a config value.

    Supports:
        ${VAR_NAME}        - Replaced with os.environ['VAR_NAME'] or empty string
        ${VAR_NAME:default} - Replaced with os.environ['VAR_NAME'] or 'default'

    Args:
        value: Any config value (str, dict, list, etc.)

    Returns:
        Value with environment variables resolved
    """
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            default = match.group(2)
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return env_val
            if default is not None:
                return default
            logger.warning(
                f"Environment variable '{var_name}' not set and no default provided"
            )
            return ""
        return _ENV_VAR_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


class ConfigManager:
    """
    Centralized configuration manager for QuantEngine Pro.

    Loads YAML configuration files from the config directory, resolves
    environment variable references, and provides dot-notation access.

    Usage:
        cfg = ConfigManager(config_dir="./config")
        data_cfg = cfg.get("data")
        provider = cfg.get("data.quote.provider")  # dot-notation access
    """

    def __init__(self, config_dir: str = "./config"):
        """
        Initialize config manager.

        Args:
            config_dir: Path to directory containing YAML config files
        """
        self._config_dir = Path(config_dir)
        self._cache: Dict[str, Dict] = {}
        logger.info(f"ConfigManager initialized with config_dir={self._config_dir}")

    def load(self, name: str, force_reload: bool = False) -> Dict:
        """
        Load a config file by name.

        Args:
            name: Config name without extension (e.g., 'data_source', 'llm')
            force_reload: If True, reload even if cached

        Returns:
            Dict containing the configuration
        """
        if name in self._cache and not force_reload:
            return self._cache[name]

        file_path = self._config_dir / f"{name}.yaml"
        if not file_path.exists():
            logger.error(f"Config file not found: {file_path}")
            raise FileNotFoundError(f"Config file not found: {file_path}")

        logger.debug(f"Loading config: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Resolve environment variables
        config = _resolve_env_vars(config)

        self._cache[name] = config
        logger.info(f"Loaded config: {name}")
        return config

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a config value using dot-notation path.

        Args:
            key_path: Dot-separated path to config value
                      (e.g., 'data_source.data.quote.provider')
            default: Default value if key not found

        Returns:
            Config value at path, or default if not found
        """
        parts = key_path.split(".")
        config_name = parts[0]

        # Map shorthand names to config files
        config_file_map = {
            "data": "data_source",
            "data_source": "data_source",
            "llm": "llm",
            "strategies": "strategies",
            "strategies_config": "strategies",
            "risk": "risk_config",
            "risk_config": "risk_config",
            "execution": "execution",
        }

        file_name = config_file_map.get(config_name, config_name)
        try:
            config = self.load(file_name)
        except FileNotFoundError:
            return default

        # Navigate nested keys
        # If the first part was a config file alias, skip it
        if config_name in config_file_map and config_name != file_name:
            remaining = parts[1:]
        else:
            remaining = parts[1:]

        current = config
        for part in remaining:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default

        return current

    def get_strategy_configs(self) -> list:
        """
        Get all enabled strategy configurations.

        Returns:
            List of strategy config dicts that are enabled
        """
        config = self.load("strategies")
        strategies = config.get("strategies", [])
        return [s for s in strategies if s.get("enabled", True)]

    def get_data_provider(self, provider_type: str) -> Optional[str]:
        """
        Get the configured provider name for a data type.

        Args:
            provider_type: One of 'quote', 'market_flow', 'news'

        Returns:
            Provider name string, or None if not configured
        """
        return self.get(f"data_source.data.{provider_type}.provider")

    def reload_all(self) -> None:
        """Force reload all cached config files."""
        cached_names = list(self._cache.keys())
        self._cache.clear()
        for name in cached_names:
            try:
                self.load(name)
            except FileNotFoundError:
                logger.warning(f"Could not reload config: {name}")


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config(config_dir: str = "./config") -> ConfigManager:
    """
    Get or create the global ConfigManager instance.

    Args:
        config_dir: Path to config directory (only used on first call)

    Returns:
        ConfigManager singleton instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
    return _config_manager
