"""Shared helpers for the MLA-Reject tests.

`need(module, name)` fetches a public name and fails the test (not errors it) with
"missing feature: ..." while the name is not written yet, so every test reports on its own.
"""
import importlib

import pytest


def need(module: str, name: str):
    mod = importlib.import_module(module)
    value = getattr(mod, name, None)
    if value is None:
        pytest.fail(f"missing feature: {module}.{name}", pytrace=False)
    return value
