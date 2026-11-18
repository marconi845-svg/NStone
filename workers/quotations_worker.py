from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_quotations_api

class QuotationWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class QuotationWorker(QRunnable):
    def __init__(self, url, headers, params, callback):
        super().__init__()
        self.url = url
        self.headers = headers
        self.params = params
        self.signals = QuotationWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_quotations_api(self.url, self.headers, self.params)
        self.signals.finished.emit(result)










