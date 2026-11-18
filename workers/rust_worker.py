from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_heavy_task

class RustWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class RustWorker(QRunnable):
    def __init__(self, task_type, payload, callback):
        super().__init__()
        self.task_type = task_type
        self.payload = payload
        self.signals = RustWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_heavy_task(self.task_type, self.payload)
        self.signals.finished.emit(result)










