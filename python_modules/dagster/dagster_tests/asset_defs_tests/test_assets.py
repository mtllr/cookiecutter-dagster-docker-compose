import ast
import datetime
import tempfile
from typing import Sequence

import pytest
from dagster import (
    AssetKey,
    AssetOut,
    AssetsDefinition,
    DagsterEventType,
    DailyPartitionsDefinition,
    Definitions,
    EventRecordsFilter,
    FreshnessPolicy,
    GraphOut,
    IOManager,
    IOManagerDefinition,
    LastPartitionMapping,
    Out,
    Output,
    ResourceDefinition,
    build_op_context,
    define_asset_job,
    fs_io_manager,
    graph,
    io_manager,
    job,
    materialize,
    materialize_to_memory,
    op,
    resource,
    with_resources,
)
from dagster._check import CheckError
from dagster._core.definitions import AssetIn, SourceAsset, asset, multi_asset
from dagster._core.definitions.auto_materialize_policy import AutoMaterializePolicy
from dagster._core.errors import (
    DagsterInvalidDefinitionError,
    DagsterInvalidInvocationError,
    DagsterInvalidPropertyError,
)
from dagster._core.instance import DagsterInstance
from dagster._core.storage.mem_io_manager import InMemoryIOManager
from dagster._core.test_utils import instance_for_test


def test_with_replaced_asset_keys():
    @asset(ins={"input2": AssetIn(key_prefix="something_else")})
    def asset1(input1, input2):
        assert input1
        assert input2

    replaced = asset1.with_attributes(
        output_asset_key_replacements={
            AssetKey(["asset1"]): AssetKey(["prefix1", "asset1_changed"])
        },
        input_asset_key_replacements={
            AssetKey(["something_else", "input2"]): AssetKey(["apple", "banana"])
        },
    )

    assert set(replaced.dependency_keys) == {
        AssetKey("input1"),
        AssetKey(["apple", "banana"]),
    }
    assert replaced.keys == {AssetKey(["prefix1", "asset1_changed"])}

    assert replaced.keys_by_input_name["input1"] == AssetKey("input1")

    assert replaced.keys_by_input_name["input2"] == AssetKey(["apple", "banana"])

    assert replaced.keys_by_output_name["result"] == AssetKey(["prefix1", "asset1_changed"])


@pytest.mark.parametrize(
    "subset,expected_keys,expected_inputs,expected_outputs",
    [
        ("foo,bar,baz,in1,in2,in3,a,b,c,foo2,bar2,baz2", "a,b,c", 3, 3),
        ("foo,bar,baz", None, 0, 0),
        ("in1,a,b,c", "a,b,c", 3, 3),
        ("foo,in1,a,b,c,bar", "a,b,c", 3, 3),
        ("foo,in1,in2,in3,a,bar", "a", 2, 1),
        ("foo,in1,in2,a,b,bar", "a,b", 2, 2),
        ("in1,in2,in3,b", "b", 0, 1),
    ],
)
def test_subset_for(subset, expected_keys, expected_inputs, expected_outputs):
    @multi_asset(
        outs={"a": AssetOut(), "b": AssetOut(), "c": AssetOut()},
        internal_asset_deps={
            "a": {AssetKey("in1"), AssetKey("in2")},
            "b": set(),
            "c": {AssetKey("a"), AssetKey("b"), AssetKey("in2"), AssetKey("in3")},
        },
        can_subset=True,
    )
    def abc_(context, in1, in2, in3):
        pass

    subbed = abc_.subset_for({AssetKey(key) for key in subset.split(",")})

    assert subbed.keys == (
        {AssetKey(key) for key in expected_keys.split(",")} if expected_keys else set()
    )

    assert len(subbed.keys_by_input_name) == expected_inputs
    assert len(subbed.keys_by_output_name) == expected_outputs

    # the asset dependency structure should stay the same
    assert subbed.asset_deps == abc_.asset_deps


def test_retain_group():
    @asset(group_name="foo")
    def bar():
        pass

    replaced = bar.with_attributes(
        output_asset_key_replacements={AssetKey(["bar"]): AssetKey(["baz"])}
    )
    assert replaced.group_names_by_key[AssetKey("baz")] == "foo"


def test_retain_freshness_policy():
    fp = FreshnessPolicy(maximum_lag_minutes=24.5)

    @asset(freshness_policy=fp)
    def bar():
        pass

    replaced = bar.with_attributes(
        output_asset_key_replacements={AssetKey(["bar"]): AssetKey(["baz"])}
    )
    assert (
        replaced.freshness_policies_by_key[AssetKey(["baz"])]
        == bar.freshness_policies_by_key[AssetKey(["bar"])]
    )


