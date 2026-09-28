import numpy as np
from backend.emotion import voice_expression

def test_voice_estimation_is_acoustic():
    quiet = np.zeros(16000, dtype='<i2').tobytes()
    tone, description = voice_expression(quiet)
    assert tone == 'calm' and 'uncertain' in description
    wave = (.12 * np.sin(2*np.pi*180*np.arange(16000)/16000)*32767).astype('<i2').tobytes()
    tone, description = voice_expression(wave)
    assert tone in ('neutral','excited')
    assert 'cannot establish how you feel' in description
