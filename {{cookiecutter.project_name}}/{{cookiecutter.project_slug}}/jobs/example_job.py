from dagster import FilesystemIOManager, graph, op
from dagster_docker import docker_executor


@op
def hello():
    return 1


@op
def goodbye(foo):
    if foo != 1:
        raise Exception("Bad io manager")
    return foo * 2


@graph
def my_graph():
    goodbye(hello())


my_job = my_graph.to_job(name="my_job")

my_step_isolated_job = my_graph.to_job(
    name="my_step_isolated_job",
    executor_def=docker_executor,
    resource_defs={
        "io_manager": FilesystemIOManager(base_dir="/tmp/io_manager_storage")
    },
)
