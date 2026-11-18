import re
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "ui/windows/machines/gestione_fanghi_window.py"
t = p.read_text(encoding="utf-8")
for name in ("group", "valori_box", "risultati_box"):
    t = re.sub(rf"\n        {name}\.setStyleSheet\(\"\"\"[\s\S]*?\"\"\"\)", "", t)
t = t.replace(
    'info_text.setStyleSheet("color: #CCCCCC; font-size: 12px;")',
    'info_text.setStyleSheet(production_label_stylesheet(variant="secondary") + " font-size: 12px;")',
)
p.write_text(t, encoding="utf-8")
print("fanghi groups cleaned")
