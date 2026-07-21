#!/usr/bin/env python3
"""
AivisSpeech 속도 테스트
앱 실행 후: python3 test_aivis_speed.py
"""
import json, time, urllib.request, urllib.parse
from pathlib import Path

VVOX_URL  = "http://localhost:10101"
CONFIG    = json.loads(Path("video_config.json").read_text(encoding="utf-8"))
SPEAKER_ID = CONFIG["tts"]["speaker_id"]
SPEED_SCALE = CONFIG["tts"]["speed_scale"]
OUT_WAV   = Path(f"output/audio/_aivis_test_mai_normal_{SPEED_SCALE:.2f}.wav")
OUT_WAV.parent.mkdir(parents=True, exist_ok=True)

# 테스트 텍스트 (약 30초 분량)
TEST_TEXT = (
    "白峰藩の北に、人の足がほとんど入らぬ山がありました。"
    "春でも朝は霧が深く、冬になれば雪が腰まで積もる。"
    "その山の麓に、小さな村がありました。"
    "村人たちは、山を畏れながらも、山の恵みで生きておりました。"
)

def check_server():
    try:
        with urllib.request.urlopen(f"{VVOX_URL}/version", timeout=3) as r:
            version = r.read().decode().strip()
        print(f"✅ 서버 응답: {version}")
        return True
    except Exception as e:
        print(f"❌ 서버 없음: {e}")
        print("   → AivisSpeech 앱을 실행해주세요")
        return False

def get_speakers():
    with urllib.request.urlopen(f"{VVOX_URL}/speakers", timeout=10) as r:
        return json.loads(r.read())

def synthesize(text, speaker_id):
    params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    req = urllib.request.Request(
        f"{VVOX_URL}/audio_query?{params}", method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        query = json.loads(r.read())

    query["speedScale"] = SPEED_SCALE

    body = json.dumps(query).encode()
    params2 = urllib.parse.urlencode({"speaker": speaker_id})
    req2 = urllib.request.Request(
        f"{VVOX_URL}/synthesis?{params2}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req2, timeout=120) as r:
        return r.read()

def main():
    if not check_server():
        return

    # 화자 목록 출력
    print("\n사용 가능한 화자:")
    speakers = get_speakers()
    for s in speakers:
        for st in s["styles"]:
            print(f"  ID {st['id']:3d} : {s['name']} ({st['name']})")

    speaker_id = SPEAKER_ID
    print(f"\n테스트 화자 ID: {speaker_id} (まい・ノーマル)")
    print(f"재생 속도: {SPEED_SCALE:.2f}")
    print(f"텍스트 길이: {len(TEST_TEXT)}자")
    print("생성 중...", end=" ", flush=True)

    t0 = time.time()
    wav_bytes = synthesize(TEST_TEXT, speaker_id)
    elapsed = time.time() - t0

    OUT_WAV.write_bytes(wav_bytes)

    # WAV 헤더에서 실제 오디오 길이 계산 (44바이트 헤더 이후 PCM)
    import wave
    with wave.open(str(OUT_WAV)) as wf:
        audio_sec = wf.getnframes() / wf.getframerate()

    ratio = elapsed / audio_sec
    full_25min = 1554  # 현재 voiceover.mp3 길이 (초)
    estimated = full_25min * ratio / 60

    print(f"완료")
    print(f"\n─────────────────────────────")
    print(f"생성 시간  : {elapsed:.1f}초")
    print(f"오디오 길이: {audio_sec:.1f}초")
    print(f"속도 비율  : 실시간의 {ratio:.2f}배 소요")
    print(f"\n25분 전체 예상 시간: 약 {estimated:.0f}분")
    print(f"─────────────────────────────")
    print(f"\n샘플 저장: {OUT_WAV}")
    print(f"재생 확인: afplay {OUT_WAV}")

if __name__ == "__main__":
    main()
