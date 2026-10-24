"""Strip legacy platform modules from the built wheel.

setuptools cannot exclude individual modules of a shipped package
(`app/main.py` is a plain module of the `app` package, not a package itself),
so `packages.find` exclude only removed the `app.api` package. The legacy
online platform (FastAPI app.main + its routers) is self-hosted separately
from the source checkout and must NOT ship in the PyPI wheel.

Idempotent: missing entries are a no-op. Deterministic: the rewritten zip keeps
member order and original metadata bytes; only the stripped entries vanish.

Usage: python _strip_wheel_legacy.py <path-to.whl>
"""
import sys
import zipfile

STRIP = {"app/main.py"}


def strip(path: str) -> None:
    with zipfile.ZipFile(path, "r") as zin:
        members = zin.namelist()
        kept = [m for m in members if m not in STRIP]
        removed = [m for m in members if m in STRIP]
        data = {m: zin.read(m) for m in kept}
        infos = {m: zin.getinfo(m) for m in kept}

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for m in kept:
            zout.writestr(infos[m], data[m])
    print("stripped from wheel:", sorted(removed) or "(none present)")


if __name__ == "__main__":
    strip(sys.argv[1])
