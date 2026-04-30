#!/usr/bin/env python3
"""kokoro TTS 헬퍼 — python3.11로 실행됨"""
import sys, json
from pathlib import Path
import soundfile as sf
import numpy as np
from kokoro import KPipeline

text, voice, out_wav = sys.argv[1], sys.argv[2], sys.argv[3]
pipeline = KPipeline(lang_code="j")
parts = [audio for _, _, audio in pipeline(text, voice=voice, speed=1.0)]
if not parts: raise RuntimeError("empty audio")
sf.write(out_wav, np.concatenate(parts), 24000)
