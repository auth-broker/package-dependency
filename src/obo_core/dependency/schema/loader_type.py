from enum import StrEnum


class LoaderSource(StrEnum):
    ENVIRONMENT = "ENVIRONMENT"
    ENVIRONMENT_OBJECT = "ENVIRONMENT_OBJECT"
    TEMPLATE = "TEMPLATE"
