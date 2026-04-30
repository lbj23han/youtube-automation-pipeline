"""썸네일 퀄리티 테스트 — HuggingFace FLUX.1-schnell"""
import subprocess, os, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config.env")
HF_TOKEN = os.getenv("HF_TOKEN", "")

try:
    import requests
except ImportError:
    subprocess.run(["pip", "install", "requests", "-q"])
    import requests

prompt = (
    "elderly Japanese man sitting alone at low wooden table, "
    "single bowl of rice, empty chair across, dim warm lamp light, "
    "Showa era 1970s Japan tatami room, oil painting style, "
    "highly detailed, sharp focus, dramatic cinematic lighting, "
    "emotional atmosphere, fictional character, masterpiece quality"
)

out = Path("output/thumbnails/test_thumb.png")
out.parent.mkdir(parents=True, exist_ok=True)

API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
headers = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json",
}
payload = {"inputs": prompt}

print("생성 중... FLUX.1-schnell (약 20~40초)")
for attempt in range(3):
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        print(f"  상태: {resp.status_code}, 크기: {len(resp.content)} bytes")

        content_type = resp.headers.get("content-type", "")
        if resp.status_code == 200 and "image" in content_type:
            out.write_bytes(resp.content)
            print(f"✅ 저장 완료: {out}")
            subprocess.run(["open", str(out)])
            break
        elif resp.status_code == 503:
            wait = 20
            try: wait = resp.json().get("estimated_time", 20)
            except: pass
            print(f"  모델 워밍업 중... {wait:.0f}초 대기")
            time.sleep(min(wait, 30))
        else:
            print(f"  응답: {resp.text[:300]}")
            if attempt < 2:
                print(f"  {10}초 후 재시도...")
                time.sleep(10)
    except Exception as e:
        print(f"  오류: {e}")
        break
