from __future__ import annotations

import re
from pathlib import Path

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def read_work_ids(
    path: Path
) -> list[str]:
    """
    Read work IDs from a text file with one ID per line; blank lines and ``#`` comments are ignored.

    Args:
        path (Path): The file to read.

    Returns:
        list[str]: The work IDs in the order of the file, without duplicates.

    Raises:
        ValueError: If a line does not contain a valid UUID.
    """
    work_ids: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        work_id = line.split("#", 1)[0].strip()
        if not work_id:
            continue
        if not _UUID.match(work_id):
            raise ValueError(f"{path}:{number}: not a work UUID: {work_id!r}")
        if work_id not in work_ids:
            work_ids.append(work_id)
    return work_ids
