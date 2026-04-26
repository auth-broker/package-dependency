# ab-dependency

A lightweight dependency loading and injection package for Python.

`ab-dependency` provides a small dependency system for loading objects from environment variables, Python callables, Pydantic models, attrs classes, and custom loaders. It is designed to feel familiar if you have used FastAPI dependencies, while also working outside FastAPI.

## Disclaimer

Whilst this package was originally built for the Open Source auth-broker package. It is published to PyPI and intended to be used for any python project, due to its high lvel of convenience.

## Features

- Load Pydantic models from environment variables
- Load primitive values from environment variables
- Support discriminated unions
- Support attrs classes by converting them to Pydantic-compatible models
- Support singleton-style persistent dependencies
- Support transient dependencies
- Inject dependencies into:
  - sync functions
  - async functions
  - sync generators
  - async generators
  - classes
  - Pydantic models
- Support generator dependency cleanup
- Support FastAPI dependency integration
- Support flattened environment variable conventions
- Support JSON serialised complex values, such as lists

## Installation

```bash
pip install ab-dependency
```

Or with `uv`:

```bash
uv add ab-dependency
```

## Basic usage

```python
from pydantic import BaseModel

from ab_core.dependency import Load


class AppConfig(BaseModel):
    host: str = "localhost"
    port: int = 8080


config = Load(AppConfig)

print(config.host)
print(config.port)
```

By default, object models are loaded from environment variables using the model name converted to env-var style.

For `AppConfig`, the default prefix is:

```text
APP_CONFIG
```

So these environment variables:

```bash
APP_CONFIG_HOST=0.0.0.0
APP_CONFIG_PORT=8000
```

produce:

```python
AppConfig(host="0.0.0.0", port=8000)
```

## Environment variable naming

Model names are converted from PascalCase or camelCase to uppercase snake case.

```python
OAuth2TokenStore -> O_AUTH2_TOKEN_STORE
HTTPServerConfig -> HTTP_SERVER_CONFIG
AppConfig        -> APP_CONFIG
```

Field names are appended to the prefix.

```bash
APP_CONFIG_HOST=0.0.0.0
APP_CONFIG_PORT=8000
```

Nested field names are flattened using underscores.

```python
class DatabaseConfig(BaseModel):
    host: str
    port: int


class AppConfig(BaseModel):
    database: DatabaseConfig
```

```bash
APP_CONFIG_DATABASE_HOST=localhost
APP_CONFIG_DATABASE_PORT=5432
```

## Loading primitive values

Use `LoaderEnvironment` when loading a single primitive value from a specific environment variable.

```python
from ab_core.dependency.loaders import LoaderEnvironment

port = LoaderEnvironment[int](key="PORT").load()
```

```bash
PORT=8080
```

The value is validated and cast using Pydantic.

## Persistent dependencies

`Load(..., persist=True)` caches the loaded dependency.

```python
from pydantic import BaseModel
from ab_core.dependency import Load


class Client(BaseModel):
    name: str = "client"


one = Load(Client, persist=True)
two = Load(Client, persist=True)

assert one is two
```

Transient dependencies are created each time.

```python
one = Load(Client, persist=False)
two = Load(Client, persist=False)

assert one is not two
assert one == two
```

## Lazy dependencies

Use `Depends` to defer loading until call time.

```python
from typing import Annotated

from pydantic import BaseModel

from ab_core.dependency import Depends, inject


class Settings(BaseModel):
    value: str = "hello"


@inject
def run(settings: Annotated[Settings, Depends(Settings)]):
    return settings.value


assert run() == "hello"
```

## Function injection

```python
from typing import Annotated

from pydantic import BaseModel

from ab_core.dependency import Depends, inject


class Database(BaseModel):
    url: str = "sqlite://"


@inject
def handler(db: Annotated[Database, Depends(Database)]):
    return db.url
```

Dependencies are only resolved when the argument was not explicitly provided.

```python
handler(Database(url="postgresql://"))
```

## Async function injection

```python
from typing import Annotated

from ab_core.dependency import Depends, inject


async def make_token() -> str:
    return "abc"


@inject
async def handler(token: Annotated[str, Depends(make_token)]):
    return token
```

## Generator dependency support

Generator dependencies are entered before the function runs and cleaned up afterwards.

```python
from typing import Annotated

from ab_core.dependency import Depends, inject


def resource():
    try:
        yield "resource"
    finally:
        print("closed")


@inject
def handler(value: Annotated[str, Depends(resource)]):
    return value
```

Exceptions are thrown back into the generator so `except` and `finally` blocks can run.

```python
def resource():
    try:
        yield "resource"
    except Exception:
        print("caught")
        raise
    finally:
        print("closed")
```

## Class injection

```python
from typing import Annotated

from pydantic import BaseModel

from ab_core.dependency import Depends, inject


class Settings(BaseModel):
    value: str = "hello"


@inject
class Service:
    settings: Annotated[Settings, Depends(Settings)]

    def run(self):
        return self.settings.value
```

## Pydantic model injection

```python
from typing import Annotated

from pydantic import BaseModel

from ab_core.dependency import Depends, inject


class Settings(BaseModel):
    value: str = "hello"


@inject
class AppConfig(BaseModel):
    settings: Annotated[Settings, Depends(Settings)]
    retries: int = 3
```

