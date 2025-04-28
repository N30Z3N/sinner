from abc import ABCMeta
from typing import Any


class Singleton(type):
    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class SingletonABCMeta(ABCMeta, Singleton):
    """Метакласс, объединяющий функциональность ABCMeta и Singleton"""
    pass