def test_graph_backed_retain_freshness_policy_and_auto_materialize_policy():
    fpa = FreshnessPolicy(maximum_lag_minutes=24.5)
    fpb = FreshnessPolicy(
        maximum_lag_minutes=30.5, cron_schedule="0 0 * * *", cron_schedule_timezone="US/Eastern"
    )
    ampa = AutoMaterializePolicy.eager()
    ampb = AutoMaterializePolicy.lazy()

    @op
    def foo():
        return 1

    @op
    def bar(inp):
        return inp + 1

    @graph(out={"a": GraphOut(), "b": GraphOut(), "c": GraphOut()})
    def my_graph():
        f = foo()
        return bar(f), bar(f), bar(f)

    my_graph_asset = AssetsDefinition.from_graph(
        my_graph,
        freshness_policies_by_output_name={"a": fpa, "b": fpb},
        auto_materialize_policies_by_output_name={"a": ampa, "b": ampb},
    )

    replaced = my_graph_asset.with_attributes(
        output_asset_key_replacements={
            AssetKey("a"): AssetKey("aa"),
            AssetKey("b"): AssetKey("bb"),
            AssetKey("c"): AssetKey("cc"),
        }
    )
    assert replaced.freshness_policies_by_key[AssetKey("aa")] == fpa
    assert replaced.freshness_policies_by_key[AssetKey("bb")] == fpb
    assert replaced.freshness_policies_by_key.get(AssetKey("cc")) is None

    assert replaced.auto_materialize_policies_by_key[AssetKey("aa")] == ampa
    assert replaced.auto_materialize_policies_by_key[AssetKey("bb")] == ampb
    assert replaced.auto_materialize_policies_by_key.get(AssetKey("cc")) is None


def test_retain_metadata_graph():
    @op
    def foo():
        return 1

    @graph
    def bar():
        return foo()

    md = {"foo": "bar", "baz": 12.5}
    original = AssetsDefinition.from_graph(bar, metadata_by_output_name={"result": md})

    replaced = original.with_attributes(
        output_asset_key_replacements={AssetKey(["bar"]): AssetKey(["baz"])}
    )
    assert (
        replaced.metadata_by_key[AssetKey(["baz"])] == original.metadata_by_key[AssetKey(["bar"])]
    )


def test_retain_group_subset():
    @op(out={"a": Out(), "b": Out()})
    def ma_op():
        return 1

    ma = AssetsDefinition(
        node_def=ma_op,
        keys_by_input_name={},
        keys_by_output_name={"a": AssetKey("a"), "b": AssetKey("b")},
        group_names_by_key={AssetKey("a"): "foo", AssetKey("b"): "bar"},
        can_subset=True,
    )

    subset = ma.subset_for({AssetKey("b")})
    assert subset.group_names_by_key[AssetKey("b")] == "bar"


def test_retain_partition_mappings():
    @asset(
        ins={"input_last": AssetIn(["input_last"], partition_mapping=LastPartitionMapping())},
        partitions_def=DailyPartitionsDefinition(datetime.datetime(2022, 1, 1)),
    )
    def bar_(input_last):
        pass

    assert isinstance(bar_.get_partition_mapping(AssetKey(["input_last"])), LastPartitionMapping)

    replaced = bar_.with_attributes(
        input_asset_key_replacements={
            AssetKey(["input_last"]): AssetKey(["input_last2"]),
        }
    )

    assert isinstance(
        replaced.get_partition_mapping(AssetKey(["input_last2"])), LastPartitionMapping
    )


def test_chain_replace_and_subset_for():
    @multi_asset(
        outs={"a": AssetOut(), "b": AssetOut(), "c": AssetOut()},
        internal_asset_deps={
            "a": {AssetKey("in1"), AssetKey("in2")},
            "b": set(),
            "c": {AssetKey("a"), AssetKey("b"), AssetKey("in2"), AssetKey("in3")},
        },
        can_subset=True,
    )
    def abc_(context, in1, in2, in3):
        pass

    replaced_1 = abc_.with_attributes(
        output_asset_key_replacements={AssetKey(["a"]): AssetKey(["foo", "foo_a"])},
        input_asset_key_replacements={AssetKey(["in1"]): AssetKey(["foo", "bar_in1"])},
    )

    assert replaced_1.keys == {AssetKey(["foo", "foo_a"]), AssetKey("b"), AssetKey("c")}
    assert replaced_1.asset_deps == {
        AssetKey(["foo", "foo_a"]): {AssetKey(["foo", "bar_in1"]), AssetKey("in2")},
        AssetKey("b"): set(),
        AssetKey("c"): {
            AssetKey(["foo", "foo_a"]),
            AssetKey("b"),
            AssetKey("in2"),
            AssetKey("in3"),
        },
    }

    subbed_1 = replaced_1.subset_for(
        {AssetKey(["foo", "bar_in1"]), AssetKey("in3"), AssetKey(["foo", "foo_a"]), AssetKey("b")}
    )
    assert subbed_1.keys == {AssetKey(["foo", "foo_a"]), AssetKey("b")}

    replaced_2 = subbed_1.with_attributes(
        output_asset_key_replacements={
            AssetKey(["foo", "foo_a"]): AssetKey(["again", "foo", "foo_a"]),
            AssetKey(["b"]): AssetKey(["something", "bar_b"]),
        },
        input_asset_key_replacements={
            AssetKey(["foo", "bar_in1"]): AssetKey(["again", "foo", "bar_in1"]),
            AssetKey(["in2"]): AssetKey(["foo", "in2"]),
            AssetKey(["in3"]): AssetKey(["foo", "in3"]),
        },
    )
    assert replaced_2.keys == {
        AssetKey(["again", "foo", "foo_a"]),
        AssetKey(["something", "bar_b"]),
    }
    assert replaced_2.asset_deps == {
        AssetKey(["again", "foo", "foo_a"]): {
            AssetKey(["again", "foo", "bar_in1"]),
            AssetKey(["foo", "in2"]),
        },
        AssetKey(["something", "bar_b"]): set(),
        AssetKey("c"): {
            AssetKey(["again", "foo", "foo_a"]),
            AssetKey(["something", "bar_b"]),
            AssetKey(["foo", "in2"]),
            AssetKey(["foo", "in3"]),
        },
    }

    subbed_2 = replaced_2.subset_for(
        {
            AssetKey(["again", "foo", "bar_in1"]),
            AssetKey(["again", "foo", "foo_a"]),
            AssetKey(["c"]),
        }
    )
    assert subbed_2.keys == {AssetKey(["again", "foo", "foo_a"])}


