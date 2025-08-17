import os
from typing import Annotated, Literal, Optional, Union
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from ab_core.dependency.depends import Load


def test_depends_complex_object():
    class ComplexObject(BaseModel):
        annotated_list: Annotated[list[float], Field(description="List of floats")]
        list_value: list[str]
        optional_list: Optional[list[int]]
        list_of_annotated: list[Annotated[str, Field(min_length=1)]]
        union_list: Union[list[str], None]
        literal_list: list[Literal["A", "B", "C"]]

    with patch.dict(
        os.environ,
        {
            "COMPLEX_OBJECT_LIST_VALUE": '["A","B","C","D"]',
            "COMPLEX_OBJECT_LIST_OF_ANNOTATED": '["X", "Y"]',
            "COMPLEX_OBJECT_ANNOTATED_LIST": "[1.1, 2.2, 3.3]",
            "COMPLEX_OBJECT_OPTIONAL_LIST": "[1, 2, 3]",
            "COMPLEX_OBJECT_UNION_LIST": '["alpha", "beta"]',
            "COMPLEX_OBJECT_LITERAL_LIST": '["A", "B"]',
        },
        clear=False,
    ):
        instance = Load(ComplexObject, persist=True)

        # ――― model instance is correct ―――
        assert isinstance(instance, ComplexObject)

        # ――― annotated_list ―――
        assert instance.annotated_list == [1.1, 2.2, 3.3]
        assert all(isinstance(x, float) for x in instance.annotated_list)

        # ――― list_value ―――
        assert instance.list_value == ["A", "B", "C", "D"]
        assert all(isinstance(x, str) for x in instance.list_value)

        # ――― optional_list ―――
        assert instance.optional_list == [1, 2, 3]
        assert all(isinstance(x, int) for x in instance.optional_list)

        # ――― list_of_annotated ―――
        assert instance.list_of_annotated == ["X", "Y"]
        assert all(isinstance(x, str) and len(x) >= 1 for x in instance.list_of_annotated)

        # ――― union_list (Optional list[str]) ―――
        assert instance.union_list == ["alpha", "beta"]
        assert all(isinstance(x, str) for x in instance.union_list)

        # ――― literal_list (items limited to "A", "B", "C") ―――
        assert instance.literal_list == ["A", "B"]
        assert all(x in ("A", "B", "C") for x in instance.literal_list)


@pytest.mark.skip("just for comparison")
def test_base_settings():
    class ComplexObject(BaseSettings):
        COMPLEX_OBJECT_LIST_VALUE: list[str]

    with patch.dict(
        os.environ,
        {
            "COMPLEX_OBJECT_LIST_VALUE": '["A","B","C","D"]',
        },
        clear=False,
    ):
        instance = ComplexObject()

        assert instance is ComplexObject
        assert instance.list_value is list
