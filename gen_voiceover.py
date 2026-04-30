#!/usr/bin/env python3
"""script.txt → output/audio/voiceover.mp3 (amitaro/style-bert-vits2)"""
import re, subprocess, sys
from pathlib import Path

BASE       = Path(__file__).parent
AUDIO_DIR  = BASE / "output/audio"
SCRIPT     = BASE / "script.txt"
OUT        = AUDIO_DIR / "voiceover.mp3"

SBV2_MODEL  = "amitaro/amitaro"
SBV2_STYLE  = "04"
SBV2_LENGTH = 1.15
CHUNK_LIMIT = 500

AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ── TTS model setup ──────────────────────────────────────────────────────────
from style_bert_vits2.nlp import bert_models
from style_bert_vits2.constants import Languages
from style_bert_vits2.tts_model import TTSModel
import soundfile as sf

bert_dir   = str(BASE / "model_assets/bert/deberta-v2-large-japanese-char-wwm")
model_base = BASE / "model_assets/voice" / SBV2_MODEL
safetensors = list(model_base.glob("*.safetensors"))
if not safetensors:
    print(f"❌ safetensors 없음: {model_base}"); sys.exit(1)

print("모델 로딩...", flush=True)
bert_models.load_model(Languages.JP, pretrained_model_name_or_path=bert_dir)
bert_models.load_tokenizer(Languages.JP, pretrained_model_name_or_path=bert_dir)
model = TTSModel(
    model_path=safetensors[0],
    config_path=model_base / "config.json",
    style_vec_path=model_base / "style_vectors.npy",
    device="cpu",
)
print("모델 로딩 완료", flush=True)


# ── Script → chunks ──────────────────────────────────────────────────────────
text = SCRIPT.read_text(encoding="utf-8")

paragraphs = re.split(r'\n\s*\n', text)
paragraphs = [' '.join(l.strip() for l in p.splitlines() if l.strip()) for p in paragraphs]
paragraphs = [p for p in paragraphs if p]

sentences = []
for para in paragraphs:
    parts = re.split(r'(?<=[。！？])', para)
    sentences.extend([s.strip() for s in parts if s.strip()])

chunks, current = [], ""
for s in sentences:
    if len(current) + len(s) > CHUNK_LIMIT:
        if current: chunks.append(current.strip())
        current = s
    else:
        current += s
if current.strip(): chunks.append(current.strip())

print(f"청크 {len(chunks)}개", flush=True)


# ── TTS each chunk ───────────────────────────────────────────────────────────
chunk_paths = []
for i, chunk in enumerate(chunks, 1):
    wav = AUDIO_DIR / f"chunk_{i:03d}.wav"
    mp3 = AUDIO_DIR / f"chunk_{i:03d}.mp3"
    print(f"  [{i}/{len(chunks)}] {len(chunk)}자...", end=" ", flush=True)
    sr, audio = model.infer(text=chunk, style=SBV2_STYLE, length=SBV2_LENGTH)
    sf.write(str(wav), audio, sr)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-q:a", "2", str(mp3)],
        capture_output=True, check=True
    )
    wav.unlink(missing_ok=True)
    chunk_paths.append(str(mp3))
    print("완료", flush=True)


# ── concat → voiceover.mp3 ───────────────────────────────────────────────────
if len(chunk_paths) == 1:
    Path(chunk_paths[0]).rename(OUT)
else:
    list_file = AUDIO_DIR / "chunks.txt"
    list_file.write_text(
        "\n".join(f"file '{Path(p).resolve()}'" for p in chunk_paths),
        encoding="utf-8"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(list_file), "-c", "copy", str(OUT)],
        capture_output=True, check=True
    )
    list_file.unlink()
    for p in chunk_paths:
        try: Path(p).unlink()
        except: pass

print(f"\n✅ {OUT}", flush=True)
