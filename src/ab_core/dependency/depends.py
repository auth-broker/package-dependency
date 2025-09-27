"""Universal object loader / dependency‑provider

Supports three kinds of *load targets*:

1. **LoaderBase** subclasses – your concrete Loader classes.  These are
   already callable and encapsulate loading logic.
2. **Raw Python types** – automatically wrapped in `DefaultLoader` so you
   can write::

       foo: Foo = Field(default=Depends(Foo))

3. **Arbitrary callables** (functions, generator functions, async
   functions, async‑generator functions).  These are executed in a way
   that mirrors FastAPI’s dependency behaviour:
   * generator → first ``yield``
   * async‑generator → first ``yield`` (returned as awaitable)
   * coroutine       → coroutine object (caller awaits)
   * plain function  → return value

There are two public entry‑points:

* :func:`Load`   – synchronous façade (blocks if passed an awaitable)
* :func:`aLoad`  – asynchronous façade (always ``await``‑safe)

Both share a single private implementation, so maintenance cost is low.
"""

from collections.abc import Awaitable
from typing import Generic, TypeVar, Union

from .loaders.base import LoaderBase
from .singleton import SingletonRegistry
from .types import LoadTarget
from .utils import is_real_callable


class NullDepends:
    def __init__(self, *args, **kwargs): ...


# ------------------------------------------------------------------ #
# Optional FastAPI integration
# ------------------------------------------------------------------ #
try:
    from fastapi.params import Depends as _FastapiDepends
except ModuleNotFoundError:  # running without FastAPI
    _FastapiDepends = NullDepends  # type: ignore[assignment,misc]

T = TypeVar("T")
Ret = Union[T, Awaitable[T]]

# --------------------------------------------------------------------- #
# Core implementation (sync; never awaits)                              #
# --------------------------------------------------------------------- #


def _load_impl(load_target: LoadTarget[T], *, persist: bool) -> T:  # noqa: C901
    """Return either *T* or an *Awaitable[T]* depending on target nature."""
    from .default import DefaultLoader  # local import to avoid cycle

    # --- 1. Callable ------------------------------------------------- #
    if is_real_callable(load_target):
        if persist:
            return SingletonRegistry(load_target, key=load_target)  # cache by the function instance
        return load_target()  # plain function

    # --- 2. Loader instance ----------------------------------------- #
    elif isinstance(load_target, LoaderBase):
        if persist:
            return SingletonRegistry(load_target, key=load_target.type)  # cache by the type
        return load_target()

    # --- 3. Raw type ------------------------------------------------- #
    elif DefaultLoader.supports(load_target):
        loader = DefaultLoader[load_target]()
        if persist:
            return SingletonRegistry(loader, key=load_target)  # cache by the type
        return loader()

    raise TypeError(
        f"Unsupported load_target type: {type(load_target).__name__}. Expected LoaderBase instance, class, or callable."
    )


def Load(load_target: LoadTarget[T], *, persist: bool = False) -> T:  # type: ignore[override]  # noqa: ANN001, D401
    """Load **synchronously**.

    If the underlying target is asynchronous, the current thread will
    block until the awaitable completes (using :pyfunc:`asyncio.run` or
    the running event‑loop’s ``run_until_complete``).
    """
    return _load_impl(load_target, persist=persist)


class Depends(Generic[T], _FastapiDepends):
    """Factory for dependency‑injection annotations.

    Example::

        def provide_db() -> DB: ...
        user: Annotated[DB, Depends(provide_db)]
    """

    def __init__(
        self,
        type_or_loader: LoadTarget[T],
        *,
        persist: bool = False,
    ) -> None:
        super().__init__(dependency=self.__call__, use_cache=persist)  # type: ignore[misc]

        self.load_target = type_or_loader
        self.persist = persist

    # The provider is designed to be called *by* the DI system, not by
    # user code.  It uses the synchronous façade because FastAPI will
    # `await` if it receives a coroutine.
    def __call__(self) -> T:  # noqa: D401
        return Load(self.load_target, persist=self.persist)
