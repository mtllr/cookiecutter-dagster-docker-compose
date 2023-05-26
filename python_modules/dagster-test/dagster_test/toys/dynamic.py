from dagster import DynamicOut, Field, graph, op
from dagster._core.definitions.events import DynamicOutput


@op
def multiply_by_two(context, y):
    context.log.info("echo_again is returning " + str(y * 2))
    return y * 2


@op(config_schema={"fail_on_first_try": Field(bool, default_value=False)})
def multiply_inputs(context, y, ten):
    if context.op_config["fail_on_first_try"]:
        current_run = context.instance.get_run_by_id(context.run_id)
        if y == 2 and current_run.parent_run_id is None:
            raise Exception()
    context.log.info("echo is returning " + str(y * ten))
    return y * ten


@op
def emit_ten():
    return 10


@op
def sum_numbers(base, nums):
    return base + sum(nums)


@op(out=DynamicOut())
def emit():
    for i in range(3):
        yield DynamicOutput(value=i, mapping_key=str(i))


@graph
def dynamic():
    result = emit().map(lambda num: multiply_by_two(multiply_inputs(num, emit_ten())))
    multiply_by_two.alias("double_total")(sum_numbers(emit_ten(), result.collect()))


dynamic_job = dynamic.to_job()
