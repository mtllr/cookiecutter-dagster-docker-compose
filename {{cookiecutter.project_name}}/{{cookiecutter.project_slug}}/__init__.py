from dagster import Definitions, load_assets_from_modules

from . import assets
from .jobs.example_job import my_job, my_step_isolated_job
from .schedules.example_schedule import my_schedule

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    jobs=[my_job, my_step_isolated_job],
    schedules=[my_schedule],
)
