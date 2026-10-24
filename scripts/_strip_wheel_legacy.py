"""Strip the legacy online platform from the built PyPI wheel (post-build step).

setuptools ships the complete, importable source tree (sdist / `pip install .`
must keep app.main + app.api for self-hosting the legacy platform). Only the
PyPI wheel is trimmed here: remove `app/main.py` and the whole `app/api/`
package, then rewrite `<dist>-info/RECORD` so it lists exactly the remaining
files (RECORD is pip's install manifest -- stale entries break installs).

Deterministic: member order and all untouched member bytes are preserved; the
rewritten zip stays byte-identical across runs (SOURCE_DATE_EPOCH already
fixed zip entry timestamps).

Usage: python _strip_wheel_legacy.py <path-to.whl>
"""
import csv
import io
import sys
import zipfile

# Exact files/dirs to remove from the wheel.
STRIP_EXACT = {"app/main.py"}
STRIP_PREFIX = "app/api/"


def _is_stripped(name: str) -> bool:
    return name in STRIP_EXACT or name.startswith(STRIP_PREFIX)


def strip(path: str) -> None:
    with zipfile.ZipFile(path, "r") as zin:
        members = zin.namelist()
        record_name = next(n for n in members if n.endswith(".dist-info/RECORD"))
        stripped = [n for n in members if _is_stripped(n)]

        kept = [n for n in members if n not in stripped and n != record_name]
        data = {n: zin.read(n) for n in kept}
        infos = {n: zin.getinfo(n) for n in kept}

        # Rewrite RECORD: keep only non-stripped entries (RECORD's own line
        # stays as the trailing ",," self-entry).
        with io.StringIO() as buf:
            rows = list(csv.reader(io.StringIO(zin.read(record_name).decode())))
            w = csv.writer(buf, lineterminator="\n")
            for row in rows:
                if not row:
                    continue
                if row[0] == record_name or not _is_stripped(row[0]):
                    w.writerow(row)
            new_record = buf.getvalue()

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for n in kept:
            zout.writestr(infos[n], data[n])
        info = zipfile.ZipInfo(record_name)
        zout.writestr(info, new_record)

    print("stripped from wheel:", len(stripped), "entries")
    for n in sorted(stripped):
        print("  -", n)


if __name__ == "__main__":
    strip(sys.argv[1])
