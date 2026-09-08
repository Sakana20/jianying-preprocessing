#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from jypre.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
