# cookiecutter-dagster-docker-compose

Cookiecutter to make a new docker compose deployable dagster project.

Compatible with Visual Studio code devcontainer.

## Getting started

```bash
cookiecutter gh:mtllr/cookiecutter-dagster-docker-compose
```

fill in the project_name.

Choose the libraries that you need to work on you dagster project by changing the requirements.txt files in the user code project and the dagster project.


```bash
docker compose up
```

open http://localhost:3000

For other steps to follow during development follow the README.md that is in the cookiecutter.

## Devcontainer

Use attach to running container and select the container running you user code.

Enjoy development!