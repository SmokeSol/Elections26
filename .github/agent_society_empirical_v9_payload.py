#!/usr/bin/env python3
from __future__ import annotations
import base64, hashlib, io, pathlib, shutil, zipfile

PAYLOAD_SHA256 = "3cdda05d95ef387c85ef8919fe3ea188226f21c0ccc9d5ef9eb7bf35c7d32df0"
CHUNKS = pathlib.Path(".github/agent_society_empirical_v9_payload_chunks")
SELF = pathlib.Path(".github/agent_society_empirical_v9_payload.py")
APPLY_WORKFLOW = pathlib.Path(".github/workflows/apply-agent-society-empirical-v9.yml")
PART_NAMES = [
    "payload_00a.part", "payload_00b.part",
    "payload_01.part", "payload_02.part", "payload_03.part", "payload_04.part",
    "payload_05.part", "payload_06.part", "payload_07.part", "payload_08.part",
]


def main() -> None:
    root = pathlib.Path(".").resolve()
    parts = [CHUNKS / name for name in PART_NAMES]
    missing = [str(path) for path in parts if not path.is_file()]
    if missing:
        raise SystemExit(f"missing payload chunks: {missing}")
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in parts)
    raw = base64.b64decode(encoded, validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PAYLOAD_SHA256:
        raise SystemExit(f"payload sha256 mismatch: {digest}")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        for name in names:
            path = pathlib.PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit(f"unsafe payload member: {name}")
        archive.extractall(root)
    shutil.rmtree(CHUNKS)
    for setup in (SELF, APPLY_WORKFLOW):
        try:
            setup.unlink()
        except FileNotFoundError:
            pass
    print(f"PASS_EMPIRICAL_MIND_V9_PAYLOAD_APPLIED files={len(names)} sha256={PAYLOAD_SHA256}")


if __name__ == "__main__":
    main()