def test_fail_on_subset_for_nonsubsettable():
    @multi_asset(outs={"a": AssetOut(), "b": AssetOut(), "c": AssetOut()})
    def abc_(context, start):
        pass

    with pytest.raises(CheckError, match="can_subset=False"):
        abc_.subset_for({AssetKey("start"), AssetKey("a")})


def test_to_source_assets():
    @asset(metadata={"a": "b"}, io_manager_key="abc", description="blablabla")
    def my_asset():
        ...

    assert (
        my_asset.to_source_assets()
        == [my_asset.to_source_asset()]
        == [
            SourceAsset(
                AssetKey(["my_asset"]),
                metadata={"a": "b"},
                io_manager_key="abc",
                description="blablabla",
            )
        ]
    )

    @multi_asset(
        outs={
            "my_out_name": AssetOut(
                key=AssetKey("my_asset_name"),
                metadata={"a": "b"},
                io_manager_key="abc",
                description="blablabla",
            ),
            "my_other_out_name": AssetOut(
                key=AssetKey("my_other_asset"),
                metadata={"c": "d"},
                io_manager_key="def",
                description="ablablabl",
            ),
        }
    )
    def my_multi_asset():
        yield Output(1, "my_out_name")
        yield Output(2, "my_other_out_name")

    my_asset_name_source_asset = SourceAsset(
        AssetKey(["my_asset_name"]),
        metadata={"a": "b"},
        io_manager_key="abc",
        description="blablabla",
    )
    my_other_asset_source_asset = SourceAsset(
        AssetKey(["my_other_asset"]),
        metadata={"c": "d"},
        io_manager_key="def",
        description="ablablabl",
    )

    assert my_multi_asset.to_source_assets() == [
        my_asset_name_source_asset,
        my_other_asset_source_asset,
    ]

    assert (
        my_multi_asset.to_source_asset(AssetKey(["my_other_asset"])) == my_other_asset_source_asset
    )
    assert my_multi_asset.to_source_asset("my_other_asset") == my_other_asset_source_asset


def test_coerced_asset_keys():
    @asset(ins={"input1": AssetIn(asset_key=["Asset", "1"])})
    def asset1(input1):
        assert input1


def test_asset_with_io_manager_def():
    events = []

    class MyIOManager(IOManager):
        def handle_output(self, context, _obj):
            events.append(f"entered for {context.step_key}")

        def load_input(self, _context):
            pass

    @io_manager
    def the_io_manager():
        return MyIOManager()

    @asset(io_manager_def=the_io_manager)
    def the_asset():
        pass

    result = materialize([the_asset])
    assert result.success
    assert events == ["entered for the_asset"]


def test_asset_with_io_manager_def_plain_old_python_object_iomanager() -> None:
    events = []

    class MyIOManager(IOManager):
        def handle_output(self, context, _obj):
            events.append(f"entered for {context.step_key}")

        def load_input(self, _context):
            pass

    @asset(io_manager_def=MyIOManager())
    def the_asset():
        pass

    result = materialize([the_asset])
    assert result.success
    assert events == ["entered for the_asset"]


def test_multiple_assets_io_manager_defs():
    io_manager_inst = InMemoryIOManager()
    num_times = [0]

    @io_manager
    def the_io_manager():
        num_times[0] += 1
        return io_manager_inst

    # Under the hood, these io managers are mapped to different asset keys, so
    # we expect the io manager initialization to be called multiple times.
    @asset(io_manager_def=the_io_manager)
    def the_asset():
        return 5

    @asset(io_manager_def=the_io_manager)
    def other_asset():
        return 6

    materialize([the_asset, other_asset])

    assert num_times[0] == 2

    the_asset_key = [key for key in io_manager_inst.values.keys() if key[1] == "the_asset"][0]
    assert io_manager_inst.values[the_asset_key] == 5

    other_asset_key = [key for key in io_manager_inst.values.keys() if key[1] == "other_asset"][0]
    assert io_manager_inst.values[other_asset_key] == 6


def test_asset_with_io_manager_key_only():
    io_manager_inst = InMemoryIOManager()

    @io_manager
    def the_io_manager():
        return io_manager_inst

    @asset(io_manager_key="the_key")
    def the_asset():
        return 5

    materialize([the_asset], resources={"the_key": the_io_manager})

    assert list(io_manager_inst.values.values())[0] == 5


def test_asset_both_io_manager_args_provided():
    @io_manager
    def the_io_manager():
        pass

    with pytest.raises(
        CheckError,
        match=(
            "Both io_manager_key and io_manager_def were provided to `@asset` "
            "decorator. Please provide one or the other."
        ),
    ):

        @asset(io_manager_key="the_key", io_manager_def=the_io_manager)
        def the_asset():
            pass


