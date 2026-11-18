from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_dashboard_stats

class DashboardWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class DashboardWorker(QRunnable):
    def __init__(self, dataset, callback):
        super().__init__()
        self.dataset = dataset
        self.signals = DashboardWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_dashboard_stats(self.dataset)
        self.signals.finished.emit(result)










