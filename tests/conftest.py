"""Pytest module-wide configuration file."""

import pytest
import os


@pytest.fixture(autouse=True)
def run_around_tests():
    # Code that will run before your test
    # Find and save current (test) working directory
    cwd = os.getcwd()
    # A test function will be run at this point
    yield
    # Code that will run after the test
    # revert changes to working directory
    os.chdir(cwd)