def test_asset_invocation():
    @asset
    def the_asset():
        return 6

    assert the_asset() == 6


def test_asset_invocation_input():
    @asset
    def input_asset(x):
        return x

    assert input_asset(5) == 5


def test_asset_invocation_resource_overrides():
    @asset(required_resource_keys={"foo", "bar"})
    def asset_reqs_resources(context):
        assert context.resources.foo == "foo_resource"
        assert context.resources.bar == "bar_resource"

    asset_reqs_resources(build_op_context(resources={"foo": "foo_resource", "bar": "bar_resource"}))

    @asset(
        resource_defs={
            "foo": ResourceDefinition.hardcoded_resource("orig_foo"),
            "bar": ResourceDefinition.hardcoded_resource("orig_bar"),
        }
    )
    def asset_resource_overrides(context):
        assert context.resources.foo == "override_foo"
        assert context.resources.bar == "orig_bar"

    with pytest.raises(
        DagsterInvalidInvocationError,
        match="resource 'foo' provided on both the definition and invocation context.",
    ):
        asset_resource_overrides(build_op_context(resources={"foo": "override_foo"}))


def test_asset_invocation_resource_errors():
    @asset(resource_defs={"ignored": ResourceDefinition.hardcoded_resource("not_used")})
    def asset_doesnt_use_resources():
        pass

    asset_doesnt_use_resources()

    @asset(resource_defs={"used": ResourceDefinition.hardcoded_resource("foo")})
    def asset_uses_resources(context):
        assert context.resources.used == "foo"

    with pytest.raises(
        DagsterInvalidInvocationError,
        match='op "asset_uses_resources" has required resources, but no context was provided',
    ):
        asset_uses_resources(None)

    asset_uses_resources(build_op_context())

    @asset(required_resource_keys={"foo"})
    def required_key_not_provided(_):
        pass

    with pytest.raises(
        DagsterInvalidDefinitionError,
        match=(
            "resource with key 'foo' required by op 'required_key_not_provided' was not provided."
        ),
    ):
        required_key_not_provided(build_op_context())


def test_multi_asset_resources_execution():
    class MyIOManager(IOManager):
        def __init__(self, the_list):
            self._the_list = the_list

        def handle_output(self, _context, obj):
            self._the_list.append(obj)

        def load_input(self, _context):
            pass

    foo_list = []

    @resource
    def baz_resource():
        return "baz"

    @io_manager(required_resource_keys={"baz"})
    def foo_manager(context):
        assert context.resources.baz == "baz"
        return MyIOManager(foo_list)

    bar_list = []

    @io_manager
    def bar_manager():
        return MyIOManager(bar_list)

    @multi_asset(
        outs={
            "key1": AssetOut(key=AssetKey("key1"), io_manager_key="foo"),
            "key2": AssetOut(key=AssetKey("key2"), io_manager_key="bar"),
        },
        resource_defs={"foo": foo_manager, "bar": bar_manager, "baz": baz_resource},
    )
    def my_asset(context):
        # Required io manager keys are available on the context, same behavoir as ops
        assert hasattr(context.resources, "foo")
        assert hasattr(context.resources, "bar")
        yield Output(1, "key1")
        yield Output(2, "key2")

    with instance_for_test() as instance:
        materialize([my_asset], instance=instance)

    assert foo_list == [1]
    assert bar_list == [2]


def test_graph_backed_asset_resources():
    @op(required_resource_keys={"foo"})
    def the_op(context):
        assert context.resources.foo == "value"
        return context.resources.foo

    @graph
    def basic():
        return the_op()

    asset_provided_resources = AssetsDefinition.from_graph(
        graph_def=basic,
        keys_by_input_name={},
        keys_by_output_name={"result": AssetKey("the_asset")},
        resource_defs={"foo": ResourceDefinition.hardcoded_resource("value")},
    )
    result = materialize_to_memory([asset_provided_resources])
    assert result.success
    assert result.output_for_node("basic") == "value"

    asset_not_provided_resources = AssetsDefinition.from_graph(
        graph_def=basic,
        keys_by_input_name={},
        keys_by_output_name={"result": AssetKey("the_asset")},
    )
    result = materialize_to_memory([asset_not_provided_resources], resources={"foo": "value"})
    assert result.success
    assert result.output_for_node("basic") == "value"


def test_graph_backed_asset_io_manager():
    @op(required_resource_keys={"foo"}, out=Out(io_manager_key="the_manager"))
    def the_op(context):
        assert context.resources.foo == "value"
        return context.resources.foo

    @op
    def ingest(x):
        return x

    @graph
    def basic():
        return ingest(the_op())

    events = []

    class MyIOManager(IOManager):
        def handle_output(self, context, _obj):
            events.append(f"entered handle_output for {context.step_key}")

        def load_input(self, context):
            events.append(f"entered handle_input for {context.upstream_output.step_key}")

    asset_provided_resources = AssetsDefinition.from_graph(
        graph_def=basic,
        keys_by_input_name={},
        keys_by_output_name={"result": AssetKey("the_asset")},
        resource_defs={
            "foo": ResourceDefinition.hardcoded_resource("value"),
            "the_manager": IOManagerDefinition.hardcoded_io_manager(MyIOManager()),
        },
    )

    with instance_for_test() as instance:
        result = materialize([asset_provided_resources], instance=instance)
        assert result.success
        assert events == [
            "entered handle_output for basic.the_op",
            "entered handle_input for basic.the_op",
        ]


