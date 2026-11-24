"""Einstiegspunkt für `python -m djsync` und die gebaute djsync.exe."""

import sys

from djsync.cli import main

sys.exit(main())
