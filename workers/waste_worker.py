from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_waste_compute

class WasteWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class WasteWorker(QRunnable):
    def __init__(self, items, callback):
        super().__init__()
        self.items = items
        self.signals = WasteWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_waste_compute(self.items)
        self.signals.finished.emit(result)










