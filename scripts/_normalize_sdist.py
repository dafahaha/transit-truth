"""Rewrite a setuptools sdist tar.gz so it is byte-reproducible.

setuptools on this platform stamps every tar member with the *actual build*
time (and the gzip header with it), ignoring SOURCE_DATE_EPOCH for the sdist
archive itself. We normalize: every member mtime -> SOURCE_DATE_EPOCH,
uid/gid/uname/gname zeroed, gzip header mtime -> 0. Content is untouched.

Usage: python _normalize_sdist.py <path-to.tar.gz>
"""
import gzip
import os
import sys
import tarfile

EPOCH = int(os.environ["SOURCE_DATE_EPOCH"])

# setuptools regenerates backend/transit_truth.egg-info/ *during* the build,
# so pre-deleting it (build_release.ps1) cannot keep it out of the sdist.
# It is a pure build byproduct (file manifest + empty dir), pip regenerates it
# on install from sdist anyway, so drop these members here.
SKIP_PATHS = ("transit_truth.egg-info",)


def _skipped(name: str) -> bool:
    return any(p in name for p in SKIP_PATHS)


def normalize(src: str) -> None:
    tmp = src + ".normalized"
    dropped = []
    with tarfile.open(src, "r:*") as tin:
        # gzip layer written explicitly: mtime=0, no FNAME (tarfile's "w:gz"
        # stamps the wall-clock mtime + source filename into the gzip header).
        with open(tmp, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as tout:
                    for m in tin.getmembers():
                        if _skipped(m.name):
                            dropped.append(m.name)
                            continue
                        m.mtime = EPOCH
                        # setuptools wrote PAX extended headers carrying the
                        # *original* fractional mtime; they override the numeric
                        # ustar field on write, so strip them entirely.
                        m.pax_headers = {}
                        m.uid = 0
                        m.gid = 0
                        m.uname = ""
                        m.gname = ""
                        f = tin.extractfile(m) if m.isfile() else None
                        tout.addfile(m, f)
    os.replace(tmp, src)
    if dropped:
        print("dropped from sdist:", len(dropped), "members")
        for n in dropped:
            print("  -", n)


if __name__ == "__main__":
    normalize(sys.argv[1])
    print("normalized:", sys.argv[1])
