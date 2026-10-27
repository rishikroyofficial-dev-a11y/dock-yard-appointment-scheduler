"""export.py - write dataclass rows to CSV deterministically.

Same rows in -> byte-identical file out (fixed column order, fixed line
endings, no timestamps), which is what makes checksum comparison possible.
"""
import csv
import hashlib
import os
from dataclasses import fields, asdict


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return 1 if value else 0        # booleans as 1/0 (SQL friendly)
    return value


def write_csv(path, rows, row_type):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = [f.name for f in fields(row_type)]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            d = asdict(r)
            w.writerow([_cell(d[c]) for c in cols])


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


#export: Writer file

"""
writes CSVs with fixed column order and \n line endings. 
It also has sha256_of(), which fingerprints a file, 
so we can compare two runs.

"""