"""
This is the module where assets are defined.

Start here.
"""

from dagster import asset

@asset
def hello():
    return "hello world"