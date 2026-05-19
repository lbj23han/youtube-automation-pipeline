#!/usr/bin/env python3
"""
script.txt → output/audio/voiceover.mp3  (VoiceVox Engine API)

사전 준비:
  Docker 방식 (권장):
    docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest

  앱 방식:
    https://voicevox.hiroshiba.jp/ 에서 VOICEVOX 다운로드 후 실행
    (앱 실행만 해두면 50021 포트에서 API 자동 시작)

화자 ID (SPEAKER_ID):
  앱 켜진 상태에서 확인:  curl http://localhost:50021/speakers | python3 -m json.tool
  주요 여성 내레이션 화자:
    3  : 春日部つむぎ (ノーマル)  — 따뜻하고 자연스러운 여성
    8  : WhiteCUL    (ノーマル)   — 맑고 차분한 여성
    14 : 冥鳴ひまり  (ノーマル)   — 부드러운 여성
    58 : 栗田まろん  (ノーマル)   — 성숙한 여성 내레이션
  주요 남성 내레이션 화자:
    13 : 青山龍星    (ノーマル)   — 깊고 차분한 남성
"""

import re, json, time, subprocess
import urllib.request, urllib.parse, urllib.error
from pathlib import Path

# ── 설정 ─────────────────────────────────────────────────────────────────────
_VC          = json.loads((Path(__file__).parent / "video_config.json").read_text())
SPEAKER_ID   = _VC["tts"]["speaker_id"]
SPEED_SCALE  = _VC["tts"]["speed_scale"]
PITCH_SCALE  = _VC["tts"]["pitch_scale"]
INTONATION   = _VC["tts"]["intonation_scale"]
VVOX_URL     = "http://localhost:10101"
CHUNK_LIMIT  = _VC["tts"]["chunk_limit"]

BASE      = Path(__file__).parent
AUDIO_DIR = BASE / "output/audio"
SCRIPT    = BASE / "script.txt"
OUT       = AUDIO_DIR / "voiceover.mp3"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ── 청크 길이 측정 ───────────────────────────────────────────────────────────
def _get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# ── VoiceVox 서버 체크 ────────────────────────────────────────────────────────
def check_server():
    try:
        urllib.request.urlopen(f"{VVOX_URL}/version", timeout=3)
        return True
    except Exception:
        return False


# ── TTS (한 청크) ─────────────────────────────────────────────────────────────
def synthesize(text: str, out_wav: Path):
    # 1) audio_query
    params = urllib.parse.urlencode({"text": text, "speaker": SPEAKER_ID})
    req = urllib.request.Request(
        f"{VVOX_URL}/audio_query?{params}", method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        query = json.loads(resp.read())

    # 파라미터 덮어쓰기
    query["speedScale"]      = SPEED_SCALE
    query["pitchScale"]      = PITCH_SCALE
    query["intonationScale"] = INTONATION

    # 2) synthesis
    body = json.dumps(query).encode()
    params2 = urllib.parse.urlencode({"speaker": SPEAKER_ID})
    req2 = urllib.request.Request(
        f"{VVOX_URL}/synthesis?{params2}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req2, timeout=120) as resp2:
        out_wav.write_bytes(resp2.read())


# ── 스크립트 → 청크 분리 ──────────────────────────────────────────────────────
def split_script(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    paragraphs = re.split(r'\n\s*\n', text)
    sentences = []
    for para in paragraphs:
        parts = re.split(r'(?<=[。！？\n])', para)
        sentences.extend(s.strip() for s in parts if s.strip())

    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > CHUNK_LIMIT:
            if current:
                chunks.append(current.strip())
            current = s
        else:
            current += s
    if current.strip():
        chunks.append(current.strip())
    return chunks


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    if not check_server():
        print("❌ VoiceVox 엔진이 실행되지 않았어요.")
        print()
        print("  Docker 방식 (터미널 새 탭에서 실행):")
        print("    docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest")
        print()
        print("  앱 방식:")
        print("    https://voicevox.hiroshiba.jp/ → VOICEVOX 다운로드 후 실행")
        return

    chunks = split_script(SCRIPT)
    print(f"화자 ID: {SPEAKER_ID} | 청크: {len(chunks)}개 | 속도: {SPEED_SCALE}")

    chunk_paths, timing_data = [], []
    cursor = 0.0
    for i, chunk in enumerate(chunks, 1):
        wav = AUDIO_DIR / f"vvox_chunk_{i:03d}.wav"
        mp3 = AUDIO_DIR / f"vvox_chunk_{i:03d}.mp3"
        print(f"  [{i}/{len(chunks)}] {len(chunk)}자...", end=" ", flush=True)
        try:
            synthesize(chunk, wav)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-q:a", "2", str(mp3)],
                capture_output=True, check=True,
            )
            wav.unlink(missing_ok=True)
            dur = _get_duration(mp3)
            timing_data.append({"text": chunk, "start": round(cursor, 3), "end": round(cursor + dur, 3)})
            cursor += dur
            chunk_paths.append(str(mp3))
            print("완료")
        except Exception as e:
            print(f"❌ {e}")

    if not chunk_paths:
        print("❌ 생성된 청크가 없어요."); return

    if len(chunk_paths) == 1:
        Path(chunk_paths[0]).rename(OUT)
    else:
        list_file = AUDIO_DIR / "vvox_chunks.txt"
        list_file.write_text(
            "\n".join(f"file '{Path(p).resolve()}'" for p in chunk_paths),
            encoding="utf-8",
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", str(OUT)],
            capture_output=True, check=True,
        )
        list_file.unlink(missing_ok=True)
        for p in chunk_paths:
            Path(p).unlink(missing_ok=True)

    TIMING_FILE = AUDIO_DIR / "chunks_timing.json"
    TIMING_FILE.write_text(json.dumps(timing_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {OUT}")
    print(f"✅ {TIMING_FILE}")


if __name__ == "__main__":
    main()
