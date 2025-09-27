from typing import Annotated, Union

from pydantic import Discriminator

from .environment import LoaderEnvironment
from .environment_object import ObjectLoaderEnvironment
from .template import LoaderTemplate

Loader = Annotated[
    ObjectLoaderEnvironment | LoaderEnvironment | LoaderTemplate,
    Discriminator("source"),
]
