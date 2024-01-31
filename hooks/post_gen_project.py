"""
Post generation hooks for cookiecutter.

A lot of this code is borrowed from cookiecutter-django 
https://github.com/cookiecutter/cookiecutter-django/blob/master/hooks/post_gen_project.py

"""
import os
import random
import re
import string
import sys

DEBUG_VALUE = "debug"  # This is the default password for the postgres user in dev

try:
    # Inspired by
    # https://github.com/django/django/blob/master/django/utils/crypto.py
    random = random.SystemRandom()
    USING_SYSRANDOM = True
except NotImplementedError:
    USING_SYSRANDOM = False


# MODULE_REGEX = r"^[_a-zA-Z][_a-zA-Z0-9]+$"


def append_to_gitignore_file(ignored_line):
    """Append a line to the .gitignore file."""
    with open(".gitignore", "a", encoding="utf-8") as gitignore_file:
        gitignore_file.write(ignored_line)
        gitignore_file.write("\n")


# Add .env files to .gitignore
append_to_gitignore_file(".env")
append_to_gitignore_file(".envs/*")
if "{{ cookiecutter.keep_local_envs_in_vcs }}".lower() == "y":
    append_to_gitignore_file("!.envs/.local")


def generate_random_user():
    """Generate a random user."""
    return generate_random_string(length=32, using_ascii_letters=True)


def generate_random_string(
    length, using_digits=False, using_ascii_letters=False, using_punctuation=False
):
    """
    Example:
        opting out for 50 symbol-long, [a-z][A-Z][0-9] string
        would yield log_2((26+26+50)^50) ~= 334 bit strength.
    """
    if not USING_SYSRANDOM:
        return None

    symbols = []
    if using_digits:
        symbols += string.digits
    if using_ascii_letters:
        symbols += string.ascii_letters
    if using_punctuation:
        all_punctuation = set(string.punctuation)
        # These symbols can cause issues in environment variables
        unsuitable = {"'", '"', "\\", "$"}
        suitable = all_punctuation.difference(unsuitable)
        symbols += "".join(suitable)

    return "".join([random.choice(symbols) for _ in range(length)])


def set_flag(file_path, flag, *args, value=None, formatted=None, **kwargs):
    """Replace a flag in a file with a value."""
    if value is None:
        random_string = generate_random_string(*args, **kwargs)
        if random_string is None:
            print(
                "We couldn't find a secure pseudo-random number generator on your "
                f"system. Please, make sure to manually {flag} later."
            )
            random_string = flag
        if formatted is not None:
            random_string = formatted.format(random_string)
        value = random_string

    with open(file_path, "r+", encoding="utf-8") as f:
        file_contents = f.read().replace(flag, value)
        f.seek(0)
        f.write(file_contents)
        f.truncate()

    return value


def generate_postgres_user():
    """Generate a random postgres user."""
    return generate_random_user()


def set_postgres_user(file_path, value):
    """Set the postgres user in the .env file."""
    postgres_user = set_flag(file_path, "!!!SET POSTGRES_USER!!!", value=value)
    return postgres_user


def set_postgres_password(file_path, value=None):
    """Set the postgres password in the .env file."""
    postgres_password = set_flag(
        file_path,
        "!!!SET POSTGRES_PASSWORD!!!",
        value=value,
        length=64,
        using_digits=True,
        using_ascii_letters=True,
    )
    return postgres_password


def set_flags_in_envs(postgres_user):
    """Set the postgres user and password in the .env files."""
    local_postgres_envs_path = os.path.join(".envs", ".local")
    production_postgres_envs_path = os.path.join(".envs", ".production")

    # Create local envs
    set_postgres_user(local_postgres_envs_path, value="postgres")
    set_postgres_password(local_postgres_envs_path, value="pgpass")

    # Create production envs
    set_postgres_user(production_postgres_envs_path, value=postgres_user)
    set_postgres_password(production_postgres_envs_path, value=None)


def main():
    """Run the main hooks."""
    set_flags_in_envs(
        generate_random_user(),
    )


if __name__ == "__main__":
    sys.exit(main())
