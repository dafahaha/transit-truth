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


def normalize(src: str) -> None:
    tmp = src + ".normalized"
    with tarfile.open(src, "r:*") as tin:
        # gzip layer written explicitly: mtime=0, no FNAME (tarfile's "w:gz"
        # stamps the wall-clock mtime + source filename into the gzip header).
        with open(tmp, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as tout:
                    for m in tin.getmembers():
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


if __name__ == "__main__":
    normalize(sys.argv[1])
    print("normalized:", sys.argv[1])
