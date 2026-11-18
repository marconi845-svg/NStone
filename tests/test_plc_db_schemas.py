"""Test schemi DB diagnostica."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.common.plc_db_schemas import format_field, get_schema


def test_multifilo_db1_stato_label():
    row = get_schema("multifilo")["db1"][0]
    assert format_field(row, {"stato": 1}) == "Run"


def test_missing_data():
    row = get_schema("lucidatrice")["db2"][0]
    assert format_field(row, None) == "—"
