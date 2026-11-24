"""Einstiegspunkt für `python -m djsync` (CLI, Linux/WSL).

Die Windows-App startet über packaging/djsync_gui.py.
"""

import sys

from djsync.cli import main

sys.exit(main())
