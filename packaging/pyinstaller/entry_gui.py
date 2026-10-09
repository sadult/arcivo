"""PyInstaller entry point for ArcivoDashboard.exe (windowed desktop app)."""

import sys

from arcivo.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
