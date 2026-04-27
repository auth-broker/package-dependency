"""Environment-backed scalar loader implementation."""

import os
from typing import Any, Literal, override

from ab_core.dependency.schema.loader_type import LoaderSource

from .base import LoaderBase, T


class LoaderEnvironment(LoaderBase[T]):
    """Load a value directly from an environment variable.

    The configured key is read verbatim and then parsed by Pydantic
    against the target type.
    """

    # These get pulled from env or you can override in code:
    source: Literal[LoaderSource.ENVIRONMENT] = LoaderSource.ENVIRONMENT

    key: str

    @override
    def load_raw(
        self,
    ) -> Any:
        """Return the raw string value from the configured environment key."""
        return os.getenv(self.key)
