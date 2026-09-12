from .base import BaseValidator

_REGISTRY: dict[str, BaseValidator] = {}


def register(name: str, validator: BaseValidator) -> None:
    key = (name or "").strip().upper()
    if not key:
        raise ValueError("validator name is required")
    validator.name = key
    _REGISTRY[key] = validator


def get_validator(name: str) -> BaseValidator | None:
    if not name:
        return None
    return _REGISTRY.get(str(name).strip().upper())


def known_validators() -> list[str]:
    return sorted(_REGISTRY.keys())
