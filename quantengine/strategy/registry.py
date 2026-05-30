"""
QuantEngine Pro - Strategy Registry & Loader
=============================================
Dynamic strategy loading from configuration.

Supports:
- Loading strategies by Python import path from YAML config
- Hot-reload: update config → reload strategy instances
- Strategy factory pattern for custom strategy creation
"""

import importlib
from typing import Dict, List, Optional, Type

from loguru import logger

from quantengine.strategy.base import BaseStrategy


class StrategyRegistry:
    """
    Registry for discovering, loading, and managing trading strategies.

    Strategies are registered via YAML configuration and loaded dynamically
    by their Python import path.

    Usage:
        registry = StrategyRegistry()
        registry.load_from_config(strategy_configs)
        strategy = registry.create("dual_thrust_eth")
    """

    def __init__(self):
        """Initialize empty registry."""
        self._registry: Dict[str, Type[BaseStrategy]] = {}
        self._instances: Dict[str, BaseStrategy] = {}
        self._configs: Dict[str, Dict] = {}
        logger.info("StrategyRegistry initialized")

    def register_class(self, name: str, strategy_cls: Type[BaseStrategy]) -> None:
        """
        Register a strategy class by name.

        Args:
            name: Unique strategy identifier
            strategy_cls: Strategy class (not instance)
        """
        if not issubclass(strategy_cls, BaseStrategy):
            raise TypeError(
                f"{strategy_cls.__name__} must be a subclass of BaseStrategy"
            )
        self._registry[name] = strategy_cls
        logger.debug(f"Registered strategy class: {name}")

    def load_from_config(self, strategy_configs: List[Dict]) -> None:
        """
        Load and register strategies from configuration list.

        Each config dict must have:
            - name: Unique strategy name
            - class: Python import path (e.g., 'quantengine.strategy.builtin.dual_ma.DualMAStrategy')
            - params: Strategy parameters dict
            - symbols: List of trading symbols
            - timeframe: Bar frequency
            - weight: Capital allocation weight
            - enabled: Whether active

        Args:
            strategy_configs: List of strategy configuration dictionaries
        """
        for cfg in strategy_configs:
            if not cfg.get("enabled", True):
                logger.info(f"Skipping disabled strategy: {cfg.get('name')}")
                continue

            name = cfg["name"]
            class_path = cfg["class"]
            self._configs[name] = cfg

            try:
                # Dynamic import: 'quantengine.strategy.builtin.dual_ma.DualMAStrategy'
                module_path, class_name = class_path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                strategy_cls = getattr(module, class_name)

                # Validate it's a proper strategy class
                if not issubclass(strategy_cls, BaseStrategy):
                    raise TypeError(
                        f"{class_name} is not a BaseStrategy subclass"
                    )

                self._registry[name] = strategy_cls
                logger.info(f"Loaded strategy: {name} → {class_path}")

            except (ImportError, AttributeError, ValueError) as e:
                logger.error(f"Failed to load strategy '{name}' from '{class_path}': {e}")
            except TypeError as e:
                logger.error(f"Invalid strategy class '{name}': {e}")

    def create(self, name: str, **overrides) -> Optional[BaseStrategy]:
        """
        Create a strategy instance by name.

        Args:
            name: Strategy name (as defined in config)
            **overrides: Parameter overrides for this instance

        Returns:
            Strategy instance, or None if creation fails
        """
        if name not in self._registry:
            logger.error(f"Strategy '{name}' not registered")
            return None

        config = self._configs.get(name, {})
        params = {**config.get("params", {}), **overrides}

        try:
            strategy_cls = self._registry[name]
            instance = strategy_cls(params)
            instance.name = name  # Override with config name
            self._instances[name] = instance
            logger.info(f"Created strategy instance: {name}")
            return instance

        except Exception as e:
            logger.error(f"Failed to create strategy '{name}': {e}")
            return None

    def create_all(self) -> Dict[str, BaseStrategy]:
        """
        Create instances for all registered strategies.

        Returns:
            Dict mapping strategy name → instance
        """
        for name in self._registry:
            if name not in self._instances:
                self.create(name)
        return self._instances

    def get(self, name: str) -> Optional[BaseStrategy]:
        """
        Get an existing strategy instance.

        Args:
            name: Strategy name

        Returns:
            Strategy instance or None
        """
        return self._instances.get(name)

    def get_all(self) -> Dict[str, BaseStrategy]:
        """Get all active strategy instances."""
        return self._instances

    def get_config(self, name: str) -> Optional[Dict]:
        """
        Get strategy configuration.

        Args:
            name: Strategy name

        Returns:
            Config dict or None
        """
        return self._configs.get(name)

    def reload(self, name: str) -> Optional[BaseStrategy]:
        """
        Hot-reload a strategy (re-create with current config).

        Args:
            name: Strategy name to reload

        Returns:
            New strategy instance
        """
        # Stop old instance if running
        old = self._instances.pop(name, None)
        if old:
            old.on_stop()

        return self.create(name)

    def reload_all(self) -> Dict[str, BaseStrategy]:
        """
        Hot-reload all strategies.

        Returns:
            Dict of new strategy instances
        """
        # Stop all old instances
        for instance in self._instances.values():
            instance.on_stop()
        self._instances.clear()

        return self.create_all()

    @property
    def strategy_names(self) -> List[str]:
        """List of registered strategy names."""
        return list(self._registry.keys())

    @property
    def active_count(self) -> int:
        """Number of active strategy instances."""
        return len(self._instances)
