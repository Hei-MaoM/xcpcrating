"""Module entry point: forwards ``python -m xcpc_rating`` to the CLI."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
