#!/usr/bin/env python3
"""
시퀀스 기반 클립 빌더

- 프리메이드 씬: output/clips/{N}.mp4 → 정규화 후 배치
- 이미지 기반 씬: output/scenes/scene_{N:03d}.png → 정지 프레임 클립 생성
- 전체 합산 = voiceover 길이에 맞게 이미지 클립 길이 자동 조정
"""
import os, shutil, subprocess, sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "-q"], check=True)
    from PIL import Image

BASE       = Path(__file__).parent
SCENES_DIR = BASE / "output/scenes"
CLIPS_DIR  = BASE / "output/clips"
AUDIO_PATH = BASE / "output/audio/voiceover.mp3"
W, H, FPS  = 1920, 1080, 30

SEQUENCE = [
    1, 2, 17, 4, 18, 19, 3, 2, 4, 17, 18, 19, 1, 2, 3, 4, 18, 19, 2, 3,
    20, 5, 21, 22, 6, 23, 7, 24, 5, 21, 22, 6, 23, 7, 24, 2, 3, 18, 19, 20,
    5, 21, 22, 6, 23, 7, 24, 1, 2, 3, 8, 25, 9, 26, 10, 27, 8, 25, 9, 26,
    10, 27, 28, 3, 2, 28, 8, 25, 9, 26, 10, 27, 28, 1, 3, 29, 11, 30, 12, 31,
    29, 11, 30, 12, 31, 32, 2, 19, 29, 11, 30, 12, 31, 32, 7, 2, 3, 11, 30, 12,
    33, 13, 34, 33, 13, 34, 35, 3, 2, 35, 28, 36, 35, 28, 36, 14, 37, 14, 37, 35,
    2, 3, 28, 36, 14, 37, 1, 2, 3, 35, 38, 2, 3, 38, 7, 38, 14, 37, 38, 2,
    3, 38, 14, 37, 38, 6, 23, 38, 7, 14, 37, 38, 2, 3, 14, 15, 39, 15, 39, 27,
    28, 39, 15, 39, 16, 40, 16, 40, 1, 40, 16, 40, 14, 37, 40, 2, 3, 40, 1, 16, 40,
]

PREMADE_SCENES = {1, 2, 3, 4, 7, 9, 11, 12, 13}


def get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def normalize_premade(src: Path, out: Path) -> None:
    """오디오 제거 + 1920×1080 30fps yuv420p 통일."""
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-an",
        str(out),
    ], capture_output=True, check=True)


def make_image_clip(img_path: Path, duration: float, out: Path) -> None:
    """정지 이미지 → video-only libx264 클립."""
    n_frames = int(duration * FPS)
    img = Image.open(img_path).convert("RGB")
    scale = max(W / img.width, H / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - W) // 2
    top  = (nh - H) // 2
    frame_bytes = img.crop((left, top, left + W, top + H)).tobytes()

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(n_frames):
            proc.stdin.write(frame_bytes)
        proc.stdin.close()
    except BrokenPipeError:
        if proc.stdin:
            proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"make_image_clip 실패: {out}\n{proc.stderr.read().decode()[-800:]}")


def main() -> None:
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    norm_cache_dir = CLIPS_DIR / "_premade_norm"
    norm_cache_dir.mkdir(exist_ok=True)

    audio_dur = get_duration(AUDIO_PATH)
    print(f"오디오: {audio_dur:.2f}초 ({audio_dur/60:.1f}분)  |  시퀀스: {len(SEQUENCE)}슬롯")

    # 프리메이드 클립 원본 길이
    premade_dur: dict[int, float] = {}
    for n in PREMADE_SCENES:
        src = CLIPS_DIR / f"{n}.mp4"
        if not src.exists():
            print(f"  ⚠️  프리메이드 없음: {src}")
            continue
        premade_dur[n] = get_duration(src)

    # 이미지 슬롯 개수 및 할당 시간 계산
    premade_total = sum(premade_dur.get(s, 0.0) for s in SEQUENCE if s in PREMADE_SCENES)
    img_slots     = [i for i, s in enumerate(SEQUENCE) if s not in PREMADE_SCENES]
    img_dur       = (audio_dur - premade_total) / len(img_slots) if img_slots else 7.0

    print(f"  프리메이드 슬롯: {len(SEQUENCE) - len(img_slots)}개 → {premade_total:.1f}초")
    print(f"  이미지 슬롯:     {len(img_slots)}개 → 각 {img_dur:.3f}초")

    # 프리메이드 정규화 (씬당 1회)
    print("\n  프리메이드 정규화 중...")
    norm_map: dict[int, Path] = {}
    for n in sorted(premade_dur.keys()):
        norm_p = norm_cache_dir / f"{n}.mp4"
        if not norm_p.exists() or norm_p.stat().st_size == 0:
            src = CLIPS_DIR / f"{n}.mp4"
            print(f"    씬{n:2d} 정규화...", end=" ", flush=True)
            normalize_premade(src, norm_p)
            print("완료")
        else:
            print(f"    씬{n:2d} 캐시 재사용")
        norm_map[n] = norm_p

    # 클립 생성
    print(f"\n  클립 생성 중 (총 {len(SEQUENCE)}개)...")
    total = len(SEQUENCE)
    for idx, scene_n in enumerate(SEQUENCE, 1):
        out_path = CLIPS_DIR / f"clip_{idx:03d}.mp4"
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"  [{idx:3d}/{total}] 씬{scene_n:2d} 재사용")
            continue

        print(f"  [{idx:3d}/{total}] 씬{scene_n:2d} 생성...", end=" ", flush=True)

        if scene_n in norm_map:
            try:
                os.link(str(norm_map[scene_n]), str(out_path))
            except OSError:
                shutil.copy2(str(norm_map[scene_n]), str(out_path))
        else:
            img_path = SCENES_DIR / f"scene_{scene_n:03d}.png"
            if not img_path.exists():
                img_path = SCENES_DIR / f"scene_{scene_n:03d}.jpg"
            if not img_path.exists():
                img_path = SCENES_DIR / f"{scene_n}.png"
            if not img_path.exists():
                raise FileNotFoundError(f"씬 이미지 없음: scenes/scene_{scene_n:03d}.png")
            make_image_clip(img_path, img_dur, out_path)

        print("완료")

    actual_total = sum(
        get_duration(CLIPS_DIR / f"clip_{i:03d}.mp4") for i in range(1, total + 1)
    )
    print(f"\n✅ 완료: {total}개 클립")
    print(f"   클립 합산: {actual_total:.1f}초  |  오디오: {audio_dur:.1f}초  |  차이: {actual_total - audio_dur:+.1f}초")

    # render_video의 normalization 루프 완전 스킵을 위해 _norm/ 프리핏
    norm_dir = CLIPS_DIR / "_norm"
    norm_dir.mkdir(exist_ok=True)
    print("\n  _norm/ 프리핏 중...")
    for i in range(1, total + 1):
        src = CLIPS_DIR / f"clip_{i:03d}.mp4"
        dst = norm_dir / f"clip_{i:03d}.mp4"
        if dst.exists():
            continue
        try:
            os.link(str(src), str(dst))
        except OSError:
            shutil.copy2(str(src), str(dst))
    print(f"  _norm/ 완료: {total}개")

    print(f"\n   렌더링 실행:")
    print(f"   python3 run_pipeline.py --script script.txt --thumb 1 --skip-images --skip-tts --skip-upload --no-clean")


if __name__ == "__main__":
    main()
