# tests/test_attrs_plugin_via_router.py
import types
import attrs
import pytest
from typing import Optional, Union, Annotated

from pydantic import BaseModel, ValidationError
from ab_core.dependency.pydanticize import pydanticize_type


def test_simple_required_and_defaults():
    @attrs.define
    class A:
        x: int                                # required
        y: str = "hi"                         # default
        z: list[int] = attrs.field(factory=list)  # default_factory

    Model = pydanticize_type(A)
    assert issubclass(Model, BaseModel)

    # Required enforced
    with pytest.raises(ValidationError):
        Model()  # missing x

    m = Model(x=1)
    assert (m.x, m.y, m.z) == (1, "hi", [])
    # default_factory should give a fresh list per instance
    m2 = Model(x=2)
    assert m2.z == [] and m2.z is not m.z


def test_nested_attrs_instances_are_accepted():
    @attrs.define
    class Child:
        a: int

    @attrs.define
    class Parent:
        child: Child
        name: str

    ParentModel = pydanticize_type(Parent)
    ChildModel = pydanticize_type(Child)

    # Passing a Child BaseModel instance
    p = ParentModel(child=ChildModel(a=5), name="ok")
    assert isinstance(p.child, ChildModel)
    assert p.child.a == 5
    assert p.name == "ok"


def test_nested_attrs_from_dict_is_parsed():
    @attrs.define
    class Child:
        a: int

    @attrs.define
    class Parent:
        child: Child
        tag: str

    ParentModel = pydanticize_type(Parent)

    # Dicts should coerce to the generated BaseModel for Child
    p = ParentModel(child={"a": 10}, tag="t")
    assert isinstance(p.child, BaseModel)
    assert p.child.a == 10
    assert p.tag == "t"


def test_optional_and_union_are_supported_as_is():
    @attrs.define
    class A:
        maybe: Optional[int]
        either: Union[int, str]

    Model = pydanticize_type(A)

    m = Model(maybe=None, either="x")
    assert (m.maybe, m.either) == (None, "x")

    m2 = Model(maybe=3, either=5)
    assert (m2.maybe, m2.either) == (3, 5)


def test_defaults_respected_for_falsey_values():
    @attrs.define
    class A:
        n: int = 0
        s: str = ""
        b: bool = False

    Model = pydanticize_type(A)
    m = Model(n=0, s="", b=False)
    assert (m.n, m.s, m.b) == (0, "", False)