def test_invalid_graph_backed_assets():
    @op
    def a():
        return 1

    @op
    def validate(inp):
        return inp == 1

    @graph
    def foo():
        a_val = a()
        validate(a_val)
        return a_val

    @graph
    def bar():
        return foo()

    @graph
    def baz():
        return a(), bar(), a()

    with pytest.raises(CheckError, match=r"leaf nodes.*validate"):
        AssetsDefinition.from_graph(foo)

    with pytest.raises(CheckError, match=r"leaf nodes.*bar\.validate"):
        AssetsDefinition.from_graph(bar)

    with pytest.raises(CheckError, match=r"leaf nodes.*baz\.bar\.validate"):
        AssetsDefinition.from_graph(baz)


def test_group_name_requirements():
    @asset(group_name="float")  # reserved python keywords allowed
    def good_name():
        return 1

    with pytest.raises(DagsterInvalidDefinitionError, match="not a valid name in Dagster"):

        @asset(group_name="bad*name")  # regex mismatch
        def bad_name():
            return 2


def test_from_graph_w_key_prefix():
    @op
    def foo():
        return 1

    @op
    def bar(i):
        return i + 1

    @graph
    def silly_graph():
        return bar(foo())

    freshness_policy = FreshnessPolicy(maximum_lag_minutes=60)
    description = "This is a description!"
    metadata = {"test_metadata": "This is some metadata"}

    the_asset = AssetsDefinition.from_graph(
        graph_def=silly_graph,
        keys_by_input_name={},
        keys_by_output_name={"result": AssetKey(["the", "asset"])},
        key_prefix=["this", "is", "a", "prefix"],
        freshness_policies_by_output_name={"result": freshness_policy},
        descriptions_by_output_name={"result": description},
        metadata_by_output_name={"result": metadata},
        group_name="abc",
    )
    assert the_asset.keys_by_output_name["result"].path == [
        "this",
        "is",
        "a",
        "prefix",
        "the",
        "asset",
    ]

    assert the_asset.group_names_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): "abc"
    }

    assert the_asset.freshness_policies_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): freshness_policy
    }

    assert the_asset.descriptions_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): description
    }

    assert the_asset.metadata_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): metadata
    }

    str_prefix = AssetsDefinition.from_graph(
        graph_def=silly_graph,
        keys_by_input_name={},
        keys_by_output_name={"result": AssetKey(["the", "asset"])},
        key_prefix="prefix",
    )

    assert str_prefix.keys_by_output_name["result"].path == [
        "prefix",
        "the",
        "asset",
    ]


def test_from_op_w_key_prefix():
    @op
    def foo():
        return 1

    freshness_policy = FreshnessPolicy(maximum_lag_minutes=60)
    description = "This is a description!"
    metadata = {"test_metadata": "This is some metadata"}

    the_asset = AssetsDefinition.from_op(
        op_def=foo,
        keys_by_input_name={},
        keys_by_output_name={"result": AssetKey(["the", "asset"])},
        key_prefix=["this", "is", "a", "prefix"],
        freshness_policies_by_output_name={"result": freshness_policy},
        descriptions_by_output_name={"result": description},
        metadata_by_output_name={"result": metadata},
        group_name="abc",
    )

    assert the_asset.keys_by_output_name["result"].path == [
        "this",
        "is",
        "a",
        "prefix",
        "the",
        "asset",
    ]

    assert the_asset.group_names_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): "abc"
    }

    assert the_asset.freshness_policies_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): freshness_policy
    }

    assert the_asset.descriptions_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): description
    }

    assert the_asset.metadata_by_key == {
        AssetKey(["this", "is", "a", "prefix", "the", "asset"]): metadata
    }

    str_prefix = AssetsDefinition.from_op(
        op_def=foo,
        keys_by_input_name={},
        keys_by_output_name={"result": AssetKey(["the", "asset"])},
        key_prefix="prefix",
    )

    assert str_prefix.keys_by_output_name["result"].path == [
        "prefix",
        "the",
        "asset",
    ]


def test_from_op_w_configured():
    @op(config_schema={"bar": str})
    def foo():
        return 1

    the_asset = AssetsDefinition.from_op(op_def=foo.configured({"bar": "abc"}, name="foo2"))
    assert the_asset.keys_by_output_name["result"].path == ["foo2"]


def get_step_keys_from_run(instance: DagsterInstance) -> Sequence[str]:
    engine_events = list(
        instance.get_event_records(EventRecordsFilter(DagsterEventType.ENGINE_EVENT))
    )
    metadata = engine_events[0].event_log_entry.get_dagster_event().engine_event_data.metadata
    step_metadata = metadata["step_keys"]
    return ast.literal_eval(step_metadata.value)  # type: ignore


def get_num_events(instance, run_id, event_type):
    events = instance.get_records_for_run(run_id=run_id, of_type=event_type).records
    return len(events)


