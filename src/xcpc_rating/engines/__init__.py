"""Engine registry with lazy imports.

Concrete engine modules are imported only when their engine is requested, so
placeholder implementations never break importing the core layer.
"""

# Registry maps engine name -> (module, class name) for lazy resolution.
# The incremental ladder is the single scoring rule (see the README, 评分算法).
ENGINES = {
    "incremental": ("xcpc_rating.engines.incremental", "IncrementalEngine"),
}


def available_engines():
    """Return the sorted list of registered engine names."""
    return sorted(ENGINES)


def get_engine(name: str):
    """Instantiate a registered engine by name (lazy import).

    Raises KeyError with the available names if the engine is unknown.
    """
    if name not in ENGINES:
        raise KeyError(
            f"unknown engine {name!r}; available: {available_engines()}"
        )
    module_path, class_name = ENGINES[name]
    import importlib

    module = importlib.import_module(module_path)
    engine_cls = getattr(module, class_name)
    return engine_cls()
