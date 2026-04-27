"""Loader type exports and tagged union helpers."""

from typing import Annotated

from pydantic import Discriminator

from .environment import LoaderEnvironment
from .environment_object import ObjectLoaderEnvironment
from .template import LoaderTemplate

Loader = Annotated[
    ObjectLoaderEnvironment | LoaderEnvironment | LoaderTemplate,
    Discriminator("source"),
]
