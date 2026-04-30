#!/usr/bin/env python3
"""특정 씬 이미지만 재생성. 사용법: python regen_scene.py 14  또는  python regen_scene.py 14 17 6"""
import sys, os, io, json
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

SCENES_DIR = Path("output/scenes")

_COMFYUI_URL = "http://127.0.0.1:8188"
_COMFYUI_MODEL = "majicmixRealistic_v7.safetensors"

def fetch_image(prompt, seed, width=1280, height=720):
    import requests, uuid, websocket, json
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
    if len(sys.argv) < 2:
        print("사용법: python regen_scene.py <씬번호> [씬번호2 ...]")
        print("예시:  python regen_scene.py 14")
        print("예시:  python regen_scene.py 6 11 14")
        sys.exit(1)

    scene_nums = [int(x) for x in sys.argv[1:]]

    data = json.loads(Path("scene_prompts.json").read_text(encoding="utf-8"))
    # 인덱스: scene 번호는 1-based
    prompts = {}
    for d in data:
        idx = d.get("scene") or (data.index(d) + 1)
        prompt = d.get("prompt_en") or d.get("prompt", "")
        prompts[idx] = prompt

    for num in scene_nums:
        if num not in prompts:
            print(f"⚠️  scene_{num} 프롬프트 없음 — 건너뜀")
            continue
        prompt = prompts[num]
        seed = 88888 + (num - 1)
        print(f"[scene_{num}] 생성 중... (seed={seed})")
        print(f"  프롬프트: {prompt[:80]}...")
        img = fetch_image(prompt, seed)
        out = SCENES_DIR / f"scene_{num}.png"
        img = img.resize((1920, 1080))
        img.save(out)
        print(f"  ✅ 저장: {out}")

if __name__ == "__main__":
    main()
