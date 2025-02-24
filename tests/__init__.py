import logging
from pathlib import Path

# Disable most logging for unit tests.
logging.disable(logging.CRITICAL)

# Set globals.
REPODIR = Path(__file__).parents[1]
TESTSDIR = REPODIR / 'tests'
TESTDATADIR = TESTSDIR / 'data'