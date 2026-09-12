from .peak_2d import Peak2DValidator
from .registry import get_validator, known_validators, register

register("PEAK_2D", Peak2DValidator())

__all__ = ["get_validator", "known_validators", "register"]
