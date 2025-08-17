from .loaders import Loader, ObjectLoaderEnvironment
from .schema.loader_type import LoaderSource

# use the loader to determine the default loader
DefaultLoader = ObjectLoaderEnvironment[Loader](
    # default loader is environment loader, unless configured
    # to something else in the environment
    default_discriminator_value=LoaderSource.ENVIRONMENT_OBJECT,
).discriminate_type()