def test_graph_backed_asset_subset():
    @op()
    def foo():
        return 1

    @op
    def bar(foo):
        return foo

    @graph(out={"one": GraphOut(), "two": GraphOut()})
    def my_graph():
        one = foo()
        return bar.alias("bar_1")(one), bar.alias("bar_2")(one)

    asset_job = define_asset_job("yay").resolve(
        [
            AssetsDefinition.from_graph(my_graph, can_subset=True),
        ],
        [],
    )

    with instance_for_test() as instance:
        result = asset_job.execute_in_process(instance=instance, asset_selection=[AssetKey("one")])
        assert (
            get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION_PLANNED)
            == 1
        )
        assert get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION) == 1
        step_keys = get_step_keys_from_run(instance)
        assert set(step_keys) == set(["my_graph.foo", "my_graph.bar_1"])


def test_graph_backed_asset_partial_output_selection():
    @op(out={"a": Out(), "b": Out()})
    def foo():
        return 1, 2

    @graph(out={"one": GraphOut(), "two": GraphOut()})
    def graph_asset():
        one, two = foo()
        return one, two

    asset_job = define_asset_job("yay").resolve(
        [
            AssetsDefinition.from_graph(graph_asset, can_subset=True),
        ],
        [],
    )

    with instance_for_test() as instance:
        result = asset_job.execute_in_process(instance=instance, asset_selection=[AssetKey("one")])
        assert (
            get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION_PLANNED)
            == 1
        )
        # This test will yield two materialization events, for assets "one" and "two". This is
        # because the "foo" op will still be executed, even though we only selected "one".
        assert get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION) == 2
        step_keys = get_step_keys_from_run(instance)
        assert set(step_keys) == set(["graph_asset.foo"])


def test_input_subsetting_graph_backed_asset():
    @asset
    def upstream_1():
        return 1

    @asset
    def upstream_2():
        return 1

    @op
    def bar(foo):
        return foo

    @op
    def baz(up_1, up_2):
        return up_1 + up_2

    @graph(out={"one": GraphOut(), "two": GraphOut(), "three": GraphOut()})
    def my_graph(upstream_1, upstream_2):
        return (
            bar.alias("bar_1")(upstream_1),
            bar.alias("bar_2")(upstream_2),
            baz(upstream_1, upstream_2),
        )

    with tempfile.TemporaryDirectory() as tmpdir_path:
        asset_job = define_asset_job("yay").resolve(
            with_resources(
                [
                    upstream_1,
                    upstream_2,
                    AssetsDefinition.from_graph(my_graph, can_subset=True),
                ],
                resource_defs={"io_manager": fs_io_manager.configured({"base_dir": tmpdir_path})},
            ),
            [],
        )
        with instance_for_test() as instance:
            # test first bar alias
            result = asset_job.execute_in_process(
                instance=instance,
                asset_selection=[AssetKey("one"), AssetKey("upstream_1")],
            )
            assert result.success
            assert (
                get_num_events(
                    instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION_PLANNED
                )
                == 2
            )
            assert (
                get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION) == 2
            )
            step_keys = get_step_keys_from_run(instance)
            assert set(step_keys) == set(["my_graph.bar_1", "upstream_1"])

        # test second "bar" alias
        with instance_for_test() as instance:
            result = asset_job.execute_in_process(
                instance=instance,
                asset_selection=[AssetKey("two"), AssetKey("upstream_2")],
            )
            assert result.success
            assert (
                get_num_events(
                    instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION_PLANNED
                )
                == 2
            )
            assert (
                get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION) == 2
            )
            step_keys = get_step_keys_from_run(instance)
            assert set(step_keys) == set(["my_graph.bar_2", "upstream_2"])

        # test "baz" which uses both inputs
        with instance_for_test() as instance:
            result = asset_job.execute_in_process(
                instance=instance,
                asset_selection=[AssetKey("three"), AssetKey("upstream_1"), AssetKey("upstream_2")],
            )
            assert result.success
            assert (
                get_num_events(
                    instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION_PLANNED
                )
                == 3
            )
            assert (
                get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION) == 3
            )
            step_keys = get_step_keys_from_run(instance)
            assert set(step_keys) == set(["my_graph.baz", "upstream_1", "upstream_2"])


@pytest.mark.parametrize(
    "asset_selection,selected_output_names_op_1,selected_output_names_op_2,num_materializations",
    [
        ([AssetKey("asset_one")], {"out_1"}, None, 1),
        ([AssetKey("asset_two")], {"out_2"}, {"add_one_1"}, 1),
        (
            [AssetKey("asset_two"), AssetKey("asset_three")],
            {"out_2"},
            {"add_one_1", "add_one_2"},
            2,
        ),
        (
            [AssetKey("asset_one"), AssetKey("asset_two"), AssetKey("asset_three")],
            {"out_1", "out_2"},
            {"add_one_1", "add_one_2"},
            3,
        ),
    ],
)
def test_graph_backed_asset_subset_context(
    asset_selection, selected_output_names_op_1, selected_output_names_op_2, num_materializations
):
    @op(out={"out_1": Out(is_required=False), "out_2": Out(is_required=False)})
    def op_1(context):
        assert context.selected_output_names == selected_output_names_op_1
        if "out_1" in context.selected_output_names:
            yield Output(1, output_name="out_1")
        if "out_2" in context.selected_output_names:
            yield Output(1, output_name="out_2")

    @op(out={"add_one_1": Out(is_required=False), "add_one_2": Out(is_required=False)})
    def add_one(context, x):
        assert context.selected_output_names == selected_output_names_op_2
        if "add_one_1" in context.selected_output_names:
            yield Output(x, output_name="add_one_1")
        if "add_one_2" in context.selected_output_names:
            yield Output(x, output_name="add_one_2")

    @graph(out={"asset_one": GraphOut(), "asset_two": GraphOut(), "asset_three": GraphOut()})
    def three():
        out_1, reused_output = op_1()
        out_2, out_3 = add_one(reused_output)
        return {"asset_one": out_1, "asset_two": out_2, "asset_three": out_3}

    asset_job = define_asset_job("yay").resolve(
        [AssetsDefinition.from_graph(three, can_subset=True)],
        [],
    )

    with instance_for_test() as instance:
        result = asset_job.execute_in_process(asset_selection=asset_selection, instance=instance)
        assert result.success
        assert (
            get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION)
            == num_materializations
        )


