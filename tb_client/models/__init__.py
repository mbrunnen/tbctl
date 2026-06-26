import importlib
import re


def _to_module(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def __getattr__(name: str):
    try:
        mod = importlib.import_module(f"tb_client.models.{_to_module(name)}")
        cls = getattr(mod, name)
        globals()[name] = cls
        return cls
    except (ImportError, AttributeError):
        raise AttributeError(f"module 'tb_client.models' has no attribute {name!r}")
