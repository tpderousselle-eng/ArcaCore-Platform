"""Example application rules; package this module with your generated application."""


def require_even(value):
    if value % 2:
        raise ValueError("Value must be even.")
    return value


def reject_reserved_slug(value):
    if value in {"admin", "api", "login", "logout", "settings"}:
        raise ValueError("This slug is reserved.")
    return value
