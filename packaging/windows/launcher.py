"""PyInstaller giriş noktası (paket içinde `python -m zerqon.desktop` karşılığı)."""

import sys

from zerqon.desktop import main

if __name__ == "__main__":
    sys.exit(main())
