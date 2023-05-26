import re
from typing import NamedTuple

import pytest
from dagster._annotations import experimental
from dagster._check import CheckError
from dagster._utils.backcompat import (
    ExperimentalWarning,
    canonicalize_backcompat_args,
    experimental_arg_warning,
)

from dagster_tests.general_tests.utils_tests.utils import assert_no_warnings


def is_new(old_flag=None, new_flag=None, include_additional_warn_txt=True):
    actual_new_flag = canonicalize_backcompat_args(
        new_val=new_flag,
        new_arg="new_flag",
        old_val=old_flag,
        old_arg="old_flag",
        breaking_version="0.9.0",
        coerce_old_to_new=lambda val: not val,
        additional_warn_txt="Will remove at next release." if include_additional_warn_txt else None,
    )

    return actual_new_flag


def test_backcompat_default():
    assert is_new() is None


def test_backcompat_new_flag():
    assert is_new(new_flag=False) is False


def test_backcompat_old_flag():
    with pytest.warns(
        DeprecationWarning,
        match=re.escape(
            '"old_flag" is deprecated and will be removed in 0.9.0. Use "new_flag" instead. Will '
            "remove at next release."
        ),
    ):
        assert is_new(old_flag=False) is True


def test_backcompat_no_additional_warn_text():
    with pytest.warns(
        DeprecationWarning,
        match=re.escape(
            '"old_flag" is deprecated and will be removed in 0.9.0. Use "new_flag" instead.'
        ),
    ):
        assert is_new(old_flag=False, include_additional_warn_txt=False) is True


def test_backcompat_both_set():
    with pytest.raises(
        CheckError,
        match=re.escape('Do not use deprecated "old_flag" now that you are using "new_flag".'),
    ):
        is_new(old_flag=False, new_flag=True)


def test_experimental_fn_warning():
    @experimental
    def my_experimental_function():
        pass

    with pytest.warns(
        ExperimentalWarning,
        match=(
            '"my_experimental_function" is an experimental function. It may break in future'
            " versions, even between dot releases. "
        ),
    ) as warning:
        my_experimental_function()

    assert warning[0].filename.endswith("test_backcompat.py")


def test_experimental_class_warning():
    @experimental
    class MyExperimentalClass:
        def __init__(self):
            pass

    with pytest.warns(
        ExperimentalWarning,
        match=(
            '"MyExperimentalClass" is an experimental class. It may break in future'
            " versions, even between dot releases. "
        ),
    ) as warning:
        MyExperimentalClass()

    assert warning[0].filename.endswith("test_backcompat.py")


def test_experimental_class_with_methods():
    @experimental
    class ExperimentalClass:
        def __init__(self, salutation="hello"):
            self.salutation = salutation

        def hello(self, name):
            return f"{self.salutation} {name}"

    @experimental
    class ExperimentalClassWithExperimentalFunction(ExperimentalClass):
        def __init__(self, sendoff="goodbye", **kwargs):
            self.sendoff = sendoff
            super().__init__(**kwargs)

        @experimental
        def goodbye(self, name):
            return f"{self.sendoff} {name}"

    with pytest.warns(
        ExperimentalWarning,
        match=(
            '"ExperimentalClass" is an experimental class. It may break in future versions, even'
            " between dot releases."
        ),
    ):
        experimental_class = ExperimentalClass(salutation="howdy")

    with assert_no_warnings():
        assert experimental_class.hello("dagster") == "howdy dagster"

    with pytest.warns(
        ExperimentalWarning,
        match=(
            '"ExperimentalClassWithExperimentalFunction" is an experimental class. It may break in'
            " future versions, even between dot releases."
        ),
    ):
        experimental_class_with_experimental_function = ExperimentalClassWithExperimentalFunction()

    with assert_no_warnings():
        assert experimental_class_with_experimental_function.hello("dagster") == "hello dagster"

    with pytest.warns(
        ExperimentalWarning,
        match=(
            '"goodbye" is an experimental function. It may break in future versions, even between'
            " dot releases."
        ),
    ):
        assert experimental_class_with_experimental_function.goodbye("dagster") == "goodbye dagster"

    @experimental
    class ExperimentalNamedTupleClass(NamedTuple("_", [("salutation", str)])):
        pass

    with pytest.warns(
        ExperimentalWarning,
        match=(
            '"ExperimentalNamedTupleClass" is an experimental class. It may break in future'
            " versions, even between dot releases."
        ),
    ):
        assert ExperimentalNamedTupleClass(salutation="howdy").salutation == "howdy"


def test_experimental_arg_warning():
    def stable_function(_stable_arg, _experimental_arg):
        experimental_arg_warning("experimental_arg", "stable_function")

    with pytest.warns(
        ExperimentalWarning,
        match=(
            '"experimental_arg" is an experimental argument to function "stable_function". '
            "It may break in future versions, even between dot releases. "
        ),
    ) as warning:
        stable_function(1, 2)

    assert warning[0].filename.endswith("test_backcompat.py")
