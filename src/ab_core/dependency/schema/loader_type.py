"""Loader source discriminator values."""

from enum import StrEnum


class LoaderSource(StrEnum):
    """Supported loader source identifiers."""

    ENVIRONMENT = "ENVIRONMENT"
    ENVIRONMENT_OBJECT = "ENVIRONMENT_OBJECT"
    TEMPLATE = "TEMPLATE"
