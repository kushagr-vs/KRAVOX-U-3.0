from backend.speech import clean_text, split_sentences, reply_tone

def test_sentence_streaming_and_hindi():
    sentences, rest = split_sentences('Hello there. नमस्ते। Still speak')
    assert sentences == ['Hello there.', 'नमस्ते।']
    assert rest == 'Still speak'
    assert split_sentences(rest, True) == (['Still speak'], '')

def test_tts_cleaning_and_tone():
    assert clean_text('**Hi** [friend](https://x.test) 😊') == 'Hi friend'
    assert reply_tone('Great!', 'sad') == 'calm'
    assert reply_tone('Great!') == 'excited'

def test_recognition_language_and_final_decoding():
    from types import SimpleNamespace
    from backend.speech import SpeechRecognizer
    import numpy as np
    calls = []
    class Model:
        def transcribe(self, audio, **options):
            calls.append(options)
            return iter([SimpleNamespace(text='Open YouTube')]), SimpleNamespace(language='en')
    recognizer = SpeechRecognizer()
    recognizer.model = Model()
    pcm = np.zeros(16000, dtype='<i2').tobytes()
    assert recognizer.transcribe(pcm, language='en')[0] == 'Open YouTube'
    assert calls[-1]['language'] is None
    assert calls[-1]['beam_size'] == 5
    assert calls[-1]['task'] == 'transcribe'
    recognizer.transcribe(pcm, partial=True, language='auto')
    assert calls[-1]['language'] is None
    assert calls[-1]['beam_size'] == 5
    assert len(calls) == 1
