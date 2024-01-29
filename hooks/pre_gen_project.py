"""Pre-generate hook."""

PROJECT_SLUG = "{{ cookiecutter.project_slug }}"
if hasattr(PROJECT_SLUG, "isidentifier"):
    assert (
        PROJECT_SLUG.isidentifier()
    ), f"'{PROJECT_SLUG}' project slug is not a valid Python identifier."
