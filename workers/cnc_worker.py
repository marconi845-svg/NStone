from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_cnc_generate

class CNCWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class CNCWorker(QRunnable):
    def __init__(self, parameters, callback):
        super().__init__()
        self.parameters = parameters
        self.signals = CNCWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_cnc_generate(self.parameters)
        self.signals.finished.emit(result)










