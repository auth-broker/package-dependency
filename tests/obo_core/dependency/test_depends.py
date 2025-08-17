import os
from typing import Annotated, Literal
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Discriminator, Field

from obo_core.dependency.depends import Depends, Load
from obo_core.dependency.loaders.environment_object import (
    ObjectLoaderEnvironment,
)


@pytest.fixture
def env_patch():
    # patch the environment so loading of FooBar works.
    with patch.dict(
        os.environ,
        {
            "CLASS_LABEL": "foo",
        },
        clear=False,
    ):
        yield


# depends on a class
class FooClass(BaseModel):
    label: Literal["foo"] = "foo"
    foo: str = "foo"


class BarClass(BaseModel):
    label: Literal["bar"] = "bar"
    bar: str = "bar"


# depends on an pydantic discriminated union
FooBar = Annotated[FooClass | BarClass, Discriminator("label")]


# depends on a function
def foo():
    return FooClass()


def bar():
    return BarClass()


LOAD_TARGETS = [
    foo,
    bar,
    FooClass,
    BarClass,
    FooBar,
    ObjectLoaderEnvironment[FooClass](),
    ObjectLoaderEnvironment[BarClass](),
]


@pytest.mark.parametrize("load_target", LOAD_TARGETS)
def test_depends(load_target, env_patch):
    one = Load(load_target, persist=True)
    two = Load(load_target, persist=True)
    three = Load(load_target, persist=False)

    assert one is two
    assert one is not three
    assert two is not three


@pytest.mark.parametrize("load_target", LOAD_TARGETS)
def test_lazy_depends(load_target, env_patch):
    one = Depends(load_target, persist=True)()
    two = Depends(load_target, persist=True)()
    three = Depends(load_target, persist=False)()

    assert one is two
    assert one is not three
    assert two is not three


@pytest.mark.parametrize("load_target", LOAD_TARGETS)
def test_depends_from_loader_pydantic(load_target, env_patch):
    class _(BaseModel):
        # BarLoader is e.g. EnvironmentLoader[Bar]
        one: BarClass = Field(
            default=Load(
                load_target,
                persist=True,
            )
        )
        two: BarClass = Field(
            default=Load(
                load_target,
                persist=True,
            )
        )

    inst = _()
    # pydantic performs a deep copy beehind the scenes
    assert inst.one is not inst.two
    assert inst.one == inst.two


@pytest.mark.parametrize("load_target", LOAD_TARGETS)
def test_lazy_depends_from_loader_pydantic(load_target, env_patch):
    class _(BaseModel):
        # BarLoader is e.g. EnvironmentLoader[Bar]
        one: BarClass = Field(
            default_factory=Depends(
                load_target,
                persist=True,
            )
        )
        two: BarClass = Field(
            default_factory=Depends(
                load_target,
                persist=True,
            )
        )

    inst = _()
    # pydantic performs a deep copy beehind the scenes
    assert inst.one is inst.two
    assert inst.one == inst.two
