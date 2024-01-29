# Dagster libraries to run both dagster-webserver and the dagster-daemon. Does not
# need to have access to any pipeline code.

FROM python:3.11-slim as base

WORKDIR /opt/dagster

# Copy the requirements file and install Python dependencies
COPY ./requirements/dagster.txt /opt/dagster/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Set $DAGSTER_HOME and copy dagster instance and workspace YAML there
ENV DAGSTER_HOME=/opt/dagster/dagster_home/
WORKDIR $DAGSTER_HOME

RUN mkdir -p $DAGSTER_HOME
COPY dagster.yaml $DAGSTER_HOME


# Production stage copies the production workspace file
FROM base as production
ENV DAGSTER_HOME=/opt/dagster/dagster_home/
WORKDIR $DAGSTER_HOME
COPY workspace.yaml $DAGSTER_HOME

# Local stage copies the local workspace file
FROM base as local
ENV DAGSTER_HOME=/opt/dagster/dagster_home/
WORKDIR $DAGSTER_HOME
COPY workspace.local.yaml $DAGSTER_HOME/workspace.yaml
