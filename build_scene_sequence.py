#!/usr/bin/env python3
"""
소스 씬 1-45 기반, 지정된 시퀀스 순서로 scene_1.png~scene_265.png 생성
사용법: python3 build_scene_sequence.py
"""
import os, io, json, shutil, time, uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config.env")

# ── 시퀀스 (265개 숫자, 1-indexed 소스 씬 번호) ─────────────────────────────
SEQUENCE = [
    1,2,1,2,1,3,2,1,3,4,3,4,1,2,3,4,5,6,7,5,6,7,8,9,8,5,6,7,9,8,6,7,5,8,9,
    10,11,10,11,8,9,10,11,12,10,12,13,45,13,45,15,45,13,14,15,14,16,1,2,3,5,6,
    7,5,8,9,10,11,12,13,45,15,14,16,17,16,17,18,17,19,18,20,19,20,21,20,22,21,
    23,22,24,23,25,24,18,19,20,21,22,23,24,26,27,26,28,27,23,24,26,27,28,20,21,
    22,23,24,26,27,28,18,19,20,22,21,23,24,26,28,27,29,28,29,30,29,30,31,30,31,
    32,31,32,33,32,33,34,33,34,35,34,35,36,35,36,24,25,26,27,28,29,30,31,32,33,
    34,35,36,25,36,24,35,36,37,36,37,38,37,38,39,38,39,40,39,40,41,40,41,42,41,
    42,39,40,41,42,39,40,41,42,43,42,43,44,43,44,37,38,39,40,41,42,43,44,43,44,
    37,43,44,43,44,43,44,43,44,1,2,3,4,5,6,7,8,9,10,11,12,13,45,15,14,16,17,18,
    19,20,21,22,23,24,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,
]

assert len(SEQUENCE) == 265, f"시퀀스 길이 오류: {len(SEQUENCE)}"

UNIQUE_SOURCES = sorted(set(SEQUENCE))  # 1-24

# ── 경로 ───────────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("output/scenes")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SRC_DIR = OUTPUT_DIR / "_src"
SRC_DIR.mkdir(exist_ok=True)

# ── 프롬프트 로드 (1-indexed: scene 1 = index 0) ──────────────────────────────
with open("scene_prompts.json", encoding="utf-8") as f:
    RAW_SCENES = json.load(f)

def get_prompt(n: int) -> str:
    """1-indexed 씬 번호 → prompt 문자열"""
    return RAW_SCENES[n - 1]["prompt"]

# ── 스타일 템플릿 ──────────────────────────────────────────────────────────────
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

NEGATIVE = (
    "deformed hands, extra fingers, missing fingers, fused fingers, too many fingers, "
    "malformed hands, broken fingers, twisted fingers, clawed hands, melted hands, "
    "extra limbs, missing limbs, floating limbs, disconnected body parts, "
    "bad anatomy, wrong anatomy, mutated body, disfigured, deformed, "
    "distorted face, melted face, asymmetrical eyes, crossed eyes, "
    "blurry, out of focus, low quality, jpeg artifacts, pixelated, "
    "watermark, text in image, signature, "
    "bare legs, exposed legs, short skirt, miniskirt, shorts, "
    "revealing clothing, low neckline, cleavage, tight clothes, "
    "3d render, cgi, nsfw, nude, violence, gore"
)

_COMFYUI_URL   = "http://127.0.0.1:8188"
_COMFYUI_MODEL = "majicmixRealistic_v7.safetensors"


def fetch_image(prompt: str, seed: int):
    import requests, websocket
    from PIL import Image

    client_id = str(uuid.uuid4())
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": _COMFYUI_MODEL}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt[:900]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEGATIVE}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1280, "height": 720, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
            "latent_image": ["4", 0], "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "steps": 20, "cfg": 7.0,
            "seed": seed, "denoise": 1.0,
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "seq_out"}},
    }
    resp = requests.post(f"{_COMFYUI_URL}/prompt",
                         json={"prompt": workflow, "client_id": client_id}, timeout=30)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]

    ws = websocket.WebSocket()
    ws.connect(f"ws://127.0.0.1:8188/ws?clientId={client_id}")
    try:
        while True:
            msg = json.loads(ws.recv())
            if msg.get("type") == "executing":
                if msg["data"].get("node") is None and msg["data"].get("prompt_id") == prompt_id:
                    break
    finally:
        ws.close()

    history = requests.get(f"{_COMFYUI_URL}/history/{prompt_id}", timeout=30).json()
    for node_out in history[prompt_id]["outputs"].values():
        if "images" in node_out:
            info = node_out["images"][0]
            img_resp = requests.get(f"{_COMFYUI_URL}/view",
                params={"filename": info["filename"], "subfolder": info["subfolder"], "type": info["type"]},
                timeout=60)
            return Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    raise RuntimeError("ComfyUI 출력 이미지 없음")


def step1_generate_sources():
    """소스 씬 1-24 생성 → _src/src_{N}.png"""
    print(f"\n[1/2] 소스 씬 생성 ({len(UNIQUE_SOURCES)}개): {UNIQUE_SOURCES}\n")
    for n in UNIQUE_SOURCES:
        out = SRC_DIR / f"src_{n}.png"
        if out.exists():
            print(f"  [{n:02d}] 이미 존재, 건너뜀")
            continue

        raw_prompt = get_prompt(n)
        full_prompt = STYLE_TEMPLATE.replace("{scene}", raw_prompt)
        seed = 88888 + n

        print(f"  [{n:02d}]", end=" ", flush=True)
        try:
            from PIL import Image
            img = fetch_image(full_prompt, seed=seed)
            img = img.resize((1920, 1080))
            img.save(out)
            print("✅")
        except Exception as e:
            print(f"❌ {e}")


def step2_build_sequence():
    """SEQUENCE 순서대로 scene_1.png~scene_144.png 복사"""
    print(f"\n[2/2] 시퀀스 배치 ({len(SEQUENCE)}개 씬 생성)\n")
    missing = []
    for n in UNIQUE_SOURCES:
        if not (SRC_DIR / f"src_{n}.png").exists():
            missing.append(n)
    if missing:
        print(f"❌ 소스 씬 없음: {missing}")
        print("   step1 을 먼저 완료하세요.")
        return

    for idx, src_n in enumerate(SEQUENCE, start=1):
        src = SRC_DIR / f"src_{src_n}.png"
        dst = OUTPUT_DIR / f"scene_{idx}.png"
        shutil.copy2(src, dst)

    print(f"✅ scene_1.png ~ scene_{len(SEQUENCE)}.png 생성 완료")
    print(f"   저장 위치: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    step1_generate_sources()
    step2_build_sequence()
