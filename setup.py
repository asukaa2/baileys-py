"""Fallback setup.py for uv / pip versions that need it.

The canonical project metadata lives in ``pyproject.toml``. This file
only exists so that older pip / uv versions can still recognise this as
a Python project. It intentionally calls ``setup()`` with no arguments
so setuptools reads everything from ``pyproject.toml``.
"""
from setuptools import setup

setup()
