"""PyInstaller entry point for Arcivo.exe (console).

No arguments  → interactive console home screen (sign in, dashboard, connection check, proxy, …)
With arguments → the full ``arcivo`` command line (e.g. ``Arcivo.exe sync``, ``Arcivo.exe search type:pdf``).
"""

import sys

from arcivo.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
