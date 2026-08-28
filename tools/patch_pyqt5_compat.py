#!/usr/bin/env python3
"""
Patches a leftover PyQt4->PyQt5 conversion bug found in InstsAndQt and
hsganalysis: several widget classes (QLineEdit, QLabel, QDialog, etc.) moved
from QtGui to QtWidgets in Qt5, but some modules still reference them as
QtGui.<Name>, which raises AttributeError at import time on any platform
with a modern PyQt5.

Idempotent: safe to run repeatedly or against a freshly re-cloned checkout.

Usage: patch_pyqt5_compat.py <repo_dir> [<repo_dir> ...]
"""
import glob
import re
import sys

from PyQt5 import QtGui, QtWidgets

WIDGETS_NAMES = set(dir(QtWidgets))
GUI_NAMES = set(dir(QtGui))


# Only match a bare `QtGui.X`, never `pg.QtGui.X` -- pyqtgraph's own Qt
# compat shim intentionally re-exports QtWidgets classes under its QtGui
# namespace, and pyqtgraph has no top-level `QtWidgets` to rewrite it to.
BARE_QTGUI_RE = r"(?<![\.\w])QtGui\.(\w+)"


def find_bad_refs(src):
    names = set(re.findall(BARE_QTGUI_RE, src))
    return sorted(n for n in names if n in WIDGETS_NAMES and n not in GUI_NAMES)


def patch_file(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        src = f.read()

    bad = find_bad_refs(src)
    if not bad:
        return None

    orig = src
    for name in bad:
        src = re.sub(rf"(?<![\.\w])QtGui\.{name}\b", f"QtWidgets.{name}", src)

    if "QtWidgets" not in re.findall(r"^from PyQt5 import ([\w, ]+)", src, re.M) and \
            not re.search(r"^from PyQt5 import QtWidgets\b", src, re.M) and \
            not re.search(r"^import PyQt5\.QtWidgets\b", src, re.M):
        m = re.search(r"^from PyQt5 import ([\w, ]+)$", src, re.M)
        if m and "QtWidgets" not in [n.strip() for n in m.group(1).split(",")]:
            src = src[:m.start()] + m.group(0) + ", QtWidgets" + src[m.end():]

    if src == orig:
        return None

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return bad


def main(repo_dirs):
    total = 0
    for repo in repo_dirs:
        for path in glob.glob(f"{repo}/**/*.py", recursive=True):
            bad = patch_file(path)
            if bad:
                total += 1
                print(f"patched {path}: {bad}")
    print(f"Done. {total} file(s) patched.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1:])
