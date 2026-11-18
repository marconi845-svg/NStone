from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_production_simulate

class ProductionWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class ProductionWorker(QRunnable):
    def __init__(self, steps, intensity, callback):
        super().__init__()
        self.steps = steps
        self.intensity = intensity
        self.signals = ProductionWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_production_simulate(self.steps, self.intensity)
        self.signals.finished.emit(result)










