"""Template loader showing extension points for custom loaders."""

from typing import Any, Literal, override

from ab_core.dependency.schema.loader_type import LoaderSource

from .base import LoaderBase, T


class LoaderTemplate(LoaderBase[T]):
    """Example loader skeleton for custom implementations.

    Replace `load_raw` with your data source retrieval logic.
    """

    # These get pulled from env or you can override in code:
    source: Literal[LoaderSource.TEMPLATE] = LoaderSource.TEMPLATE

    key: str

    @override
    def load_raw(
        self,
    ) -> Any:
        """Return raw data from the backing source."""
        raise NotImplementedError()
