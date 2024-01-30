# {{cookiecutter.project_name}}

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

You can start writing assets in `{{cookiecutter.project_name}}/assets.py`. The assets are automatically loaded into the Dagster code location as you define them.

## Development

In development mode, dagster is run using the `code-server` entrypoint such that code changes can applied using the `dagster-webserver` UI 'reload' code location feature. 

To run in development, specify the `docker-compose.local.yml` docker compose file with:

```bash
docker compose -f docker-compose.local.yml up
```

open http://localhost:3000

Alternatively you can use the devecontainer by opening in vscode and and using the `rebuild and open in container` action.

### Requirements
Requirements and dependencies are handled by [Poetry](https://python-poetry.org/). In addition, the docker file uses a multi build stage and buildx for caching to improve build speed.

By using the local/dev compose file, poetry will be built into the container so adding dependancies are as simple as `poetry add <new-awesome-package>`. Because the root project is mounted in local/dev mode poetry will modify the `poetry.lock` in your project root outside the folder, so that the production stage will read that directly. 

You could also modify the project `project.toml` dependancies directly.


### Unit testing

Tests are in the `{{cookiecutter.project_name}}_tests` directory and you can run tests using `pytest`:

```bash
pytest {{cookiecutter.project_name}}_tests
```


## Production
In production we usually don't need to hot-reload the code, and prefer to build the code into the "user code" contianer rather than mount it; improving reproducibility and portability. Production mode also calls the `gRPC api` rather than the `code-server`. To run in develpment mode simply run:

```bash
docker compose up
```
which will use the `docker-compose.yml` file by default and will build the user code docker file to the `production` build stage


## Schedules and sensors

If you want to enable Dagster [Schedules](https://docs.dagster.io/concepts/partitions-schedules-sensors/schedules) or [Sensors](https://docs.dagster.io/concepts/partitions-schedules-sensors/sensors) for your jobs, the [Dagster Daemon](https://docs.dagster.io/deployment/dagster-daemon) process must be running. This is done automatically when you run `dagster dev`.

Once your Dagster Daemon is running, you can start turning on schedules and sensors for your jobs.

## Deploy on Dagster Cloud

The easiest way to deploy your Dagster project is to use Dagster Cloud. Check out the [Dagster Cloud Documentation](https://docs.dagster.cloud) to learn more.

### TODO AWS/AZURE/GCP