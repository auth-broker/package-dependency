import os
from typing import Any, Literal, override

from pydantic import model_validator

from ab_core.dependency.schema.loader_type import LoaderSource
from ab_core.dependency.utils import extract_env_tree, to_env_prefix

from .base import ObjectLoaderBase, T


class ObjectLoaderEnvironment(ObjectLoaderBase[T]):
    """A loader that picks a subtype of a Discriminated Union
    from an env-var PREFIX_type, then scans PREFIX_type_{value}_{field}
    for every other field on that subtype.
    """

    # These get pulled from env or you can override in code:
    source: Literal[LoaderSource.ENVIRONMENT_OBJECT] = LoaderSource.ENVIRONMENT_OBJECT

    env_prefix: str | None = None

    @model_validator(mode="after")
    def default_env_prefix(self):
        if self.env_prefix is None:
            self.env_prefix = to_env_prefix(self.alias_name)
        return self

    @override
    def load_raw(
        self,
    ) -> dict[str, Any]:
        """Collects environment variables to build a dict matching the discriminated union fields,
        keyed by discriminator and field names, ready for Pydantic validation.
        """
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
