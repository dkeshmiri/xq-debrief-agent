"""Display assessment scores without introducing rounding or trailing zeros."""


def format_score(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
