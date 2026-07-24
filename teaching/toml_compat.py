"""Load TOML on Python versions with or without stdlib tomllib."""

try:
    import tomllib  # type: ignore[no-redef]
except ModuleNotFoundError:  # pragma: no cover - selected on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

__all__ = ["tomllib"]
