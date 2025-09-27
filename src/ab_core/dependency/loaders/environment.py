import os
from typing import Any, Literal, override

from ab_core.dependency.schema.loader_type import LoaderSource

from .base import LoaderBase, T


class LoaderEnvironment(LoaderBase[T]):
    """A loader that picks a subtype of a Discriminated Union
    from an env-var PREFIX_type, then scans PREFIX_type_{value}_{field}
    for every other field on that subtype.
    """

    # These get pulled from env or you can override in code:
    source: Literal[LoaderSource.ENVIRONMENT] = LoaderSource.ENVIRONMENT

    key: str

    @override
    def load_raw(
        self,
    ) -> Any:
        """Collects environment variables to build a dict matching the discriminated union fields,
        keyed by discriminator and field names, ready for Pydantic validation.
        """
        return os.getenv(self.key)
