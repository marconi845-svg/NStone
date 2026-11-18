"""
Lettura DB Snap7 generica con supporto chunk (DB lunghi).
"""

from __future__ import annotations

from typing import Any, Optional

# PDU Snap7 tipica: letture >240 byte spesso vanno spezzate
DEFAULT_CHUNK_SIZE = 240


def read_db_bytes(
    client: Any, db_number: int, offset: int, size: int
) -> Optional[bytes]:
    if size <= 0:
        return b""
    reader = getattr(client, "_read_bytes", None)
    if not callable(reader):
        return None
    data = reader(db_number, offset, size)
    if data is None:
        return None
    return bytes(data)


def read_db_chunked(
    client: Any,
    db_number: int,
    total_size: int,
    *,
    offset: int = 0,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Optional[bytes]:
    """Legge total_size byte da db_number partendo da offset (letture a chunk)."""
    if total_size <= 0:
        return b""
    parts: list[bytes] = []
    pos = 0
    while pos < total_size:
        chunk_len = min(chunk_size, total_size - pos)
        block = read_db_bytes(client, db_number, offset + pos, chunk_len)
        if block is None:
            return None
        parts.append(block)
        pos += chunk_len
    return b"".join(parts)
