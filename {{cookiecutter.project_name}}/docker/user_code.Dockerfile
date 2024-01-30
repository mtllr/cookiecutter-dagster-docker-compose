FROM python:3.11-slim

WORKDIR /opt/dagster

# Copy the requirements file and install Python dependencies
COPY ./requirements/user_code.txt /opt/dagster/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the repository code
COPY ./{{cookiecutter.project_slug}} /opt/dagster/app

# Run dagster gRPC server on port 4000
EXPOSE 4000

# CMD allows this to be overridden from run launchers or executors that want
# to run other commands against your repository
CMD ["dagster", "api", "grpc", "-h", "0.0.0.0", "-p", "4000", "-m", "app"]


