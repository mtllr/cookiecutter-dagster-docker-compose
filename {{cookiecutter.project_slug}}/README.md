# {{cookiecutter.project_slug}}

This is a [Dagster](https://dagster.io/) project scaffolded with [`dagster project scaffold`](https://docs.dagster.io/getting-started/create-new-project) and augmented with cookiecutter.

## Getting started

First, install your Dagster code location as a container.

```bash
docker-compose build
```

Then, start the Dagster UI web server:

```bash
docker-compose up
```

Open http://localhost:3000 with your browser to see the project.

You can start writing assets in `{{cookiecutter.project_slug}}/assets.py`. The assets are automatically loaded into the Dagster code location as you define them.

## Development


### Adding new Python dependencies

You can specify new Python dependencies in `setup.py`. Then rebuild the image: `docker-compose up`.

### Unit testing

Tests are in the `{{cookiecutter.project_slug}}_tests` directory and you can run tests using `pytest`:

```bash
pytest {{cookiecutter.project_slug}}_tests
```

### Schedules and sensors

If you want to enable Dagster [Schedules](https://docs.dagster.io/concepts/partitions-schedules-sensors/schedules) or [Sensors](https://docs.dagster.io/concepts/partitions-schedules-sensors/sensors) for your jobs, the [Dagster Daemon](https://docs.dagster.io/deployment/dagster-daemon) process must be running. This is done automatically when you run `dagster dev`.

Once your Dagster Daemon is running, you can start turning on schedules and sensors for your jobs.

## Deploy on Dagster Cloud

The easiest way to deploy your Dagster project is to use Dagster Cloud. Check out the [Dagster Cloud Documentation](https://docs.dagster.cloud) to learn more.

### TODO AWS/AZURE/GCP