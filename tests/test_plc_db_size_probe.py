import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plc.plc_db_size_probe import resolve_db_read_size
from plc.plc_map_loader import MAP_PROFILE_PLANT, suggested_read_size


class _FakePlc:
    def __init__(self, block_size: int = 512):
        self._size = block_size

    @property
    def client(self):
        return self


def test_resolve_prefers_manual():
    size, src = resolve_db_read_size(None, 1, user_size=1024)
    assert size == 1024
    assert src == "manual"


def test_resolve_uses_map_without_plc():
    map_sz = suggested_read_size(MAP_PROFILE_PLANT, "multifilo", 1)
    size, src = resolve_db_read_size(None, 1, map_size=map_sz, auto_detect=False)
    assert size == map_sz
    assert src == "map"
