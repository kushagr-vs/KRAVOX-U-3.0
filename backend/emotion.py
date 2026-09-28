"""Heuristic expression estimation. Never infer a diagnosis or a person's feelings."""
import base64
import os
import numpy as np
from .config import ROOT

os.environ.setdefault('DEEPFACE_HOME', str(ROOT / 'models'))
# DeepFace's emoji logger can fail on Windows cp1252 consoles.
os.environ.setdefault('DEEPFACE_LOG_LEVEL', '50')

def voice_expression(pcm):
    import librosa
    audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
    # Use at most four seconds to bound latency; these are acoustic hints only.
    audio = audio[-64000:]
    if len(audio) < 2048: return 'neutral', 'Too little audio for voice expression estimation.'
    energy = float(np.sqrt(np.mean(audio ** 2)))
    if energy < .008: return 'calm', 'Voice expression estimation: low energy. This is an uncertain acoustic observation.'
    pitch = librosa.yin(audio, fmin=65, fmax=400, sr=16000)
    median = float(np.nanmedian(pitch))
    variation = float(np.nanstd(pitch))
    tone = 'excited' if energy > .07 and variation > 35 else 'neutral'
    return tone, f'Voice expression estimation: {tone} acoustic pattern, RMS energy {energy:.3f}, estimated pitch {median:.0f} Hz. Pitch and energy cannot establish how you feel.'

def face_expression(image):
    import cv2
    try:
        from deepface import DeepFace
    except ImportError:
        raise RuntimeError('Face expression estimation needs the optional vision dependencies. Install backend/requirements-vision.txt.')
    raw = base64.b64decode(image, validate=True)
    if len(raw) > 400_000: raise ValueError('Camera frame too large')
    frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[0] > 1080 or frame.shape[1] > 1920: raise ValueError('Invalid camera frame')
    # Face detection is enforced: a blank frame must never become an emotion result.
    result = DeepFace.analyze(frame, actions=['emotion'], enforce_detection=True, silent=True)
    if isinstance(result, list): result = result[0]
    expression = result.get('dominant_emotion', 'neutral')
    return expression, f'Facial expression estimation: {expression}-like visual pattern. This estimate is uncertain and does not establish your feelings or a diagnosis.'
