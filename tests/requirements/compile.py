#!/usr/bin/env python
"""
Based on Adam Johnson's script:
https://github.com/adamchainz/django-cors-headers/blob/main/tests/requirements/compile.py
"""

import os
import subprocess
import sys
from functools import partial
from pathlib import Path

if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    common_args = [
        "uv",
        "pip",
        "compile",
        "--quiet",
        "--generate-hashes",
        "--constraint",
        "-",
        "requirements.in",
        *sys.argv[1:],
    ]
    django_python_versions = {
        "Django>=4.2,<5.0": ["3.10", "3.11", "3.12"],
        "Django>=5.0,<5.1": ["3.10", "3.11", "3.12"],
        "Django>=5.1,<5.2": ["3.10", "3.11", "3.12", "3.13"],
        "Django>=5.2,<6.0": ["3.10", "3.11", "3.12", "3.13", "3.14"],
        "Django>=6.0,<6.1": ["3.12", "3.13", "3.14"],
    }
    run = partial(subprocess.run, check=True)
    for django_version, python_versions in django_python_versions.items():
        for python_version in python_versions:
            django_nodot = (
                django_version.split("=", 1)[1].split(",", 1)[0].replace(".", "")
            )
            python_nodot = python_version.replace(".", "")
            run(
                [
                    *common_args,
                    "--python",
                    python_version,
                    "--output-file",
                    f"py{python_nodot}-django{django_nodot}.txt",
                ],
                input=django_version.encode("utf-8"),
            )
