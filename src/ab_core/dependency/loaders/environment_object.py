"""Environment-backed object loader implementation."""

import os
from typing import Any, Literal, override

from pydantic import model_validator

from ab_core.dependency.schema.loader_type import LoaderSource
from ab_core.dependency.utils import extract_env_tree, to_env_prefix

from .base import ObjectLoaderBase, T


class ObjectLoaderEnvironment(ObjectLoaderBase[T]):
    """Load structured objects from environment variables.

    Data is collected using a configurable prefix and reshaped to match
    the target model schema.
    """

    # These get pulled from env or you can override in code:
    source: Literal[LoaderSource.ENVIRONMENT_OBJECT] = LoaderSource.ENVIRONMENT_OBJECT

    env_prefix: str | None = None

    @model_validator(mode="after")
    def default_env_prefix(self):
        """Populate a default prefix from the inferred alias name."""
        if self.env_prefix is None:
            self.env_prefix = to_env_prefix(self.alias_name)
        return self

    @override
    def load_raw(
        self,
    ) -> dict[str, Any]:
        """Build a nested dictionary from environment keys for model parsing."""
        tree = extract_env_tree(
            os.environ,
            self.env_prefix,
        )

        if self.discriminator_key:
            if not tree.get(self.discriminator_key):
                if self.default_discriminator_value:
                    tree[self.discriminator_key] = str(self.default_discriminator_value)
                else:
                    raise ValueError(
                        f"No discriminator choice provided for `{self.discriminator_key}`, loading"
                        f" please ensure you have configured your environmnt correctly."
                        f" `{self.env_prefix}_{self.discriminator_key.upper()}` should be"
                        f" one of the following: {'|'.join(self.discriminator_choices)}"
                    )

        return tree
