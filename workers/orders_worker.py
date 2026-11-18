from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_orders_parse, run_orders_validate

class OrdersWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class OrdersParseWorker(QRunnable):
    def __init__(self, raw_text, callback):
        super().__init__()
        self.raw_text = raw_text
        self.signals = OrdersWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_orders_parse(self.raw_text)
        self.signals.finished.emit(result)

class OrdersValidateWorker(QRunnable):
    def __init__(self, order_data, callback):
        super().__init__()
        self.order_data = order_data
        self.signals = OrdersWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_orders_validate(self.order_data)
        self.signals.finished.emit(result)










