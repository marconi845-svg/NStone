from PyQt5.QtCore import QRunnable, pyqtSignal, QObject
from plc.rust_bridge import run_gcode_analyze, run_gcode_validate, run_gcode_optimize

class GCodeWorkerSignals(QObject):
    finished = pyqtSignal(dict)

class GCodeAnalyzeWorker(QRunnable):
    def __init__(self, gcode_text, callback):
        super().__init__()
        self.gcode_text = gcode_text
        self.signals = GCodeWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_gcode_analyze(self.gcode_text)
        self.signals.finished.emit(result)

class GCodeValidateWorker(QRunnable):
    def __init__(self, gcode_text, callback):
        super().__init__()
        self.gcode_text = gcode_text
        self.signals = GCodeWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_gcode_validate(self.gcode_text)
        self.signals.finished.emit(result)

class GCodeOptimizeWorker(QRunnable):
    def __init__(self, gcode_text, callback):
        super().__init__()
        self.gcode_text = gcode_text
        self.signals = GCodeWorkerSignals()
        self.signals.finished.connect(callback)

    def run(self):
        result = run_gcode_optimize(self.gcode_text)
        self.signals.finished.emit(result)