@pytest.mark.parametrize(
    "asset_selection,selected_output_names_op_1,selected_output_names_op_3,num_materializations",
    [
        # Because out_1 of op_1 is an input to generate asset_one and is yielded as asset_4,
        # we materialize it even though it is not selected. A log message will indicate that it is
        # an unexpected materialization.
        ([AssetKey("asset_one")], {"out_1"}, None, 2),
        ([AssetKey("asset_two")], {"out_2"}, {"op_3_1"}, 1),
        ([AssetKey("asset_two"), AssetKey("asset_three")], {"out_2"}, {"op_3_1", "op_3_2"}, 2),
        ([AssetKey("asset_four"), AssetKey("asset_three")], {"out_1", "out_2"}, {"op_3_2"}, 2),
        ([AssetKey("asset_one"), AssetKey("asset_four")], {"out_1"}, None, 2),
        (
            [
                AssetKey("asset_one"),
                AssetKey("asset_two"),
                AssetKey("asset_three"),
                AssetKey("asset_four"),
            ],
            {"out_1", "out_2"},
            {"op_3_1", "op_3_2"},
            4,
        ),
    ],
)
def test_graph_backed_asset_subset_context_intermediate_ops(
    asset_selection, selected_output_names_op_1, selected_output_names_op_3, num_materializations
):
    @op(out={"out_1": Out(is_required=False), "out_2": Out(is_required=False)})
    def op_1(context):
        assert context.selected_output_names == selected_output_names_op_1
        if "out_1" in context.selected_output_names:
            yield Output(1, output_name="out_1")
        if "out_2" in context.selected_output_names:
            yield Output(1, output_name="out_2")

    @op
    def op_2(x):
        return x

    @op(out={"op_3_1": Out(is_required=False), "op_3_2": Out(is_required=False)})
    def op_3(context, x):
        assert context.selected_output_names == selected_output_names_op_3
        if "op_3_1" in context.selected_output_names:
            yield Output(x, output_name="op_3_1")
        if "op_3_2" in context.selected_output_names:
            yield Output(x, output_name="op_3_2")

    @graph(
        out={
            "asset_one": GraphOut(),
            "asset_two": GraphOut(),
            "asset_three": GraphOut(),
            "asset_four": GraphOut(),
        }
    )
    def graph_asset():
        out_1, out_2 = op_1()
        asset_one = op_2(op_2(out_1))
        asset_two, asset_three = op_3(op_2(out_2))
        return {
            "asset_one": asset_one,
            "asset_two": asset_two,
            "asset_three": asset_three,
            "asset_four": out_1,
        }

    asset_job = define_asset_job("yay").resolve(
        [AssetsDefinition.from_graph(graph_asset, can_subset=True)],
        [],
    )

    with instance_for_test() as instance:
        result = asset_job.execute_in_process(asset_selection=asset_selection, instance=instance)
        assert result.success
        assert (
            get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION)
            == num_materializations
        )


@pytest.mark.parametrize(
    "asset_selection,selected_output_names_op_1,selected_output_names_op_2,num_materializations",
    [
        ([AssetKey("a")], {"op_1_1"}, None, 1),
        ([AssetKey("b")], {"op_1_2"}, None, 1),
        # The following two test cases will also yield a materialization for b because b
        # is required as an input and directly outputted from the graph. A warning is logged.
        ([AssetKey("c")], {"op_1_2"}, {"op_2_1"}, 2),
        ([AssetKey("c"), AssetKey("d")], {"op_1_2"}, {"op_2_1", "op_2_2"}, 3),
        ([AssetKey("b"), AssetKey("d")], {"op_1_2"}, {"op_2_2"}, 2),
    ],
)
def test_nested_graph_subset_context(
    asset_selection, selected_output_names_op_1, selected_output_names_op_2, num_materializations
):
    @op(out={"op_1_1": Out(is_required=False), "op_1_2": Out(is_required=False)})
    def op_1(context):
        assert context.selected_output_names == selected_output_names_op_1
        if "op_1_1" in context.selected_output_names:
            yield Output(1, output_name="op_1_1")
        if "op_1_2" in context.selected_output_names:
            yield Output(1, output_name="op_1_2")

    @op(out={"op_2_1": Out(is_required=False), "op_2_2": Out(is_required=False)})
    def op_2(context, x):
        assert context.selected_output_names == selected_output_names_op_2
        if "op_2_2" in context.selected_output_names:
            yield Output(x, output_name="op_2_2")
        if "op_2_1" in context.selected_output_names:
            yield Output(x, output_name="op_2_1")

    @graph(out={"a": GraphOut(), "b": GraphOut()})
    def two_outputs_graph():
        a, b = op_1()
        return {"a": a, "b": b}

    @graph(out={"c": GraphOut(), "d": GraphOut()})
    def downstream_graph(b):
        c, d = op_2(b)
        return {"c": c, "d": d}

    @graph(out={"a": GraphOut(), "b": GraphOut(), "c": GraphOut(), "d": GraphOut()})
    def nested_graph():
        a, b = two_outputs_graph()
        c, d = downstream_graph(b)
        return {"a": a, "b": b, "c": c, "d": d}

    asset_job = define_asset_job("yay").resolve(
        [AssetsDefinition.from_graph(nested_graph, can_subset=True)],
        [],
    )

    with instance_for_test() as instance:
        result = asset_job.execute_in_process(asset_selection=asset_selection, instance=instance)
        assert result.success
        assert (
            get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION)
            == num_materializations
        )


