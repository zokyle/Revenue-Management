"""pytest configuration for the gleda tool tests.

Run with:  cd electrical/tools && /usr/bin/python3 -m pytest -q
(the system Python is required because it provides ``pcbnew``).
"""
import os
import sys

import pytest

TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
for p in (TOOLS_DIR, TESTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False,
                     help="also run the tests marked slow (the full demo build: "
                          "several minutes of routing)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long running end-to-end tests "
                                       "(run with --runslow or GLEDA_RUN_SLOW=1)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow") or os.environ.get("GLEDA_RUN_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="slow test: run with --runslow (or GLEDA_RUN_SLOW=1)")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


@pytest.fixture()
def mini():
    """A fresh copy of the small reference design."""
    from mini_design import mini_design
    return mini_design()


@pytest.fixture(scope="session")
def built_mini(tmp_path_factory):
    """The mini design built once per test session: (design, BoardFiles)."""
    from mini_design import mini_design
    from gleda import board
    design = mini_design()
    out = tmp_path_factory.mktemp("mini_board")
    files = board.build_board(design, str(out))
    return design, files


@pytest.fixture(scope="session")
def mini_drc(built_mini):
    """DRC result of the unrouted mini board (zones filled and saved)."""
    from gleda import drc
    design, files = built_mini
    return drc.run_drc(files.pcb, json_path=os.path.join(files.directory, "drc.json"))
