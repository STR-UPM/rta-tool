"""Exact arithmetic for ceiling operations and fixed-point comparisons."""
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import math
from typing import Union

from .errors import ModelError

TimeLike = Union[int, float, str, Decimal, Fraction]


def time_value(value: TimeLike, field: str = "time") -> Fraction:
    """Convert decimal-looking floats through str, never their binary expansion."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal, Fraction)):
        raise ModelError(f"{field} must be a finite number, not {value!r}")
    try:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("not finite")
        result = Fraction(str(value)) if isinstance(value, (float, str)) else Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError, InvalidOperation) as exc:
        raise ModelError(f"{field} must be a finite number, not {value!r}") from exc
    if result < 0:
        raise ModelError(f"{field} must be nonnegative, not {value!r}")
    return result


def nonnegative_integer(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelError(f"{field} must be a nonnegative integer")
    return value


def ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def exact_string(value: Fraction) -> str:
    """A finite decimal without rounding, or a/b for a non-terminating rational."""
    value = Fraction(value)
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        return str(value)
    places = max(twos, fives)
    integer = abs(value.numerator) * 2 ** (places - twos) * 5 ** (places - fives)
    sign = "-" if value < 0 else ""
    if places == 0:
        return sign + str(integer)
    digits = str(integer).rjust(places + 1, "0")
    return (sign + digits[:-places] + "." + digits[-places:]).rstrip("0").rstrip(".")


def tsf_string(value: Fraction) -> str:
    result = exact_string(value)
    if "/" in result:
        raise ModelError(f"TSF requires a finite decimal; cannot serialize {value}")
    return result


def display_number(value: Fraction, places: int = 3) -> str:
    if not 0 <= places <= 18:
        raise ModelError("display precision must be between 0 and 18")
    value = Fraction(value)
    with localcontext() as ctx:
        ctx.prec = max(28, len(str(abs(value.numerator))) + len(str(value.denominator)) + places + 4)
        return format(Decimal(value.numerator) / Decimal(value.denominator), f".{places}f")
