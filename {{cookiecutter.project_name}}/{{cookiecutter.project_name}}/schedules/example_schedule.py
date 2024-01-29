from dagster import schedule

from ..jobs.example_job import my_job


@schedule(cron_schedule="* * * * *", job=my_job, execution_timezone="US/Central")
def my_schedule(_context):
    return {}
