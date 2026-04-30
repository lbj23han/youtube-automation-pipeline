#!/usr/bin/env python3
"""
특정 씬만 골라 재생성 — output/scenes/scene_XX.png 덮어쓰기
사용법: python3 regen_scenes.py
"""
import os, sys, io, json, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config.env")

NEGATIVE = (
    "deformed hands, extra fingers, missing fingers, fused fingers, too many fingers, "
    "malformed hands, broken fingers, twisted fingers, clawed hands, melted hands, "
    "extra limbs, missing limbs, floating limbs, disconnected body parts, "
    "extra legs, three legs, four legs, extra arms, three arms, duplicate limbs, "
    "extra hands, three hands, wrong number of limbs, multiple legs, "
    "bad anatomy, wrong anatomy, mutated body, disfigured, deformed, "
    "distorted face, melted face, asymmetrical eyes, crossed eyes, lazy eye, "
    "extra eyes, missing eyes, wrong eye direction, wall eyes, uneven eyes, "
    "heterochromia, dead eyes, shiny eyes, "
    "distorted nose, distorted mouth, extra mouth, duplicate face, "
    "uncanny valley, zombie face, corpse face, horror face, "
    "blurry, out of focus, low quality, jpeg artifacts, pixelated, "
    "watermark, text in image, signature, "
    "bare legs, exposed legs, short skirt, miniskirt, shorts, "
    "revealing clothing, low neckline, cleavage, tight clothes, "
    "sexy pose, suggestive pose, seductive, lingerie, "
    "3d render, cgi, nsfw, nude, violence, gore"
)

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
    ALL_SCENES = {s["scene"]: s for s in json.load(f)}

OUTPUT_DIR = Path("output/scenes")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 재생성할 씬 번호 목록 ───────────────────────────────────────────────────────
REGEN = [1, 5, 13, 15, 18, 20, 21, 23, 24, 27, 29, 31, 33, 34, 37, 39, 41, 47]


def _expand_char_tokens(prompt: str) -> tuple[str, int]:
    seed_offset = 0
    for name, desc in CHARACTERS.items():
        token = "{" + name + "}"
        if token in prompt:
            short_desc = ", ".join(desc.split(", ")[:2])
            prompt = prompt.replace(token, short_desc)
            seed_offset += _CHAR_SEED.get(name, 0)
    return prompt, seed_offset


_COMFYUI_URL = "http://127.0.0.1:8188"
_COMFYUI_MODEL = "majicmixRealistic_v7.safetensors"

def fetch_image(prompt, width=1280, height=720, seed=42):
    import requests, uuid, websocket
    from PIL import Image

    client_id = str(uuid.uuid4())
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": _COMFYUI_MODEL}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt[:900]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEGATIVE}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
            "latent_image": ["4", 0], "sampler_name": "dpmpp_2m",
            "scheduler": "karras", "steps": 20, "cfg": 7.0,
            "seed": seed, "denoise": 1.0
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "regen_out"}},
    }
    resp = requests.post(f"{_COMFYUI_URL}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=30)
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


def main():
    print(f"\n🎨 씬 재생성: {REGEN}\n")

    for scene_num in REGEN:
        entry = ALL_SCENES.get(scene_num)
        if not entry:
            print(f"  [{scene_num:02d}] 프롬프트 없음, 건너뜀")
            continue

        raw = entry["prompt_en"]
        expanded, char_seed = _expand_char_tokens(raw)
        prompt = STYLE_TEMPLATE.replace("{scene}", expanded)
        seed = 88888 + (char_seed if char_seed else scene_num)

        out_path = OUTPUT_DIR / f"scene_{scene_num}.png"
        print(f"  [{scene_num:02d}]", end=" ", flush=True)

        try:
            img = fetch_image(prompt, 1280, 720, seed=seed)
            img = img.resize((1920, 1080))
            img.save(out_path)
            print(f"✅ 저장됨")
        except Exception as e:
            print(f"❌ 실패: {e}")

    print(f"\n완료. 저장 위치: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
