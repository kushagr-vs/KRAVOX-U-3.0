"""Compatibility import for the new asynchronous backend.

The former PySide6/threaded backend is preserved in legacy-desktop.zip.
"""
from backend.session import VoiceSession
from backend.llm import chat_stream

KravoxBackend = VoiceSession
