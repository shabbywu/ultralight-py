"""Internal input value validation."""


def integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not -(2**31) <= value < 2**31:
        raise OverflowError(f"{name} exceeds the SDK int range")
