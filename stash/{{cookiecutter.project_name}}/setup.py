from setuptools import find_packages, setup

setup(
    name="{{cookiecutter.project_name}}",
    packages=find_packages(exclude=["{{cookiecutter.project_name}}_tests"]),
    install_requires=[
        "dagster",
        "dagster-cloud"
    ],
    extras_require={"dev": ["dagit", "pytest"]},
)
