"""Optional custom Kravox ONNX wake model. No pretrained Kravox model is bundled."""
import os
from pathlib import Path
import numpy as np

class WakeDetector:
    def __init__(self): self.model = None; self.buffer = bytearray()
    def predict(self, pcm):
        path = os.getenv('WAKE_MODEL', '')
        if not path or not Path(path).is_file(): raise RuntimeError('Set WAKE_MODEL to a custom Kravox .onnx model in backend/.env.')
        if self.model is None:
            try:
                from openwakeword.model import Model
            except ImportError:
                raise RuntimeError('Install backend/requirements-wake.txt to use the wake word.')
            self.model = Model(wakeword_models=[path], inference_framework='onnx')
        self.buffer.extend(pcm)
        hit = False
        while len(self.buffer) >= 2560:
            frame = np.frombuffer(bytes(self.buffer[:2560]), dtype='<i2')
            del self.buffer[:2560]
            predictions = self.model.predict(frame)
            if any(float(score) >= .6 for score in predictions.values()):
                hit = True; self.model.reset(); self.buffer.clear(); break
        return hit