def test_graph_backed_asset_reused():
    @asset
    def upstream():
        return 1

    @op
    def foo(upstream):
        return 1

    @graph
    def graph_asset(upstream):
        return foo(upstream)

    @asset
    def one_downstream(asset_one):
        return asset_one

    @asset
    def duplicate_one_downstream(duplicate_one):
        return duplicate_one

    with tempfile.TemporaryDirectory() as tmpdir_path:
        asset_job = define_asset_job("yay").resolve(
            with_resources(
                [
                    upstream,
                    AssetsDefinition.from_graph(
                        graph_asset,
                        keys_by_output_name={
                            "result": AssetKey("asset_one"),
                        },
                        can_subset=True,
                    ),
                    AssetsDefinition.from_graph(
                        graph_asset,
                        keys_by_output_name={
                            "result": AssetKey("duplicate_one"),
                        },
                        can_subset=True,
                    ),
                    one_downstream,
                    duplicate_one_downstream,
                ],
                resource_defs={"io_manager": fs_io_manager.configured({"base_dir": tmpdir_path})},
            ),
            [],
        )

        with instance_for_test() as instance:
            asset_job.execute_in_process(instance=instance, asset_selection=[AssetKey("upstream")])
            result = asset_job.execute_in_process(
                instance=instance,
                asset_selection=[AssetKey("asset_one"), AssetKey("one_downstream")],
            )
            assert result.success
            assert (
                get_num_events(
                    instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION_PLANNED
                )
                == 2
            )
            assert (
                get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION) == 2
            )
            step_keys = get_step_keys_from_run(instance)
            assert set(step_keys) == set(["graph_asset.foo", "one_downstream"])

            # Other graph-backed asset
            result = asset_job.execute_in_process(
                instance=instance,
                asset_selection=[AssetKey("duplicate_one"), AssetKey("duplicate_one_downstream")],
            )
            assert result.success
            assert (
                get_num_events(
                    instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION_PLANNED
                )
                == 2
            )
            assert (
                get_num_events(instance, result.run_id, DagsterEventType.ASSET_MATERIALIZATION) == 2
            )
            step_keys = get_step_keys_from_run(instance)
            assert set(step_keys) == set(["graph_asset.foo", "duplicate_one_downstream"])


def test_self_dependency():
    from dagster import PartitionKeyRange, TimeWindowPartitionMapping

    @asset(
        partitions_def=DailyPartitionsDefinition(start_date="2020-01-01"),
        ins={
            "a": AssetIn(
                partition_mapping=TimeWindowPartitionMapping(start_offset=-1, end_offset=-1)
            )
        },
    )
    def a(a):
        del a

    class MyIOManager(IOManager):
        def handle_output(self, context, obj):
            ...

        def load_input(self, context):
            assert context.asset_key.path[-1] == "a"
            if context.partition_key == "2020-01-01":
                assert context.asset_partition_keys == []
                assert context.has_asset_partitions
            else:
                assert context.partition_key == "2020-01-02"
                assert context.asset_partition_keys == ["2020-01-01"]
                assert context.asset_partition_key == "2020-01-01"
                assert context.asset_partition_key_range == PartitionKeyRange(
                    "2020-01-01", "2020-01-01"
                )
                assert context.has_asset_partitions

    resources = {"io_manager": MyIOManager()}
    materialize([a], partition_key="2020-01-01", resources=resources)
    materialize([a], partition_key="2020-01-02", resources=resources)


def test_context_assets_def():
    @asset
    def a(context):
        assert context.assets_def == a
        return 1

    @asset
    def b(context, a):
        assert context.assets_def == b
        return 2

    asset_job = define_asset_job("yay", [a, b]).resolve(
        [a, b],
        [],
    )

    asset_job.execute_in_process()


def test_invalid_context_assets_def():
    @op
    def my_op(context):
        context.assets_def

    @job
    def my_job():
        my_op()

    with pytest.raises(DagsterInvalidPropertyError, match="does not have an assets definition"):
        my_job.execute_in_process()


def test_asset_takes_bare_resource():
    class BareObjectResource:
        pass

    executed = {}

    @asset(resource_defs={"bare_resource": BareObjectResource()})
    def blah(context):
        assert context.resources.bare_resource
        executed["yes"] = True

    defs = Definitions(assets=[blah])
    defs.get_implicit_global_asset_job_def().execute_in_process()
    assert executed["yes"]
