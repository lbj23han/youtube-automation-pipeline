#!/usr/bin/env python3
"""
BGM 자동 다운로드 스크립트
출처: incompetech.com (Kevin MacLeod) — CC BY 4.0 / 유튜브 수익화 가능
폴더 구조: assets/bgm/{mood}/track.mp3

사용법:
  python3 bgm_downloader.py           # 전체 무드 다운로드
  python3 bgm_downloader.py --mood calm
  python3 bgm_downloader.py --list    # 트랙 목록만 출력
"""

import argparse
import ssl
import time
import urllib.request
from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets" / "bgm"
INCOMPETECH_BASE = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
MAOUDAMASHII_BASE = "https://maoudamashii.jokersounds.com/music/bgm/"

# ─── 무드별 트랙 카탈로그 ───────────────────────────────────────────────────────
# incompetech: CC BY 4.0 (저작자 표시 필요 — 영상 설명란에 "Music by Kevin MacLeod" 추가)
# 파일명: 공백은 %20 인코딩
CATALOG = {
    "calm": [
        # 잔잔하고 회상적인 — 일상, 도입부, 독백
        {"name": "Gymnopedie No 1",          "url": INCOMPETECH_BASE + "Gymnopedie%20No%201.mp3"},
        {"name": "Gymnopedie No 3",          "url": INCOMPETECH_BASE + "Gymnopedie%20No%203.mp3"},
        {"name": "Impact Andante",           "url": INCOMPETECH_BASE + "Impact%20Andante.mp3"},
    ],
    "warm": [
        # 따뜻한 일상감 — 가족, 식사, 소소한 행복
        {"name": "Carefree",                 "url": INCOMPETECH_BASE + "Carefree.mp3"},
        {"name": "Touching Moments One",     "url": INCOMPETECH_BASE + "Touching%20Moments%20One%20-%20Pulse.mp3"},
    ],
    "nostalgic": [
        # 그리움, 회상 — 옛날 이야기, 추억
        {"name": "Canon in D Major",         "url": INCOMPETECH_BASE + "Canon%20in%20D%20Major.mp3"},
        {"name": "Gymnopedie No 1",          "url": INCOMPETECH_BASE + "Gymnopedie%20No%201.mp3"},
    ],
    "hopeful": [
        # 희망적이고 밝은 — 엔딩, 새 출발, 봄
        {"name": "Inspired",                 "url": INCOMPETECH_BASE + "Inspired.mp3"},
        {"name": "Touching Moments Two",     "url": INCOMPETECH_BASE + "Touching%20Moments%20Two%20-%20Higher.mp3"},
    ],
    "sad": [
        # 슬프고 무거운 — 이별, 상실, 눈물
        {"name": "Sad Trio",                 "url": INCOMPETECH_BASE + "Sad%20Trio.mp3"},
        {"name": "Crossing the Chasm",       "url": INCOMPETECH_BASE + "Crossing%20the%20Chasm.mp3"},
    ],
    "tense": [
        # 긴박, 불안 — 갈등, 위기
        {"name": "Anxiety",                  "url": INCOMPETECH_BASE + "Anxiety.mp3"},
        {"name": "Thinking Music",           "url": INCOMPETECH_BASE + "Thinking%20Music.mp3"},
    ],
    "healing": [
        # 치유적인 — 화해, 감동, 위로
        {"name": "Touching Moments One",     "url": INCOMPETECH_BASE + "Touching%20Moments%20One%20-%20Pulse.mp3"},
        {"name": "Touching Moments Two",     "url": INCOMPETECH_BASE + "Touching%20Moments%20Two%20-%20Higher.mp3"},
    ],
    "funny": [
        # 유쾌하고 코믹한 — 웃긴 상황, 가벼운 해프닝
        {"name": "Sneaky Snitch",            "url": INCOMPETECH_BASE + "Sneaky%20Snitch.mp3"},
        {"name": "Fluffing a Duck",          "url": INCOMPETECH_BASE + "Fluffing%20a%20Duck.mp3"},
    ],
    "dramatic": [
        # 드라마틱 — 충격, 반전
        {"name": "Crossing the Chasm",       "url": INCOMPETECH_BASE + "Crossing%20the%20Chasm.mp3"},
        {"name": "Anxiety",                  "url": INCOMPETECH_BASE + "Anxiety.mp3"},
    ],
}

# ─── 유틸리티 ─────────────────────────────────────────────────────────────────
def _download(url: str, dest: Path, label: str) -> bool:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = resp.read()
        if len(data) < 10_000:
            print(f"  ⚠️  {label}: 파일 너무 작음 ({len(data)}bytes) — 건너뜀")
            return False
        dest.write_bytes(data)
        print(f"  ✅ {label} ({len(data)//1024}KB)")
        return True
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        return False


def download_mood(mood: str, overwrite: bool = False):
    tracks = CATALOG.get(mood, [])
    if not tracks:
        print(f"  [!] 카탈로그에 {mood} 무드 없음")
        return

    dest_dir = ASSETS_DIR / mood
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n── {mood.upper()} ({len(tracks)}트랙) → {dest_dir} ──")
    downloaded = 0
    for track in tracks:
        safe_name = track["name"].replace(" ", "_") + ".mp3"
        dest = dest_dir / safe_name
        if dest.exists() and not overwrite:
            print(f"  ⏭️  {track['name']} (캐시)")
            continue
        ok = _download(track["url"], dest, track["name"])
        if ok:
            downloaded += 1
        time.sleep(0.3)  # 서버 부하 방지

    existing = len(list(dest_dir.glob("*.mp3")))
    print(f"  → {mood}: 총 {existing}개 트랙 준비됨")


def list_catalog():
    print("\n📋 BGM 카탈로그")
    print("=" * 60)
    for mood, tracks in CATALOG.items():
        print(f"\n[{mood.upper()}] {len(tracks)}트랙")
        for t in tracks:
            dest = ASSETS_DIR / mood / (t["name"].replace(" ", "_") + ".mp3")
            status = "✅" if dest.exists() else "  "
            print(f"  {status} {t['name']}")


def main():
    parser = argparse.ArgumentParser(description="BGM 다운로더")
    parser.add_argument("--mood", help="특정 무드만 다운로드 (healing/calm/warm/hopeful/sad/dramatic)")
    parser.add_argument("--overwrite", action="store_true", help="기존 파일 덮어쓰기")
    parser.add_argument("--list", action="store_true", help="카탈로그 목록 출력")
    args = parser.parse_args()

    if args.list:
        list_catalog()
        return

    moods = [args.mood] if args.mood else list(CATALOG.keys())
    print(f"🎵 BGM 다운로드 시작 ({', '.join(moods)})")
    print("📜 출처: incompetech.com (Kevin MacLeod) — CC BY 4.0")
    print("   유튜브 영상 설명란에 다음을 추가하세요:")
    print('   "Music by Kevin MacLeod (incompetech.com) — Licensed under Creative Commons: By Attribution 4.0"')
    print()

    for mood in moods:
        download_mood(mood, overwrite=args.overwrite)

    print("\n✅ 완료! 폴더 구조:")
    for mood in moods:
        folder = ASSETS_DIR / mood
        files = list(folder.glob("*.mp3")) if folder.exists() else []
        print(f"  assets/bgm/{mood}/ — {len(files)}개")


if __name__ == "__main__":
    main()
