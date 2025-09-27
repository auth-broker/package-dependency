from typing import TypeVar, cast

_T = TypeVar("_T")
_INJECT_SENTINEL = object()  # unique, never used at runtime


def sentinel() -> _T:  # noqa: N802  (capital I for clarity)
    """Typing-only sentinel for DI parameters.

    Usage:
        db: Annotated[Database, Depends(make_db)] = Sentinel()
    """
    return cast(_T, _INJECT_SENTINEL)
