"""Startskript für die gebündelte Windows-App (PyInstaller, siehe djsync.spec).

PyInstaller braucht ein Skript ohne relative Imports; `djsync/gui/__main__.py` eignet sich
dafür nicht.
"""

import sys

from djsync.gui.app import main

sys.exit(main())
