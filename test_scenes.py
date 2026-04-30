#!/usr/bin/env python3
"""
무작위 씬 5장 테스트 생성
사용법: python test_scenes.py
"""
import os, sys, io, json, random, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config.env")

# ── 설정 로드 ──────────────────────────────────────────────────────────────────
with open("video_config.json", encoding="utf-8") as f:
    vc = json.load(f)

CHARACTERS = vc["image"].get("characters", {})
_CHAR_SEED  = {name: abs(hash(name)) % 50000 for name in CHARACTERS}

STYLE_TEMPLATE = (
    "Japanese watercolor picture book illustration, "
    "soft hand-painted style, visible paper grain and wash texture, "
    "gentle fine pencil linework, muted pastel tones, pale warm background, "
    "wide or medium cinematic shot showing full figures and environment, "
    "{scene}, "
    "quiet sentimental atmosphere, natural diffused light, "
    "traditional Japanese storybook aesthetic, Ghibli-adjacent delicate rendering, "
    "no text, no watermark, no Japanese text, no kanji, "
    "not Korean webtoon, not manga close-up portrait, not face crop, "
    "not thick digital outlines, not saturated colors, "
    "not photorealistic, not 3D, not western cartoon"
)

with open("scene_prompts.json", encoding="utf-8") as f:
    ALL_SCENES = json.load(f)

OUTPUT_DIR = Path("output/test_scenes")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _expand_char_tokens(prompt: str) -> tuple[str, int]:
    seed_offset = 0
    for name, desc in CHARACTERS.items():
        token = "{" + name + "}"
        if token in prompt:
            short_desc = ", ".join(desc.split(", ")[:2])
            prompt = prompt.replace(token, short_desc)
            seed_offset += _CHAR_SEED.get(name, 0)
    return prompt, seed_offset


def fetch_image(prompt, width=1280, height=720, seed=42):
    import requests
    from PIL import Image

    api_key = os.getenv("PIXAZO_API_KEY", "")
    if not api_key:
        print("❌ PIXAZO_API_KEY 없음"); sys.exit(1)

    url = "https://gateway.pixazo.ai/flux-1-schnell/v1/getData"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Ocp-Apim-Subscription-Key": api_key,
    }
    payload = {
        "prompt": prompt[:900],
        "num_steps": vc["image"].get("num_steps", 8),
        "seed": seed,
        "height": height,
        "width": width,
    }

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                img_url = data.get("output", "")
                if not img_url:
                    raise ValueError(f"output URL 없음: {data}")
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    img_resp = requests.get(img_url, timeout=60, verify=False)
                return Image.open(io.BytesIO(img_resp.content)).convert("RGB")
            else:
                print(f"    응답 이상 {resp.status_code}: {resp.text[:80]}, 재시도...")
                time.sleep(5)
        except Exception as e:
            if attempt < 2:
                print(f"    재시도... ({e})")
                time.sleep(5)
            else:
                raise


def main():
    # 문제됐던 씬 20, 23 재검증
    force = {20, 23}
    picked = [s for s in ALL_SCENES if s["scene"] in force]
    picked.sort(key=lambda x: x["scene"])

    print(f"\n🎨 테스트 씬 5장 생성")
    print(f"   선택된 씬: {[s['scene'] for s in picked]}\n")

    for entry in picked:
        scene_num = entry["scene"]
        mood      = entry.get("mood", "")
        raw       = entry["prompt_en"]

        expanded, char_seed = _expand_char_tokens(raw)
        prompt = STYLE_TEMPLATE.replace("{scene}", expanded)
        seed   = 88888 + (char_seed if char_seed else scene_num)

        out_path = OUTPUT_DIR / f"test_scene_{scene_num:02d}_{mood}.png"
        print(f"  [{scene_num:02d}] mood={mood:<10s}", end=" ", flush=True)

        try:
            img = fetch_image(prompt, 1280, 720, seed=seed)
            img = img.resize((1920, 1080))
            img.save(out_path)
            print(f"✅ {out_path.name}")
        except Exception as e:
            print(f"❌ 실패: {e}")

    print(f"\n완료. 저장 위치: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
