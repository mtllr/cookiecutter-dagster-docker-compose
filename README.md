# cookiecutter-dagster-docker-compose

Cookiecutter to make a new docker compose deployable dagster project.

Compatible with Visual Studio code devcontainer.

## Getting started

```bash
cookiecutter gh:mtllr/cookiecutter-dagster-docker-compose
```

fill in the project_name.

Choose the libraries that you need to work on you dagster project by changing the requirements.txt files in the user code project and the dagster project.

### Devlopment mode

There is a development and production docker-compose cofiguration.

In development mode, dagster is run using the `code-server` entrypoint such that code changes can applied using the `dagster-webserver` UI 'reload' code location feature. 

To run in development, specify the `docker-compose.local.yml` docker compose file with:

```bash
docker compose -f docker-compose.local.yml up
```

open http://localhost:3000

Alternatively you can use the devecontainer by opening in vscode and and using the `rebuild and open in container` action.

#### Requirements
Modify the `./requirements/use_code.txt` to add requirments to the user code container. Then rebuild with 

```bash
docker compose -f docker-compose.local.yml up --build
```

to add the requirements to the user code container.

### Production mode
In production we usually don't need to hot-reload the code, and prefer to build the code into the "user code" contianer rather than mount it; improving reproducibility and portability. Production mode also calls the `gRPC api` rather than the `code-server`. To run in develpment mode simply run:

```bash
docker compose up
```

open http://localhost:3000

For other steps to follow during development follow the README.md that is in the cookiecutter.

## Devcontainer

Use attach to running container and select the container running you user code.

Enjoy development!