If a field is supplied by input data, the dependency is not resolved.

## FastAPI integration

`Depends` subclasses FastAPI's dependency parameter when FastAPI is installed.

```python
from typing import Annotated

from fastapi import Depends as FDepends, FastAPI
from pydantic import BaseModel

from ab_core.dependency import Depends, inject


class SomeDependency(BaseModel):
    value: str = "injected"


def provide_dependency() -> SomeDependency:
    return SomeDependency()


@inject
def context(dep: Annotated[SomeDependency, Depends(provide_dependency)]):
    try:
        yield dep
    finally:
        pass


app = FastAPI()


@app.get("/")
def route(dep: Annotated[SomeDependency, FDepends(context)]):
    return {"value": dep.value}
```

## Discriminated unions

Discriminated unions are supported through Pydantic's `Discriminator`.

```python
from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator

from ab_core.dependency import Load


class FileStore(BaseModel):
    type: Literal["FILE"] = "FILE"
    path: str


class S3Store(BaseModel):
    type: Literal["S3"] = "S3"
    bucket: str


Store = Annotated[FileStore | S3Store, Discriminator("type")]

store = Load(Store)
```

Environment variables:

```bash
STORE_TYPE=S3
STORE_S3_BUCKET=my-bucket
```

Result:

```python
S3Store(type="S3", bucket="my-bucket")
```

## Flattened discriminator convention

For discriminated unions, the discriminator selects which nested branch is used.

```bash
DUMMY_STORE_TYPE=A
DUMMY_STORE_A_FOO=hello
DUMMY_STORE_A_NUM=42
```

This becomes:

```python
{
    "type": "A",
    "foo": "hello",
    "num": 42,
}
```

## attrs support

attrs classes can be loaded by converting them into Pydantic-compatible models.

```python
import attrs

from ab_core.dependency import Load
from ab_core.dependency.pydanticize import pydanticize_type


@attrs.define
class Settings:
    host: str = "localhost"
    port: int = 8080


SettingsModel = pydanticize_type(Settings)
settings = Load(SettingsModel)
```

attrs defaults and factories are preserved.

## List support

Simple lists can be supplied as JSON strings.

```python
from pydantic import BaseModel

from ab_core.dependency import Load


class Config(BaseModel):
    values: list[str]
```

```bash
CONFIG_VALUES='["A", "B", "C"]'
```

Result:

```python
Config(values=["A", "B", "C"])
```

## Planned recursive list environment convention

For recursive object loading, lists may also be represented as indexed environment variables.

Simple values:

```bash
CONFIG_VALUES_0=A
CONFIG_VALUES_1=B
CONFIG_VALUES_2=C
```

Equivalent JSON form:

```bash
CONFIG_VALUES='["A", "B", "C"]'
```

Lists of Pydantic models:

```python
from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator


class BlahItem(BaseModel):
    type: Literal["blah"] = "blah"
    label: str


class OtherItem(BaseModel):
    type: Literal["other"] = "other"
    label: str


Item = Annotated[BlahItem | OtherItem, Discriminator("type")]


class SomeObject(BaseModel):
    list_field: list[Item]
```

Environment variables:

```bash
SOME_OBJECT_LIST_FIELD_0_TYPE=blah
SOME_OBJECT_LIST_FIELD_0_BLAH_LABEL=first
SOME_OBJECT_LIST_FIELD_1_TYPE=other
SOME_OBJECT_LIST_FIELD_1_OTHER_LABEL=second
```

Expected result:

```python
SomeObject(
    list_field=[
        BlahItem(type="blah", label="first"),
        OtherItem(type="other", label="second"),
    ]
)
```

This keeps backwards compatibility with the existing JSON form while allowing recursive, schema-aware environment unpacking.

## Custom loaders

Create a custom loader by subclassing `LoaderBase`.

```python
from typing import Any

from ab_core.dependency.loaders.base import LoaderBase


class MyLoader(LoaderBase[str]):
    key: str

    def load_raw(self) -> Any:
        return f"value-for-{self.key}"
```

Then use it directly:

```python
loader = MyLoader[str](key="example")
value = loader.load()
```

## Public API

```python
from ab_core.dependency import (
    Depends,
    Load,
    inject,
    sentinel,
    pydanticize_data,
    pydanticize_type,
    pydanticize_object,
    cached_type_adapter,
    is_supported_by_pydantic,
)
```

## Design notes

`Load` resolves immediately.

```python
settings = Load(Settings)
```

`Depends` resolves lazily.

```python
settings: Annotated[Settings, Depends(Settings)]
```

`persist=True` caches by load target or loaded type.

```python
Depends(Settings, persist=True)
```

`persist=False` creates a fresh dependency each time.

```python
Depends(Settings, persist=False)
```

## Development

Run tests:

```bash
pytest
```

Run formatting and linting:

```bash
ruff check .
ruff format .
```

## Compatibility goals

The package aims to keep existing behaviour stable:

* Existing JSON list loading should continue to work.
* Existing flat object env-var loading should continue to work.
* Existing discriminator conventions should continue to work.
* New recursive list loading should be additive.
