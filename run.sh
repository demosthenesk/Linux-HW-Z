#!/bin/sh
# Run Linux HW-Z from the source tree (needs python3 + PySide6).
cd "$(dirname "$0")" && exec python3 -m hwz "$@"
