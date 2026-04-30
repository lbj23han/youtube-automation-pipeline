#!/usr/bin/env python3
"""
일본 시니어 생애 이야기 YouTube 자동화 파이프라인 — 롱폼 전용
사용법: python run_pipeline.py --script script.txt
"""
from PIL import Image
import json
import os, sys, re, asyncio, subprocess, pickle, datetime, time, textwrap, io, struct
import urllib.request, urllib.parse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config.env")

# ══════════════════════════════════════════════════════════════════════════════
# 경로
# ══════════════════════════════════════════════════════════════════════════════
OUTPUT_DIR     = Path("output")
THUMBNAILS_DIR = OUTPUT_DIR / "thumbnails"
SCENES_DIR     = OUTPUT_DIR / "scenes"
AUDIO_DIR      = OUTPUT_DIR / "audio"
FINAL_DIR      = OUTPUT_DIR / "final"
SUBTITLES_DIR  = OUTPUT_DIR / "subtitles"
ASSETS_DIR     = Path("assets")
YOUTUBE_CLIENT_SECRETS = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")

# ══════════════════════════════════════════════════════════════════════════════
# 면책조항 — "실화 기반 재구성 + AI 보조" 프레이밍
# ══════════════════════════════════════════════════════════════════════════════
STORY_NOTICE_JP = (
    "この物語は、視聴者の方々から寄せられた実体験をもとに、"
    "プライバシー保護のため人物名・地名・時代背景等を変更し再構成しています。"
)
AI_ASSIST_NOTICE_JP = (
    "ナレーション・映像の制作にAI技術を活用しています。"
)
RECONSTRUCTION_NOTICE_JP = (
    "※ 本作品は実体験をもとに再構成・脚色した物語です"
)
WATERMARK_TEXT = "※実体験をもとに再構成"

# ══════════════════════════════════════════════════════════════════════════════
# 콘텐츠 안전성 블랙리스트
# ══════════════════════════════════════════════════════════════════════════════
KEYWORD_BLACKLIST = [
    "岸田", "安倍", "菅", "麻生", "小池", "橋下", "鳩山",
    "バイデン", "トランプ", "プーチン", "習近平",
    "天皇", "皇室", "皇后", "皇太子",
    "自殺", "自死", "死にたい", "殺してやる", "爆弾", "テロ",
    "麻薬", "覚醒剤", "大麻", "ヘロイン",
    r"\d+番地", r"\d+丁目\d+番",
]

# ══════════════════════════════════════════════════════════════════════════════
# 이미지 프롬프트 상수 (Pollinations Flux용)
# ══════════════════════════════════════════════════════════════════════════════
STYLE_BASE = (
    "elderly Japanese person, Showa era Japan 1960s-1980s, "
    "highly detailed oil painting, sharp focus, vivid warm colors, "
    "dramatic cinematic lighting, fictional character, not a real person, "
    "expressive emotional face, masterpiece quality, 8k resolution"
)

# ── 이미지 스타일 템플릿 ───────────────────────────────────────────────────────
IMAGE_STYLES = {
    "watercolor": (
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
    ),
    "realistic": (
        "cinematic film still, photorealistic, {scene}, "
        "natural skin texture, correct human anatomy, "
        "realistic face with proper eyes symmetrical pupils natural iris, "
        "correct hand anatomy five fingers per hand natural finger length, "
        "soft dramatic lighting, shallow depth of field, sharp focus, "
        "Showa era Japan 1980s-1990s setting, warm film grain, 4k quality, "
        "no text, no watermarks, no logos"
    ),
    "pencil": (
        "pencil sketch illustration, soft graphite hatching texture, "
        "warm sepia tones, hand-drawn feel, delicate linework, "
        "no photorealism, artistic sketch style"
    ),
    "anime_film": (
        "soft digital painting, illustrated drama, painterly art style, "
        "{scene}, "
        "warm painterly shading, expressive illustrated face, clear gentle eyes, "
        "modest clothing, long skirt or trousers, fully covered legs, conservative dress, "
        "wide shot showing full figures and environment, small figures in scene, "
        "warm soft lighting, detailed brushwork, "
        "traditional Japanese setting, quiet emotional atmosphere, "
        "no text, no watermark, no Japanese text, no kanji"
    ),
}
NEGATIVE_PROMPT_TEXT = (
    # 손/팔/다리 변형
    "deformed hands, extra fingers, missing fingers, fused fingers, too many fingers, "
    "malformed hands, broken fingers, twisted fingers, clawed hands, melted hands, "
    "extra limbs, missing limbs, floating limbs, disconnected body parts, "
    "extra legs, three legs, four legs, extra arms, three arms, duplicate limbs, "
    "extra hands, three hands, wrong number of limbs, multiple legs, "
    "bad anatomy, wrong anatomy, mutated body, disfigured, deformed, "
    # 얼굴/눈
    "distorted face, melted face, asymmetrical eyes, crossed eyes, lazy eye, "
    "extra eyes, missing eyes, wrong eye direction, wall eyes, uneven eyes, "
    "heterochromia, dead eyes, shiny eyes, "
    "distorted nose, distorted mouth, extra mouth, duplicate face, "
    "uncanny valley, zombie face, corpse face, horror face, "
    # 전반적 품질
    "blurry, out of focus, low quality, jpeg artifacts, pixelated, "
    "watermark, text in image, signature, username, "
    # 선정성 방지
    "bare legs, exposed legs, short skirt, miniskirt, shorts, "
    "revealing clothing, low neckline, cleavage, tight clothes, "
    "sexy pose, suggestive pose, seductive, lingerie, "
    # 스타일 충돌
    "3d render, cgi, nsfw, nude, violence, gore"
)
THUMBNAIL_EXTRA = (
    "close-up dramatic portrait, intense emotional expression, "
    "high contrast, cinematic composition, eye-catching, vivid colors, "
    "professional illustration quality, strong visual impact"
)

# ══════════════════════════════════════════════════════════════════════════════
# video_config.json 로드 — 영상마다 바뀌는 설정은 전부 여기서
# ══════════════════════════════════════════════════════════════════════════════
def _load_video_config():
    import json as _j
    p = Path("video_config.json")
    if not p.exists():
        return {}
    try:
        return _j.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️  video_config.json 파싱 실패: {e}")
        return {}

_VC = _load_video_config()
_tts = _VC.get("tts", {})
_bgm = _VC.get("bgm", {})
_img = _VC.get("image", {})

SCENE_CHARACTER_BASE = _img.get("character_base", "")
CHARACTERS = _img.get("characters", {})
STYLE_SUFFIX = _img.get("style_suffix", "")

# 캐릭터별 고정 시드 오프셋 (조합별 일관성)
_CHAR_SEED = {name: abs(hash(name)) % 50000 for name in CHARACTERS}

def _expand_char_tokens(prompt: str) -> tuple[str, int]:
    """프롬프트 내 {character} 토큰을 캐릭터 묘사로 치환.
    반환: (치환된 프롬프트, 캐릭터 조합 기반 시드 오프셋)
    """
    seed_offset = 0
    for name, desc in CHARACTERS.items():
        token = "{" + name + "}"
        if token in prompt:
            prompt = prompt.replace(token, desc)
            seed_offset += _CHAR_SEED.get(name, 0)
    return prompt, seed_offset
TTS_ENGINE       = _tts.get("engine", "edge")
TTS_VOICE        = _tts.get("speaker_id", _tts.get("voicevox_id", 13))
TTS_SPEED        = _tts.get("speed_scale", _tts.get("speed", 1.0))
TTS_PITCH_VVOX   = _tts.get("pitch_scale", _tts.get("pitch_vvox", 0.0))
TTS_VOICE_EDGE   = _tts.get("voice", "ja-JP-KeitaNeural")
TTS_RATE         = _tts.get("rate", "-8%")
TTS_PITCH        = _tts.get("pitch", "+0Hz")
TTS_CHUNK_LIMIT  = _tts.get("chunk_limit", 500)
BGM_VOLUME       = _bgm.get("volume", float(os.getenv("BGM_VOLUME", "0.25")))
BGM_CROSSFADE    = _bgm.get("crossfade", 3.0)
_bgm_zones_raw   = _bgm.get("zones", None)
BGM_ZONES        = [(z["end_sec"], z["mood"]) for z in _bgm_zones_raw] if _bgm_zones_raw else None
IMAGE_STYLE      = _img.get("style", "watercolor")

# 무드별 BGM pool — Kevin MacLeod CC BY 4.0 (incompetech.com)
# 매 실행마다 무드별로 랜덤 1곡 선택 → 영상마다 다른 BGM
# 무드: calm(평온), sad(슬픔), hopeful(희망), nostalgic(그리움), tense(긴장), warm(따뜻함)
BGM_POOL = {
    "calm":      ["Gymnopedie%20No%201"],    # 사티 짐노페디 1번 — 조용하고 담담
    "nostalgic": ["Canon%20in%20D%20Major"], # 캐논 — 따뜻한 그리움
    "sad":       ["Sad%20Trio"],             # 슬픈 트리오 — 잔잔한 슬픔
    "tense":     ["Anxiety"],                # 불안/긴장
    "hopeful":   ["Inspired"],               # 밝고 희망적인 피아노
    "warm":      ["Carefree"],               # 가볍고 따뜻한 일상감
    "healing":   ["Touching%20Moments%20One%20-%20Pulse"],  # 치유, 감동
    "dramatic":  ["Crossing%20the%20Chasm"], # 드라마틱, 충격
    "funny":     ["Sneaky%20Snitch"],        # 유쾌하고 코믹한 상황
}
_BGM_BASE   = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
_DOVA_BASE  = "https://dova-s.jp/_download/bgm/download1.php?id="

# 무드 키워드 (일본어) — 점수 높은 무드로 분류
MOOD_KEYWORDS = {
    "sad": [
        "涙", "悲し", "寂し", "泣", "諦め", "傷つ", "空っぽ", "重い", "つら",
        "痛", "血の気", "こわ", "苦し", "暗い", "消え", "冷た", "ひどく", "震え"
    ],
    "nostalgic": [
        "昔", "思い出", "あのころ", "若いころ", "ずっと前", "懐か", "あの人",
        "当時", "かつて", "記憶", "残って", "変わらない", "戻れない", "写真"
    ],
    "tense": [
        "怒", "刺", "壁", "こわい", "気まず", "ひそひそ", "空気が変わ",
        "言えない", "逃げ", "緊張", "睨", "鋭", "冷たい視線", "固まった"
    ],
    "hopeful": [
        "笑", "ありがた", "信じ", "大丈夫", "感謝", "やわら", "やっと",
        "十分", "これから", "やさし", "温か", "明る", "始まる", "ちゃんと"
    ],
    "warm": [
        "やさしく", "ほっ", "安心", "ぬくもり", "抱きしめ", "一緒", "そばに",
        "愛", "嬉し", "幸せ", "心地", "穏やか", "ほほえ", "ありがとう",
        "公園", "ベンチ", "ハンカチ", "待つ", "余白", "春", "陽だまり",
        "会いに", "また来", "静かな時間", "ゆっくり", "歩く",
    ],
    # 일본 스타일 무드
    "japanese": [
        "桜", "花びら", "春風", "和", "着物", "畳", "縁側", "茶道",
        "昔ながら", "故郷", "ふるさと", "日本", "四季", "梅", "紅葉",
    ],
    "wagashi": [
        "喫茶", "珈琲", "コーヒー", "カップ", "喫茶店", "昭和", "レトロ",
        "窓際", "午後", "静かな", "湯のみ", "お茶", "縁側", "ゆっくり",
    ],
    "nihon": [
        "誇り", "感動", "日本人", "大切", "受け継", "伝統", "絆", "魂",
        "故郷を離れ", "この国", "育てた", "守る", "命をかけ",
    ],
}
VIDEO_FPS        = 30
SECS_PER_SCENE   = _img.get("scene_duration", 17)  # 씬당 초 (기본 17초)


# ══════════════════════════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════════════════════════
def print_step(n, total, msg):
    print(f"\n{'─'*60}\n[{n}/{total}] {msg}\n{'─'*60}")

def print_ok(msg):   print(f"  ✅ {msg}")
def print_warn(msg): print(f"  ⚠️  {msg}")
def print_error(msg): print(f"\n❌ 오류: {msg}", file=sys.stderr)

def _download_file(url, dest):
    """SSL 우회 다운로드 헬퍼"""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        data = resp.read()
    if len(data) < 50_000:
        raise ValueError(f"파일이 너무 작음: {len(data)}bytes")
    Path(dest).write_bytes(data)


def _bgm_url(name: str) -> str:
    """BGM 이름 → 다운로드 URL. dova:ID 형식이면 DOVA-SYNDROME, 아니면 incompetech."""
    if name.startswith("dova:"):
        return _DOVA_BASE + name[5:]
    return _BGM_BASE + name + ".mp3"


def download_bgm_tracks():
    """무드별 BGM pool에서 랜덤 1곡씩 선택 후 다운로드 — 매 영상마다 다른 곡"""
    import random
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for mood, names in BGM_POOL.items():
        dest = ASSETS_DIR / f"bgm_{mood}.mp3"
        if dest.exists():
            print(f"  BGM [{mood}] 캐시 사용")
            continue
        random.shuffle(names)
        downloaded = False
        for name in names:
            url = _bgm_url(name)
            label = name[5:] if name.startswith("dova:") else name
            print(f"  BGM [{mood}] {label}...", end=" ", flush=True)
            try:
                _download_file(url, dest)
                print("완료")
                downloaded = True
                break
            except Exception as e:
                print_warn(f"실패({e}), 다음 후보 시도")
        if not downloaded:
            print_warn(f"BGM [{mood}] 모든 후보 실패 — 해당 구간 BGM 없음")


def classify_chapter_mood(body):
    """키워드 빈도로 챕터 무드 분류 → 6종 중 하나"""
    scores = {mood: sum(body.count(kw) for kw in kws)
              for mood, kws in MOOD_KEYWORDS.items()}
    best_mood = max(scores, key=scores.get)
    if scores[best_mood] >= 2:
        return best_mood
    return "calm"  # 키워드 부족 시 기본값


def _bgm_file_for_mood(mood: str) -> str | None:
    """무드별 BGM 파일 반환. assets/bgm/{mood}/ 폴더 우선, 없으면 assets/bgm_{mood}.mp3"""
    import random as _rand
    folder = ASSETS_DIR / "bgm" / mood
    if folder.exists():
        files = list(folder.glob("*.mp3"))
        if files:
            return str(_rand.choice(files))
    # 폴백: 단일 파일
    p = ASSETS_DIR / f"bgm_{mood}.mp3"
    if p.exists():
        return str(p)
    # 최후 폴백: calm
    for fallback in ["calm", "healing", "warm"]:
        fp = ASSETS_DIR / "bgm" / fallback
        if fp.exists():
            candidates = list(fp.glob("*.mp3"))
            if candidates:
                return str(_rand.choice(candidates))
        fp2 = ASSETS_DIR / f"bgm_{fallback}.mp3"
        if fp2.exists():
            return str(fp2)
    return None


def _get_scene_zone_list(audio_dur: float):
    """scene_prompts.json의 mood 필드로 씬별 BGM 존 목록 생성. 없으면 None."""
    import json as _j
    p = Path("scene_prompts.json")
    if not p.exists():
        return None
    data = _j.loads(p.read_text(encoding="utf-8"))
    moods = [d.get("mood", "calm") for d in data if isinstance(d, dict) and d.get("mood")]
    if not moods:
        return None
    # 씬 개수에 맞게 자동 분배
    total_clips = len(moods)
    scene_dur   = audio_dur / total_clips
    return [(scene_dur, m) for m in moods]


def build_composite_bgm(chapters, audio_dur):
    """BGM_ZONES(시간 기반) → scene_prompts 무드 → 챕터 무드 순서로 BGM 합성"""
    out = AUDIO_DIR / "bgm_composite.mp3"
    cf = BGM_CROSSFADE

    def bgm_file(mood):
        return _bgm_file_for_mood(mood)

    # ── 구간/무드 목록 결정 (우선순위: BGM_ZONES > scene_prompts.json > 챕터) ──
    if BGM_ZONES:
        # 시간 기반 존 모드
        zone_list = []
        prev = 0.0
        for end_sec, mood in BGM_ZONES:
            actual_end = min(float(end_sec), audio_dur)
            dur = actual_end - prev
            if dur > 0.5:
                zone_list.append((dur, mood))
            prev = actual_end
            if actual_end >= audio_dur:
                break
        moods = [m for _, m in zone_list]
        durs  = [d for d, _ in zone_list]
        print(f"  BGM 존: {' '.join(f'{m}({d:.0f}s)' for d, m in zone_list)}")
    elif (scene_zones := _get_scene_zone_list(audio_dur)):
        # scene_prompts.json 씬별 무드 모드
        moods = [m for _, m in scene_zones]
        durs  = [d for d, _ in scene_zones]
        print(f"  씬별 BGM: {' '.join(moods)}")
    else:
        # 챕터 기반 모드 (기존)
        scene_dur = audio_dur / len(chapters)
        moods = [classify_chapter_mood(c["body"]) for c in chapters]
        durs  = [scene_dur] * len(chapters)
        mood_str = " ".join(f"{c['title'][:6]}:{m}" for c, m in zip(chapters, moods))
        print(f"  챕터 무드: {mood_str}")

    # ── 입력 파일 등록 (무드별 1개씩 — 새 6무드 + 레거시 무드 포함) ────────────
    ALL_MOODS = ["healing", "calm", "warm", "hopeful", "sad", "dramatic",
                 "nostalgic", "tense", "japanese", "wagashi", "nihon"]
    inputs_cmd = []
    offset_map = {}
    mood_idx = {}
    idx = 0
    for mood in ALL_MOODS:
        f = bgm_file(mood)
        if f:
            inputs_cmd += ["-stream_loop", "-1", "-i", f]
            mood_idx[mood] = idx
            offset_map[mood] = 0.0
            idx += 1

    if not mood_idx:
        print_warn("BGM 파일 없음 — BGM 건너뜀")
        return None

    # ── 구간별 FFmpeg filter 생성 ─────────────────────────────────────────────
    filters = []
    seg_labels = []
    for i, (dur, mood) in enumerate(zip(durs, moods)):
        m = mood if mood in mood_idx else "calm"
        if m not in mood_idx:
            m = next(iter(mood_idx))
        src_idx = mood_idx[m]
        start = offset_map.get(m, 0.0)
        offset_map[m] = start + dur
        label = f"seg{i}"
        filters.append(
            f"[{src_idx}:a]atrim=start={start:.3f}:duration={dur:.3f},"
            f"asetpts=PTS-STARTPTS[{label}]"
        )
        seg_labels.append(f"[{label}]")

    # ── 크로스페이드 연결 ─────────────────────────────────────────────────────
    if len(seg_labels) == 1:
        filters.append(f"{seg_labels[0]}volume={BGM_VOLUME}[bgm_out]")
    else:
        prev = seg_labels[0]
        for i in range(1, len(seg_labels)):
            nxt = seg_labels[i]
            out_label = f"cf{i}"
            filters.append(
                f"{prev}{nxt}acrossfade=d={cf:.1f}:c1=tri:c2=tri[{out_label}]"
            )
            prev = f"[{out_label}]"
        filters.append(f"{prev}volume={BGM_VOLUME}[bgm_out]")

    cmd = [
        "ffmpeg", "-y",
        *inputs_cmd,
        "-filter_complex", "; ".join(filters),
        "-map", "[bgm_out]",
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print_warn("BGM 합성 실패 — 단일 BGM으로 대체")
        for line in result.stderr.splitlines()[-5:]: print(f"  {line}")
        return bgm_file("calm")
    print_ok(f"BGM 합성 완료: {len(moods)}개 구간")
    return str(out)


def ensure_dirs():
    for d in [THUMBNAILS_DIR, SCENES_DIR, AUDIO_DIR, FINAL_DIR, SUBTITLES_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def load_script(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print_error(f"스크립트 파일 없음: {path}"); sys.exit(1)

def load_metadata():
    """metadata.json 우선, 없으면 metadata.txt 폴백"""
    import json as _json
    json_path = Path("metadata.json")
    if json_path.exists():
        data = _json.loads(json_path.read_text(encoding="utf-8"))
        # channel_id / region / category_id 는 metadata.txt 에서 보완
        txt_path = Path("metadata.txt")
        if txt_path.exists():
            for line in txt_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                key, _, val = line.partition("=")
                k = key.strip().lower()
                if k not in data:
                    data[k] = val.strip()
        return data
    try:
        meta = {}
        for line in Path("metadata.txt").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            key, _, val = line.partition("=")
            meta[key.strip().lower()] = val.strip()
        return meta
    except FileNotFoundError:
        print_error("metadata.txt 없음"); sys.exit(1)

FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"  # libass 포함 빌드

def check_ffmpeg():
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        print_error("FFmpeg 미설치 → brew install ffmpeg"); sys.exit(1)

def get_audio_duration(path):
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 300.0

def find_japanese_font():
    for p in [
        "assets/fonts/NotoSansJP-Bold.otf",
        "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/Library/Fonts/NotoSansJP-Bold.otf",
        "/System/Library/Fonts/Arial Unicode.ttf",
    ]:
        if Path(p).exists(): return p
    return "assets/fonts/NotoSansJP-Bold.otf"


# ══════════════════════════════════════════════════════════════════════════════
# 안전성 검사
# ══════════════════════════════════════════════════════════════════════════════
def check_script_safety(script):
    found = [w for w in KEYWORD_BLACKLIST if re.search(w, script)]
    if found:
        print_error(f"금지 키워드 포함: {', '.join(found)}")
        print("  실재 인물명 / 유해 콘텐츠 / 구체적 주소 제거 후 재시도")
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# 챕터 파싱
# ══════════════════════════════════════════════════════════════════════════════
def parse_chapters(script):
    """
    【HOOK】 섹션 (선택) + 【第X章：タイトル】 또는 ━━━ 구분자로 챕터 분리.
    【HOOK】 섹션이 있으면 첫 챕터로 삽입 (title="HOOK").
    """
    # ── HOOK 섹션 추출 ──────────────────────────────────────────────
    hook_body = None
    hook_match = re.search(r'【HOOK】\s*\n(.*?)(?=\n━|【第|\Z)', script, re.DOTALL)
    if hook_match:
        hook_body = hook_match.group(1).strip()
        # HOOK 섹션을 스크립트에서 제거 후 나머지 파싱
        script = script[:hook_match.start()] + script[hook_match.end():]

    # ── 챕터 헤더 패턴 ──────────────────────────────────────────────
    chapter_pattern = r'【第[一二三四五六七八九十百\d]+章[：:][^】]*】'
    headers = re.findall(chapter_pattern, script)
    parts   = re.split(chapter_pattern, script)

    if len(headers) >= 2:
        chapters = []
        for i, body in enumerate(parts[1:], 1):
            title = headers[i-1].strip("【】") if i <= len(headers) else f"第{i}章"
            chapters.append({"title": title, "body": body.strip()})
    else:
        # ━━━ 구분자
        sections = re.split(r'[━─―\-]{5,}', script)
        sections = [s.strip() for s in sections if len(s.strip()) > 50]
        chapters = [{"title": f"第{i+1}章", "body": s} for i, s in enumerate(sections)]

    # HOOK 챕터를 맨 앞에 삽입
    if hook_body:
        chapters.insert(0, {"title": "HOOK", "body": hook_body})
        print_ok("HOOK 섹션 감지 → 영상 첫 장면으로 배치")

    return chapters

    # 최후 수단: 글자 수 기준 균등 분할 (약 1000자씩)
    chunk_size = 1000
    chunks = [script[i:i+chunk_size] for i in range(0, len(script), chunk_size)]
    return [{"title": f"第{i+1}章", "body": c} for i, c in enumerate(chunks)]


# ══════════════════════════════════════════════════════════════════════════════
# 키워드 추출
# ══════════════════════════════════════════════════════════════════════════════
def extract_keywords(text, n=5):
    words = re.findall(r'[一-龯々]{2,}|[ぁ-ん]{3,}|[ァ-ン]{2,}', text)
    stopwords = {"という","について","それから","しかし","そして","ために",
                 "ました","です","ます","ある","いる","なる","する","いた",
                 "きた","から","まで","より","など","ところ","こと","もの",
                 "とき","ため","よう","自分","時代","気持","思い","言葉",
                 "人生","ありがとう","という","られ"}
    words = [w for w in words if w not in stopwords]
    freq = {}
    for w in words: freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=lambda x: -freq[x])[:n]


# ══════════════════════════════════════════════════════════════════════════════
# 어그로 카피 생성
# ══════════════════════════════════════════════════════════════════════════════
def generate_hook_text(script, title):
    """스크립트 감정 피크 → 클릭 유도 카피"""
    candidates = re.findall(r'「([^」]{8,25})」', script)
    emotion_words = ["涙","泣","後悔","気づ","知らなか","言えなかった","ありがとう",
                     "最後","遺","残","秘密","本当は","ごめん","許"]
    def score(s): return sum(1 for w in emotion_words if w in s)
    candidates = sorted(set(candidates), key=score, reverse=True)

    prefixes = ["【号泣】","【感動実話】","【涙腺崩壊】","【実話】"]
    suffixes = ["...に涙が止まらない","...衝撃の告白","...最後の言葉",""]

    if candidates:
        best   = candidates[0][:20]
        prefix = prefixes[hash(title) % len(prefixes)]
        suffix = suffixes[hash(script[:30]) % len(suffixes)]
        return f"{prefix}「{best}」{suffix}"
    return f"【感動実話】{title[:22]}"


# ══════════════════════════════════════════════════════════════════════════════
# 챕터별 맞춤 씬 프롬프트 시스템
# ══════════════════════════════════════════════════════════════════════════════

# 등장인물 고정 묘사
PROTAGONIST = (
    "an elderly Japanese woman in her late 70s, neat white hair in a small bun, "
    "dark navy cardigan over a cream blouse, small pearl earrings, "
    "kind weathered face with delicate wrinkles, slender small frame"
)
_KENJI = (
    "a Japanese man in his late 20s, short black hair, wearing a dark jacket, "
    "lean athletic build, casual confident posture"
)
_MIKA = (
    "a young Japanese woman in her early 20s, fashionably styled wavy hair, "
    "bright trendy clothing, always holding a smartphone"
)
_SHIBATA = (
    "an elderly Japanese man in his late 70s, grey hair, "
    "simple dark traditional clothing, calm dignified expression"
)
_OWNER = (
    "a middle-aged Japanese man in his late 40s, short neat hair, "
    "wearing a white café apron, tired but kind face"
)
_CAFÉ = (
    "small intimate 1980s Japanese café, warm wooden interior, "
    "large window with soft morning street view, ceramic cups, wooden tables"
)

_STYLE = (
    "cinematic film still, highly detailed oil painting style, "
    "sharp focus, rich warm color palette, dramatic professional lighting, "
    "1980s Japan aesthetic, no text, no watermarks, masterpiece quality, 8k"
)

# 챕터별 1:1 대응 씬 프롬프트 (스크립트 플롯 직접 반영)
CHAPTER_SCENE_PROMPTS = [
    # 01 春の光が入る席 — 春子의 아침 루틴, 조용한 일상
    {
        "label": "일상/도입",
        "seed_anchor": True,
        "prompt": (
            f"wide cinematic shot, {_CAFÉ} at 7am, "
            f"{PROTAGONIST} walking slowly toward the window seat, "
            "morning light streaming through the large window, "
            "the seat empty and waiting for her, café owner watching warmly from behind the counter, "
            f"peaceful ritual, {_STYLE}"
        ),
    },
    # 02 若い笑い声 — 젊은 커플이 자리 차지, 봄자의 당혹감
    {
        "label": "갈등/자리빼앗김",
        "seed_anchor": True,
        "prompt": (
            f"cinematic wide shot of {_CAFÉ}, "
            f"foreground LEFT: {PROTAGONIST} stopped mid-step, hand slightly raised, expression of quiet shock and hurt, "
            "foreground RIGHT: a young couple in their 20s dropping their bags onto the window seat, "
            "laughing loudly, one of them immediately taking a selfie, "
            "they don't notice the elderly woman at all — the contrast is painful, "
            f"dramatic side lighting divides the frame, {_STYLE}"
        ),
    },
    # 03 その席に座る理由 — 남편과의 회상
    {
        "label": "회상/남편",
        "seed_anchor": False,
        "prompt": (
            f"soft sepia-toned memory scene: a young Japanese couple in their 30s "
            f"sitting together at a café window table in the 1960s, "
            "the woman laughing brightly, the man watching her with quiet deep adoration, "
            "warm afternoon light through the window, "
            "dreamy nostalgic soft focus at the edges — a precious memory frozen in time, "
            f"no modern elements, {_STYLE}"
        ),
    },
    # 04 ケンジという男 — 케이지의 무신경한 말
    {
        "label": "갈등/케이지",
        "seed_anchor": True,
        "prompt": (
            f"medium shot inside {_CAFÉ}, "
            f"LEFT: {_KENJI} sitting sprawled at the window seat, one arm over the backrest, "
            "smirking slightly, phone on the table, casual dismissive posture, "
            f"RIGHT: {PROTAGONIST} standing in the aisle nearby, "
            "expression showing quiet pain at his careless words, "
            "she is trying to smile but cannot hide the hurt, "
            f"uncomfortable tension between them, {_STYLE}"
        ),
    },
    # 05 ミカの笑顔 — 미카가 할머니를 흉보며 웃는 장면
    {
        "label": "갈등/미카조롱",
        "seed_anchor": True,
        "prompt": (
            f"inside {_CAFÉ}, "
            f"FOREGROUND: {_MIKA} and her female friend at the window seat, "
            "Mika leaning toward her friend whispering something, "
            "both covering their mouths laughing, one of them glancing sideways, "
            f"BACKGROUND BLURRED: {PROTAGONIST} standing in the aisle, "
            "expression showing she has heard every word, "
            "hand trembling slightly on her coffee cup, "
            f"shallow depth of field, cruel contrast between the two groups, {_STYLE}"
        ),
    },
    # 06 見えない壁 — 봄자가 있는 것만으로 분위기가 이상해지는 장면
    {
        "label": "고립/보이지않는벽",
        "seed_anchor": True,
        "prompt": (
            f"wide shot of {_CAFÉ}, "
            f"{PROTAGONIST} just inside the entrance, looking toward the window seat, "
            "young customers at the window seat deliberately avoiding eye contact, "
            "one person conspicuously looking at their phone, another turning away, "
            "the social barrier is invisible but the body language makes it visible, "
            f"cold geometric composition, the elderly woman isolated in her own frame, {_STYLE}"
        ),
    },
    # 07 小さな動画 — 미카가 몰래 촬영하는 장면
    {
        "label": "갈등/촬영",
        "seed_anchor": True,
        "prompt": (
            f"inside {_CAFÉ}, "
            f"FOREGROUND: {_MIKA} at the window seat, holding smartphone sideways, "
            "secretly filming, a sly amused expression on her face, "
            f"BACKGROUND: {PROTAGONIST} walking slowly toward her usual seat, "
            "completely unaware she is being filmed, "
            "the malice in Mika's expression contrasted with the elderly woman's oblivious dignity, "
            f"uncomfortable voyeuristic angle, {_STYLE}"
        ),
    },
    # 08 来なくなった朝 — 봄자가 집에 혼자 앉아있는 장면
    {
        "label": "슬픔/외출못함",
        "seed_anchor": True,
        "prompt": (
            f"{PROTAGONIST} alone in her small dim Japanese home, "
            "sitting in a chair by a window with curtains barely open, "
            "morning light outside — beautiful and unreachable, "
            "she is dressed as if ready to go out, but cannot move, "
            "an old photograph resting on her lap, face showing numb quiet grief, "
            f"single lamp light, deep shadows, the weight of absence, {_STYLE}"
        ),
    },
    # 09 残された違和感 — 가게 주인과 케이지가 사진을 발견
    {
        "label": "발견/사진",
        "seed_anchor": False,
        "prompt": (
            f"inside {_CAFÉ}, behind the counter, "
            f"{_OWNER} holding an old framed photograph, "
            f"{_KENJI} leaning over to look at it, both men frozen, "
            "the photograph shows the window seat — with a young couple smiling "
            "and the elderly man who built the café, "
            "expressions of slow horrified realization on both their faces, "
            f"low dramatic lighting, dust motes in the air, {_STYLE}"
        ),
    },
    # 10 昔の約束 — 柴田 노인이 이야기를 털어놓는 장면
    {
        "label": "계시/시바타이야기",
        "seed_anchor": False,
        "prompt": (
            f"inside {_CAFÉ}, three people gathered — "
            f"{_SHIBATA} sitting at a table, speaking with slow deliberate gravity, "
            f"{_OWNER} standing behind the counter gripping the edge, face pale, "
            f"{_KENJI} sitting across, staring down in shame, "
            "the window seat visible and empty in the background, "
            "early morning light, the truth settling like weight in the room, "
            f"three-person dramatic composition, {_STYLE}"
        ),
    },
    # 11 ミカの軽さ — 미카가 시바타에게 직면당하는 장면
    {
        "label": "갈등/미카직면",
        "seed_anchor": False,
        "prompt": (
            f"dramatic confrontation inside {_CAFÉ}, "
            f"LEFT: {_MIKA} caught mid-step toward the window seat, "
            "phone in hand, face shifting from casual to defensive to shocked, "
            f"RIGHT: {_SHIBATA} seated, not shouting, but his quiet words cut like steel, "
            "pointing slowly toward the empty window seat, "
            f"BACKGROUND: {_OWNER} watching with hard disappointed eyes, "
            "the moment Mika understands the real consequence of what she did, "
            f"confrontational framing, high emotional tension, {_STYLE}"
        ),
    },
    # 12 ケンジの沈黙 — 케이지가 빈 자리를 바라보며 죄책감
    {
        "label": "회한/케이지",
        "seed_anchor": True,
        "prompt": (
            f"inside {_CAFÉ}, {_KENJI} sitting alone at a table far from the window, "
            "staring at the empty window seat, "
            "his posture collapsed forward, elbows on knees, face in his hands — guilt, "
            "the window seat is lit by morning sun, beautiful and accusatory, "
            "other customers moving around him but he is utterly alone in his remorse, "
            f"cinematic melancholy, {_STYLE}"
        ),
    },
    # 13 訪ねるべき家 — 가게 주인이 봄자의 집을 찾아가는 장면
    {
        "label": "방문/사과",
        "seed_anchor": False,
        "prompt": (
            f"exterior shot: {_OWNER} standing at the front gate of a small quiet Japanese house, "
            "small potted plants by the entrance, clean but modest, "
            "he holds his cap in both hands, head already beginning to bow, "
            "the door is closed — he has not yet knocked — "
            "the weight of what he needs to say visible in his entire body, "
            f"early morning, quiet neighborhood street, {_STYLE}"
        ),
    },
    # 14 言えなかったこと — 봄자의 문에서 마주침
    {
        "label": "화해/대면",
        "seed_anchor": True,
        "prompt": (
            f"at the front door of a modest Japanese home, "
            f"{_OWNER} standing outside, head bowed deeply in apology, "
            f"FACING HIM: {PROTAGONIST} at the doorway, "
            "surprise on her face giving way to something cracking open — "
            "not anger, but years of quiet hurt finally being seen, "
            "tears beginning at the corner of her eyes, "
            "morning light behind the owner silhouettes him in a moment of sincerity, "
            f"two people, a doorway, everything unsaid between them, {_STYLE}"
        ),
    },
    # 15 戻る朝、戻らないもの — 봄자가 카페 앞에서 망설이는 장면
    {
        "label": "귀환/망설임",
        "seed_anchor": True,
        "prompt": (
            f"exterior of a small 1980s Japanese café at 7am, "
            f"{PROTAGONIST} standing on the pavement just outside the entrance, "
            "hand raised but not yet touching the door handle, "
            "looking through the glass at the window seat — it is empty, lit by morning light, "
            "her expression a complex mixture of longing, fear, and quiet resolve, "
            "a moment suspended between past and forward, "
            f"back-lit by the rising sun, {_STYLE}"
        ),
    },
    # 16 ケンジの謝罪 — 케이지가 봄자에게 직접 사과
    {
        "label": "사과/화해",
        "seed_anchor": True,
        "prompt": (
            f"inside {_CAFÉ}, "
            f"{_KENJI} standing before {PROTAGONIST} who is seated at the window table, "
            "he is bowing deeply — lower than a casual bow, a real one — "
            "one hand over his chest, voice clearly emotional, "
            "the elderly woman looking up at him with tired but forgiving eyes, "
            "morning light falls gently across both of them, "
            "the window seat finally filled again with something right, "
            f"emotional two-person scene, {_STYLE}"
        ),
    },
    # 17 ミカの削除 — 미카가 혼자 동영상을 삭제하는 장면
    {
        "label": "후회/삭제",
        "seed_anchor": False,
        "prompt": (
            f"{_MIKA} alone, sitting on a bench outside, "
            "staring at her smartphone screen, "
            "the video she posted still playing in a small window, "
            "her finger hovering over delete — unable to take back the past but trying, "
            "no one around, late afternoon cold light, "
            "her fashionable clothing makes her look somehow very small and young, "
            f"tight shot on hands and face, quiet guilt, {_STYLE}"
        ),
    },
    # 18 その席が残したもの — 가게에 작은 꽃이 놓인 자리
    {
        "label": "잔향/빈자리",
        "seed_anchor": False,
        "prompt": (
            f"close-up of the window seat in {_CAFÉ}, "
            "a single small wildflower in a tiny glass vase placed on the table by someone, "
            "morning light illuminating the table, the flower, the empty seat, "
            "coffee cup ring stains on the worn wood — decades of mornings, "
            "no people, the absence is now full of meaning, "
            f"still life composition, emotional weight in every object, {_STYLE}"
        ),
    },
    # 19 誰にも見えない朝 — 봄자가 이른 아침 혼자 앉아있는 장면
    {
        "label": "새벽/혼자",
        "seed_anchor": True,
        "prompt": (
            f"very early morning, {_CAFÉ} is empty, not yet open, "
            f"but {PROTAGONIST} has been let in early — she sits alone at the window seat, "
            "both hands around a warm cup, looking out at the dark street slowly brightening, "
            "completely alone, completely at peace, "
            "this is hers. this has always been hers, "
            f"pre-dawn blue light transitioning to gold, deeply quiet, {_STYLE}"
        ),
    },
    # 20 その席は、もともと私のものでした — 엔딩
    {
        "label": "엔딩/귀환완성",
        "seed_anchor": True,
        "prompt": (
            f"wide cinematic shot of {_CAFÉ} in full morning light, "
            f"{PROTAGONIST} seated at the window seat — her seat — "
            "hands wrapped around a coffee cup, a small quiet smile on her face, "
            "morning light falls across her exactly as it always has, "
            "the café owner watching from behind the counter, nodding once, "
            "everything is back where it should be, "
            "the world outside the window is ordinary and beautiful, "
            f"full circle, peaceful resolution, {_STYLE}"
        ),
    },
]


def build_scene_prompt(chapter_idx, _unused_situation=None, _unused_comp=None, _unused_body=None):
    """챕터 인덱스로 직접 씬 프롬프트 반환 (키워드 추측 방식 폐기)"""
    idx = min(chapter_idx, len(CHAPTER_SCENE_PROMPTS) - 1)
    return CHAPTER_SCENE_PROMPTS[idx]["prompt"]


# ── Claude API 기반 자동 씬 프롬프트 생성 ─────────────────────────────────────
_SCENE_PROMPT_SYSTEM = """You are a cinematic scene director for a Japanese story YouTube video.

Given a chapter, output ONE image generation prompt in English.

Rules:
- Identify the KEY dramatic moment of the chapter
- Include specific character details:
  * 春子 (Haruko): elderly Japanese woman late 70s, white hair bun, navy cardigan, cream blouse, pearl earrings
  * ケンジ (Kenji): Japanese man late 20s, dark jacket, short black hair, lean build
  * ミカ (Mika): Japanese woman early 20s, wavy hair, trendy clothing, always on smartphone
  * 柴田 (Shibata): elderly man late 70s, grey hair, dark traditional clothing
  * 店長 (owner): middle-aged man 40s, white apron
- Vary compositions: wide shots for atmosphere, close-ups for emotion, multi-person for conflict
- For conflict scenes: show multiple characters with body language tension
- For memory/flashback: use sepia/golden nostalgic tones
- Setting: 1980s Japan, small intimate café with large window
- End with: cinematic film still, oil painting style, 8k, no text, no watermarks
- Output ONLY the prompt. No explanation. Max 400 characters."""


def auto_generate_scene_prompts(chapters):
    """
    Claude Haiku로 전체 챕터 자동 분석 → 씬 프롬프트 리스트 생성.
    캐싱: script 해시가 같으면 output/scene_prompts_cache.json 재사용.
    """
    import hashlib, json

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "여기에_키_입력":
        return None   # API 키 없으면 hardcoded fallback 사용

    try:
        import anthropic
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "anthropic", "-q"], check=True)
        import anthropic

    # 캐시 확인 — 동일 스크립트면 재생성 안 함
    cache_path  = OUTPUT_DIR / "scene_prompts_cache.json"
    script_hash = hashlib.md5("".join(c["title"] + c["body"] for c in chapters).encode()).hexdigest()

    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("hash") == script_hash:
            print_ok(f"씬 프롬프트 캐시 사용 ({len(cached['prompts'])}개)")
            return cached["prompts"]

    print(f"  Claude Haiku로 씬 프롬프트 자동 생성 중 ({len(chapters)}챕터)...")
    client  = anthropic.Anthropic(api_key=api_key)
    prompts = []

    for i, chap in enumerate(chapters):
        user_msg = f"Chapter {i+1}/{len(chapters)}: {chap['title']}\n\n{chap['body'][:600]}"
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=_SCENE_PROMPT_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            prompt = resp.content[0].text.strip()
        except Exception as e:
            print_warn(f"  Ch{i+1} 자동생성 실패 ({e}), fallback 사용")
            idx = min(i, len(CHAPTER_SCENE_PROMPTS) - 1)
            prompt = CHAPTER_SCENE_PROMPTS[idx]["prompt"]
        prompts.append(prompt)
        print(f"    [{i+1:02d}/{len(chapters)}] 완료")

    # 캐시 저장
    cache_path.write_text(
        json.dumps({"hash": script_hash, "prompts": prompts}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print_ok(f"씬 프롬프트 생성 완료 → 캐시 저장: {cache_path}")
    return prompts


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — 이미지 생성 (Pollinations.ai FLUX-schnell)
# ══════════════════════════════════════════════════════════════════════════════
STYLE_PREFIX = "realistic live-action Japanese TV drama still, soft cinematic lighting, "
STYLE_SUFFIX_QUALITY = "muted warm tones, no text, no watermark, no subtitle, no logo"
MULTI_PERSON_SAFETY = (
    "seen from behind, distant framing, no clear facial detail, "
    "wide establishing shot, small figures in environment"
)

_SEED_ZONES = [
    (0,   29,  1201),
    (30,  44,  2201),
    (45,  64,  3201),
    (65,  84,  4201),
    (85,  119, 5201),
]

def _get_scene_seed(scene_idx: int, char_seed: int = 0) -> int:
    base = 88888
    for start, end, zone_seed in _SEED_ZONES:
        if start <= scene_idx <= end:
            base = zone_seed
            break
    return base + (char_seed % 100)

def _is_multi_person(prompt: str) -> bool:
    p = prompt.lower()
    count = sum(1 for kw in ["fumie", "michiko", "yuko", "nurse", "young_fumie", "young_michiko"]
                if "{" + kw + "}" in prompt or kw in p)
    if count >= 2:
        return True
    for kw in ["two women", "two elderly", "both ", "together", "side by side"]:
        if kw in p:
            return True
    return False

# 요청 간격 제어 (rate limit 방지)
_POLL_MIN_INTERVAL = 16.0  # 익명 rate limit 1req/15s + 여유 1s
_last_poll_time = 0.0

def fetch_image_hf(prompt: str, width: int = 1280, height: int = 720, seed: int = 42):
    """Pollinations.ai gen API — turbo 모델"""
    import time, requests as req_lib, urllib.parse
    from PIL import Image
    global _last_poll_time

    full = f"{STYLE_PREFIX}{prompt}, {STYLE_SUFFIX_QUALITY}"
    encoded = urllib.parse.quote(full[:1000])
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?model=turbo&width={width}&height={height}&seed={seed}"
        f"&nologo=true&enhance=false"
    )

    for attempt in range(8):
        wait = _POLL_MIN_INTERVAL - (time.time() - _last_poll_time)
        if wait > 0:
            time.sleep(wait)
        try:
            _last_poll_time = time.time()
            resp = req_lib.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
            ct = resp.headers.get("content-type", "")
            if resp.status_code == 200 and "image" in ct:
                return Image.open(io.BytesIO(resp.content)).convert("RGB")
            if resp.status_code == 429:
                wait2 = 30 + attempt * 15
                print(f" [429→{wait2}s]", end="", flush=True)
                time.sleep(wait2)
            else:
                print(f" [HTTP{resp.status_code}]", end="", flush=True)
                time.sleep(15)
        except Exception as e:
            print(f" [err:{e}]", end="", flush=True)
            time.sleep(10)

    print_error(f"생성 실패(8회): {prompt[:60]}")
    return None


def add_thumbnail_text(img, main_text, badge_text="感動の実話", position="bottom"):
    """
    고CTR 썸네일 텍스트 오버레이.
    position: "bottom" | "center" | "top"
    - 이미지 전체 유지 (그라디언트 없음)
    - 메인 카피 대형 + 두꺼운 스트로크
    - 하단 빨간 배지
    """
    from PIL import Image, ImageDraw, ImageFont
    if not main_text:
        return img

    img  = img.copy().convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    font_path = find_japanese_font()
    try:
        f_main  = ImageFont.truetype(font_path, 130)
        f_badge = ImageFont.truetype(font_path, 44)
    except Exception:
        f_main = f_badge = ImageFont.load_default()

    # 「」 안 텍스트만 추출
    inner = re.search(r'「(.+?)」', main_text)
    display = inner.group(1) if inner else main_text

    margin    = 52
    line_h    = 148
    max_chars = 8

    lines = []
    while display:
        lines.append(display[:max_chars])
        display = display[max_chars:]

    total_text_h = len(lines) * line_h

    # position별 y 기준점
    if position == "center":
        y_start = (h - total_text_h) // 2
    elif position == "top":
        y_start = 60
    else:  # bottom
        y_start = h - total_text_h - 80

    # ── 메인 텍스트 ─────────────────────────────────────────────────────────────
    stroke = 7
    for line in lines:
        for dx in range(-stroke, stroke + 1):
            for dy in range(-stroke, stroke + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((margin + dx, y_start + dy), line,
                          font=f_main, fill=(0, 0, 0, 255))
        draw.text((margin, y_start), line, font=f_main, fill=(255, 235, 28))
        y_start += line_h

    # ── 하단 빨간 배지 ────────────────────────────────────────────────────────
    badge_x1 = margin
    badge_y1 = h - 58
    try:
        bw = int(draw.textlength(badge_text, font=f_badge)) + 32
    except Exception:
        bw = 240
    draw.rectangle([(badge_x1, badge_y1), (badge_x1 + bw, h - 10)],
                   fill=(210, 20, 20, 255))
    draw.text((badge_x1 + 14, badge_y1 + 6), badge_text,
              font=f_badge, fill=(255, 255, 255, 255))

    return img.convert("RGB")


def _make_thumbnail_texts(title: str) -> list:
    """
    일본 시니어 채널 고CTR 공식:
      1번 → 「なぜ〜」 패턴  (이유/의문 → 클릭 유발)
      2번 → 「あの日〜」 패턴 (특정 날 → 공감 유발)
      3번 → 「最後〜」 패턴  (끝/마지막 → 감정 자극)
    타이틀 키워드에서 핵심 명사를 뽑아 동적으로 채움.
    """
    # 키워드 추출 — 타이틀에서 감성 명사 탐색
    noun_map = {
        "電話": ("電話に出なかった", "電話が鳴った日", "最後の着信"),
        "声":   ("声が届かなかった", "あの声を聞いた日", "最後に聞いた声"),
        "息子": ("息子は知らなかった", "あの日、息子が来た", "最後の言葉"),
        "母":   ("母は何も言わなかった", "あの日の母の顔", "最後に見た笑顔"),
        "娘":   ("娘は気づかなかった", "あの日、娘が泣いた", "最後の手紙"),
        "夫":   ("夫はもういない", "あの日、夫が言った", "最後の約束"),
        "席":   ("その席に座れなかった", "あの日の席の理由", "最後に見た席"),
        "手紙": ("手紙は届かなかった", "あの日の手紙", "最後の一文"),
    }
    for kw, (naze, ano, saigo) in noun_map.items():
        if kw in title:
            return [f"「なぜ、{naze}」", f"「あの日、{ano}」", f"「最後の{saigo.split('の')[-1]}」"]

    # 매칭 없으면 타이틀 앞부분 활용한 범용 패턴
    short = title[:10]
    return [
        f"「なぜ、誰も知らなかった」",
        f"「あの日から、変わった」",
        f"「最後に残ったひとこと」",
    ]


def _build_thumbnail_config(title: str) -> dict:
    """
    타이틀 기반 썸네일 텍스트(なぜ/あの日/最後 공식) + 이미지 프롬프트 생성.
    각 썸네일마다 position(텍스트 위치)도 다르게 설정.
    """
    THUMB_STYLE = (
        "cinematic close-up portrait, high contrast dramatic side lighting, "
        "sharp focus, shallow depth of field bokeh background, "
        "realistic oil painting style, 8k resolution, no text, no logos"
    )

    # video_config.json에 thumbnail.texts 있으면 우선 사용, 없으면 자동 생성
    _thumb_cfg = _VC.get("thumbnail", {})
    texts = _thumb_cfg.get("texts") or _make_thumbnail_texts(title)
    positions = _thumb_cfg.get("positions") or ["bottom", "center", "bottom"]

    # 이미지 프롬프트 — 타이틀 키워드별
    is_phone        = any(k in title for k in ["電話", "声", "息子", "母"]) and not any(k in title for k in ["ノート", "嘘", "知っていた"])
    is_seat         = any(k in title for k in ["席", "カフェ", "喫茶"])
    is_old_man      = any(k in title for k in ["老人", "職人", "技術者", "父", "祖父", "じいさん", "おじいさん", "直せた", "老職人"])
    is_handkerchief = any(k in title for k in ["ハンカチ", "公園", "ベンチ", "忘れた"])
    is_nenkin       = any(k in title for k in ["年金", "通帳", "一人暮らし", "老後の現実", "年金生活"])
    is_haha         = any(k in title for k in ["ノート", "嘘", "知っていた", "後悔", "大丈夫は"])
    is_hitori       = any(k in title for k in ["平気だと", "一人でも", "一人で生き", "孤独", "老後に"])

    if is_phone:
        prompts = [
            (
                "close-up portrait of elderly Japanese woman late 70s white hair bun dark cardigan, "
                "holding an old flip phone close, expression of quiet longing and exhausted love, "
                "single warm lamp in dark Japanese room, eyes slightly downcast, "
                f"{THUMB_STYLE}"
            ),
            (
                "close-up portrait of adult Japanese man late 30s dark jacket sitting alone at night, "
                "face illuminated only by cold blue-white phone screen light, "
                "expression of stunned irreversible regret, listening to a voicemail, "
                f"{THUMB_STYLE}"
            ),
            (
                "elderly Japanese mother late 70s white hair neat bun sitting alone at a low table, "
                "Sunday evening lamp light, old phone face-up in front of her, not ringing, "
                "her gaze distant and waiting, profound stillness, "
                f"{THUMB_STYLE}"
            ),
        ]
    elif is_seat:
        prompts = [
            (
                "close-up portrait of elderly Japanese woman late 70s white hair bun dark cardigan, "
                "eyes glistening with restrained tears, expression of quiet dignified loss, "
                "blurred 1980s Japanese café background, "
                f"{THUMB_STYLE}"
            ),
            (
                "medium shot elderly Japanese woman 1980s café, looking at window seat taken by young people, "
                "her small figure in focus, quiet resignation in her posture, "
                f"{THUMB_STYLE}"
            ),
            (
                "wide 1980s Japanese café, elderly woman left of frame staring at occupied window seat, "
                "young people right side, shaft of morning light dividing them, "
                f"{THUMB_STYLE}"
            ),
        ]
    elif is_old_man:
        prompts = [
            (
                "close-up portrait of elderly Japanese man late 70s short grey hair weathered face, "
                "worn dark work jacket, calm dignified expression with quiet hidden strength, "
                "blurred workshop interior with tools in background, dramatic side lighting, "
                f"{THUMB_STYLE}"
            ),
            (
                "elderly Japanese man late 70s grey hair crouching beside a large machine in a dimly lit factory, "
                "his hands resting on the metal surface, expression of deep familiarity and mastery, "
                "younger workers watching from behind in stunned silence, "
                f"{THUMB_STYLE}"
            ),
            (
                "close-up of weathered elderly Japanese man's face in profile, lit from one side by warm workshop lamp, "
                "eyes focused and calm, the face of a man who knows exactly what he is doing, "
                "dark background, intimate dramatic framing, "
                f"{THUMB_STYLE}"
            ),
        ]
    elif is_handkerchief:
        texts = [
            "あの日から、毎日が少し変わった",
            "公園のベンチで、もう一度春が来た",
            "あの人が、ハンカチを届けてくれた日から",
        ]
        positions = ["bottom", "center", "top"]
        prompts = [
            (
                "elderly Japanese woman late 70s and elderly Japanese man late 70s sitting on a park bench, "
                "the man gently handing a folded white handkerchief to the woman, "
                "soft spring morning light filtering through cherry blossom trees, "
                "expression of quiet surprise and warmth on her face, peaceful park background bokeh, "
                f"{THUMB_STYLE}"
            ),
            (
                "close-up portrait of elderly Japanese woman late 70s silver hair neat, "
                "sitting alone on a wooden park bench, soft warm spring sunlight on her face, "
                "eyes glistening with gentle emotion, a white folded handkerchief resting on her lap, "
                "blurred green park background, "
                f"{THUMB_STYLE}"
            ),
            (
                "elderly Japanese woman and elderly man walking slowly side by side on a quiet park path, "
                "morning light through tall trees casting long shadows, "
                "her hand near his arm, both with calm peaceful expressions, "
                "cherry blossom petals drifting gently, "
                f"{THUMB_STYLE}"
            ),
        ]
    elif is_hitori:
        texts = [
            "本当は平気じゃなかった",
            "誰にも言えない不安があった",
            "静かな老後に足りなかったもの",
        ]
        positions = ["bottom", "center", "bottom"]
        prompts = [
            (
                "close-up portrait of elderly Japanese man early 70s, sitting alone in a dimly lit Japanese room at night, "
                "single warm floor lamp casting soft side light on his face, "
                "expression of quiet endurance, exhaustion, and loneliness — not crying, just bearing it, "
                "simple sparse room, dark background, no clutter, "
                f"{THUMB_STYLE}"
            ),
            (
                "elderly Japanese man early 70s sitting at a small kitchen table alone at dusk, "
                "looking at an empty chair across from him, a simple meal in front of him untouched, "
                "warm dim interior light, profound stillness and absence, "
                "realistic Japanese apartment interior, "
                f"{THUMB_STYLE}"
            ),
            (
                "two elderly Japanese neighbors — a man and a woman — sitting quietly on a park bench, "
                "early spring light, plum blossoms softly blurred in background, "
                "calm peaceful expressions, not talking, just present together, "
                "emotional warmth and quiet companionship, "
                f"{THUMB_STYLE}"
            ),
        ]
    elif is_haha:
        texts = [
            "「大丈夫は、嘘でした」",
            "「母は、気づいていた」",
            "「あの一言が、最後でした」",
        ]
        positions = ["bottom", "center", "top"]
        prompts = [
            (
                "close-up of a small worn notebook open on a wooden table, "
                "handwritten Japanese text on yellowed pages, "
                "warm soft lamp light from the side, gentle bokeh background, "
                "intimate emotional mood, no people, no hands, "
                f"{THUMB_STYLE}"
            ),
            (
                "Japanese man in his early 40s seen from behind, sitting at a window, "
                "warm afternoon sunlight streaming in, quiet and reflective posture, "
                "simple Japanese apartment, soft natural light, peaceful melancholic mood, "
                "no dark elements, warm tones only, "
                f"{THUMB_STYLE}"
            ),
            (
                "close-up of an old photograph lying on a wooden table, "
                "faded image of a young man and an elderly woman together, "
                "soft warm side light, nostalgic and gentle atmosphere, "
                "no people in scene, no dark elements, "
                f"{THUMB_STYLE}"
            ),
        ]
    elif is_nenkin:
        texts = [
            "「これで大丈夫だと思っていた」",
            "減っているのは、お金だけじゃなかった",
            "気づけば、静かになっていた",
        ]
        positions = ["bottom", "center", "top"]
        prompts = [
            (
                "close-up portrait of elderly Japanese man late 70s sitting alone at a small wooden table, "
                "holding a worn bankbook with both hands, looking down quietly, "
                "expression of quiet resignation and reflection, soft natural side light, "
                "simple Japanese apartment interior blurred background, "
                f"{THUMB_STYLE}"
            ),
            (
                "elderly Japanese man late 70s standing at a convenience store shelf, "
                "hand reaching toward a bento box then hesitating, not picking it up, "
                "warm dim fluorescent lighting, expression of quiet hesitation, "
                "realistic Japanese convenience store background softly blurred, "
                f"{THUMB_STYLE}"
            ),
            (
                "elderly Japanese man late 70s standing by a window at sunset, "
                "warm golden light on his face, looking outside quietly, "
                "simple Japanese apartment room, expression of calm acceptance and melancholy, "
                "soft bokeh background, "
                f"{THUMB_STYLE}"
            ),
        ]
    else:
        prompts = [
            (
                "close-up portrait of elderly Japanese person late 70s, "
                "expression of quiet sadness and dignity, dramatic side lighting, "
                "realistic Japanese home interior blurred background, "
                f"{THUMB_STYLE}"
            ),
        ] * 3

    return {"texts": texts, "prompts": prompts, "positions": positions}


def generate_images(script, chapters, skip_thumbs=False):
    metadata = load_metadata()
    title    = metadata.get("title", "")
    hook     = generate_hook_text(script, title)
    print(f"  어그로 카피: {hook}")

    # ── 썸네일 3장 ────────────────────────
    if skip_thumbs:
        print(f"\n  썸네일 건너뜀 (기존 파일 재사용)")
    else:
        thumb_cfg = _build_thumbnail_config(title)
        THUMB_TEXTS   = thumb_cfg["texts"]
        _thumb_vc = _VC.get("thumbnail", {})
        thumb_prompts = _thumb_vc.get("prompts") or thumb_cfg["prompts"]
        positions = thumb_cfg.get("positions", ["bottom", "center", "bottom"])
        print(f"\n  썸네일 3장 생성 중...")
        for i, (prompt, text, pos) in enumerate(zip(thumb_prompts, THUMB_TEXTS, positions), 1):
            print(f"    [{i}/3] {text[:16]}... ({pos})", end=" ", flush=True)
            img = fetch_image_hf(prompt, 960, 544, seed=88888 + i * 111)
            img = img.resize((1920, 1080), Image.LANCZOS)
            img = add_thumbnail_text(img, text, position=pos)
            img.save(THUMBNAILS_DIR / f"thumb_{i}.png")
            print("완료")

    # ── 씬 이미지 프롬프트 우선순위 ─────────────────────────────────────────
    # 1순위: scene_prompts.json (ChatGPT/Claude Pro로 직접 뽑은 파일)
    # 2순위: Anthropic API 자동생성 (ANTHROPIC_API_KEY 있을 때)
    # 3순위: 하드코딩 CHAPTER_SCENE_PROMPTS (현재 스크립트 전용)
    scene_count  = min(len(chapters), 40)
    auto_prompts = None
    source_label = "하드코딩"

    manual_file = Path("scene_prompts.json")
    if manual_file.exists():
        import json
        data = json.loads(manual_file.read_text(encoding="utf-8"))
        # 형식: ["prompt1", "prompt2", ...] 또는 [{"prompt": "..."}, ...]
        if data and isinstance(data[0], dict):
            auto_prompts = [d.get("prompt_en") or d.get("prompt", "") for d in data]
        else:
            auto_prompts = data
        # scene_prompts.json 프롬프트 수를 씬 수로 우선 사용
        scene_count = len(auto_prompts)
        source_label = "scene_prompts.json"
        print_ok(f"scene_prompts.json 사용 ({len(auto_prompts)}개 프롬프트)")
    else:
        auto_prompts = auto_generate_scene_prompts(chapters[:scene_count])
        if auto_prompts:
            source_label = "Claude 자동분석"

    print(f"\n  씬 이미지 {scene_count}장 생성 중 ({source_label} 프롬프트)...")

    using_auto = auto_prompts is not None

    for i in range(scene_count):
        chap = chapters[i] if i < len(chapters) else chapters[-1]

        if using_auto:
            raw = auto_prompts[i % len(auto_prompts)]
            raw, char_seed = _expand_char_tokens(raw)
            label = "auto"
        else:
            scene_def = CHAPTER_SCENE_PROMPTS[i] if i < len(CHAPTER_SCENE_PROMPTS) else CHAPTER_SCENE_PROMPTS[-1]
            raw = scene_def["prompt"]
            char_seed = 0
            label = scene_def["label"]

        # 다중 인물 감지 → 안전 framing 자동 추가
        multi = _is_multi_person(raw)
        if multi:
            prompt = f"{raw}, {MULTI_PERSON_SAFETY}"
        else:
            prompt = raw

        seed = _get_scene_seed(i, char_seed)

        out_path = SCENES_DIR / f"scene_{i+1}.png"
        print(f"    [{i+1:02d}/{scene_count}] {'2인' if multi else '  '} {label:14s}  {chap['title'][:14]}...",
              end=" ", flush=True)

        if out_path.exists():
            print("⏭️  기존 파일 유지")
            continue

        img = fetch_image_hf(prompt, 960, 544, seed=seed)
        if img is None:
            print("❌ 스킵")
            continue
        img = img.resize((1920, 1080), Image.LANCZOS)
        img.save(out_path)
        print("✅")

    return scene_count, hook


def prompt_thumbnail_choice():
    thumbs = [str(THUMBNAILS_DIR / f"thumb_{i}.png") for i in range(1, 4)]
    subprocess.Popen(["open", "-a", "Preview"] + thumbs)
    print("\n  썸네일 3장이 Preview에 열렸습니다.")
    while True:
        c = input("  사용할 썸네일 번호 (1/2/3): ").strip()
        if c in ("1","2","3"): return int(c)
        print("  1, 2, 3 중 하나를 입력하세요.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — TTS (Edge TTS, 청크 처리)
# ══════════════════════════════════════════════════════════════════════════════
def split_script_for_tts(script):
    """문장 단위로 청크 분할 (TTS 글자수 제한 대응)"""
    # 챕터 헤더 제거 (읽히지 않도록)
    script = re.sub(r'【[^】]*】', '', script)
    # ――― 구분자 제거
    script = re.sub(r'^[━─―\-]{3,}$', '', script, flags=re.MULTILINE)

    # 줄바꿈 처리: 단순 줄바꿈은 공백으로 이어붙이고, 빈 줄(\n\n)만 문단 경계로 사용
    # 이렇게 해야 짧은 시적 줄들이 자연스럽게 연결됨
    paragraphs = re.split(r'\n\s*\n', script)
    paragraphs = [' '.join(line.strip() for line in p.splitlines() if line.strip()) for p in paragraphs]
    paragraphs = [p for p in paragraphs if p]

    # 문단을 。！？ 기준으로 문장 분리
    sentences = []
    for para in paragraphs:
        parts = re.split(r'(?<=[。！？])', para)
        sentences.extend([s.strip() for s in parts if s.strip()])

    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > TTS_CHUNK_LIMIT:
            if current: chunks.append(current.strip())
            current = s
        else:
            current += s
    if current.strip(): chunks.append(current.strip())
    return chunks


async def _tts_chunk_edge(text, voice, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=TTS_RATE, pitch=TTS_PITCH).save(str(path))


_SBV2_MODEL_CACHE: dict = {}

def _tts_chunk_sbv2(text: str, model_dir: str, path: Path, style: str = "Neutral", length: float = 1.0):
    """Style-BERT-VITS2 TTS — 로컬 일본어 여성 목소리"""
    from style_bert_vits2.nlp import bert_models
    from style_bert_vits2.constants import Languages
    from style_bert_vits2.tts_model import TTSModel
    import soundfile as sf

    _base = Path(__file__).parent
    bert_dir = str(_base / "model_assets/bert/deberta-v2-large-japanese-char-wwm")
    model_base = _base / "model_assets/voice" / model_dir

    # 모델 파일 자동 탐색
    safetensors = list(model_base.glob("*.safetensors"))
    if not safetensors:
        raise FileNotFoundError(f"safetensors 파일 없음: {model_base}")
    model_file = safetensors[0]

    cache_key = str(model_file)
    if cache_key not in _SBV2_MODEL_CACHE:
        bert_models.load_model(Languages.JP, pretrained_model_name_or_path=bert_dir)
        bert_models.load_tokenizer(Languages.JP, pretrained_model_name_or_path=bert_dir)
        model = TTSModel(
            model_path=model_file,
            config_path=model_base / "config.json",
            style_vec_path=model_base / "style_vectors.npy",
            device="cpu",
        )
        _SBV2_MODEL_CACHE[cache_key] = model

    model = _SBV2_MODEL_CACHE[cache_key]
    sr, audio = model.infer(text=text, style=style, length=length)

    wav_path = path.with_suffix(".wav")
    sf.write(str(wav_path), audio, sr)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-q:a", "2", str(path)],
        capture_output=True, check=True
    )
    wav_path.unlink(missing_ok=True)


_KOKORO_HELPER = Path(__file__).parent / "_kokoro_tts.py"

def _ensure_kokoro_helper():
    """Kokoro는 Python <3.13 필요 → python3.11 서브프로세스용 헬퍼 스크립트 생성"""
    if _KOKORO_HELPER.exists():
        return
    _KOKORO_HELPER.write_text(
        '#!/usr/bin/env python3\n'
        '"""kokoro TTS 헬퍼 — python3.11로 실행됨"""\n'
        'import sys, json\n'
        'from pathlib import Path\n'
        'import soundfile as sf\n'
        'import numpy as np\n'
        'from kokoro import KPipeline\n\n'
        'text, voice, out_wav = sys.argv[1], sys.argv[2], sys.argv[3]\n'
        'pipeline = KPipeline(lang_code="j")\n'
        'parts = [audio for _, _, audio in pipeline(text, voice=voice, speed=1.0)]\n'
        'if not parts: raise RuntimeError("empty audio")\n'
        'sf.write(out_wav, np.concatenate(parts), 24000)\n',
        encoding="utf-8"
    )

def _tts_chunk_kokoro(text: str, voice: str, path: Path):
    """Kokoro TTS — python3.11 서브프로세스 경유 (Python 3.14 호환)"""
    _ensure_kokoro_helper()
    wav_path = path.with_suffix(".wav")
    # python3.11로 헬퍼 실행
    py311 = "/opt/homebrew/bin/python3.11"
    interpreter = py311 if Path(py311).exists() else "python3.11"
    result = subprocess.run(
        [interpreter, str(_KOKORO_HELPER), text, voice, str(wav_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Kokoro 실패: {result.stderr[-300:]}")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-q:a", "2", str(path)],
        capture_output=True, check=True
    )
    wav_path.unlink(missing_ok=True)


def _tts_chunk_voicevox(text, speaker_id, path):
    """VOICEVOX / AivisSpeech API로 단일 청크 음성 생성"""
    import urllib.request, json
    base = "http://localhost:10101" if TTS_ENGINE == "aivis" else "http://localhost:50021"

    # 1단계: audio_query 생성
    params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    req = urllib.request.Request(f"{base}/audio_query?{params}", method="POST")
    with urllib.request.urlopen(req) as r:
        query = json.loads(r.read())

    # 속도/피치 적용
    query["speedScale"]  = TTS_SPEED
    query["pitchScale"]  = TTS_PITCH_VVOX
    query["pauseLength"] = 0.3  # 문장 사이 간격

    # 2단계: synthesis
    body = json.dumps(query).encode("utf-8")
    params2 = urllib.parse.urlencode({"speaker": speaker_id})
    req2 = urllib.request.Request(
        f"{base}/synthesis?{params2}", data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req2) as r:
        wav_data = r.read()

    # WAV → MP3 변환
    wav_path = path.with_suffix(".wav")
    wav_path.write_bytes(wav_data)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-q:a", "2", str(path)],
        capture_output=True, check=True
    )
    wav_path.unlink(missing_ok=True)


def generate_tts(script):
    chunks = split_script_for_tts(script)
    print(f"  분할 청크: {len(chunks)}개")

    chunk_paths = []
    for i, chunk in enumerate(chunks, 1):
        path = AUDIO_DIR / f"chunk_{i:03d}.mp3"
        print(f"  TTS [{i}/{len(chunks)}]...", end=" ", flush=True)
        if TTS_ENGINE == "style-bert-vits2":
            try:
                _sbv2_model = _VC.get("tts", {}).get("sbv2_model", "jvnv-F1-jp")
                _sbv2_style = _VC.get("tts", {}).get("sbv2_style", "Neutral")
                _sbv2_length = _VC.get("tts", {}).get("sbv2_length", 1.0)
                _tts_chunk_sbv2(chunk, _sbv2_model, path, style=_sbv2_style, length=_sbv2_length)
            except Exception as e:
                print_warn(f"Style-BERT-VITS2 실패 ({e}) → Edge TTS 폴백")
                asyncio.run(_tts_chunk_edge(chunk, TTS_VOICE_EDGE, path))
        elif TTS_ENGINE == "kokoro":
            try:
                _tts_chunk_kokoro(chunk, TTS_VOICE_EDGE, path)
            except Exception as e:
                print_warn(f"Kokoro 실패 ({e}) → Edge TTS 폴백")
                asyncio.run(_tts_chunk_edge(chunk, "ja-JP-NanamiNeural", path))
        elif TTS_ENGINE in ("voicevox", "aivis"):
            try:
                _tts_chunk_voicevox(chunk, TTS_VOICE, path)
            except Exception as e:
                print_warn(f"{'AivisSpeech' if TTS_ENGINE == 'aivis' else 'VOICEVOX'} 실패 ({e}) → Edge TTS 폴백")
                asyncio.run(_tts_chunk_edge(chunk, TTS_VOICE_EDGE, path))
        else:
            try:
                import edge_tts  # noqa
            except ImportError:
                print_error("edge-tts 미설치 → pip install edge-tts"); sys.exit(1)
            asyncio.run(_tts_chunk_edge(chunk, TTS_VOICE_EDGE, path))
        chunk_paths.append(str(path))
        print("완료")

    # FFmpeg로 청크 MP3 합치기
    out_path = AUDIO_DIR / "voiceover.mp3"
    if len(chunk_paths) == 1:
        Path(chunk_paths[0]).rename(out_path)
    else:
        list_file = AUDIO_DIR / "chunks.txt"
        list_file.write_text("\n".join(f"file '{Path(p).resolve()}'" for p in chunk_paths), encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", str(out_path)],
            capture_output=True, check=True
        )
        list_file.unlink()
        for p in chunk_paths:
            try: Path(p).unlink()
            except: pass

    print_ok(f"보이스오버 저장: {out_path}")
    return out_path


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — 자막 생성 (Whisper 음성 동기화 우선, 폴백: 균등 분배)
# ══════════════════════════════════════════════════════════════════════════════
def _ass_header(font_name):
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},76,&H00FFFFFF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,4,2,2,10,10,80,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

def _ts(s):
    h, m, sec, cs = int(s//3600), int((s%3600)//60), int(s%60), int((s%1)*100)
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"

def _split_line(text, max_chars=22):
    """일본어 자막 줄 나누기 — 22자 초과 시 줄바꿈"""
    if len(text) <= max_chars:
        return text
    mid = len(text) // 2
    # 句読点 근처에서 자르기
    for i in range(mid, min(mid + 6, len(text))):
        if text[i] in '、。！？':
            return text[:i+1] + r'\N' + text[i+1:].strip()
    return text[:mid] + r'\N' + text[mid:]

def generate_ass_whisper(audio_path, font_name="Hiragino Sans"):
    """faster-whisper로 음성 인식 → 정확한 타임스탬프 ASS 자막 생성"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  faster-whisper 설치 중...")
        subprocess.run([sys.executable, "-m", "pip", "install", "faster-whisper", "-q"], check=True)
        from faster_whisper import WhisperModel

    print("  🎙️  Whisper 음성 인식 중... (small 모델, ja)")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(audio_path),
        language="ja",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
    )

    # 인트로가 있으면 자막 타임스탬프를 인트로 길이만큼 오프셋
    intro_path = ASSETS_DIR / "intro.mp4"
    intro_offset = get_audio_duration(str(intro_path)) if intro_path.exists() else 0.0
    if intro_offset > 0:
        print(f"  인트로 오프셋 적용: +{intro_offset:.2f}초")

    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    events = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        line = _split_line(text)
        events.append(f"Dialogue: 0,{_ts(seg.start + intro_offset)},{_ts(seg.end + intro_offset)},Default,,0,0,0,,{line}")

    ass = SUBTITLES_DIR / "subtitles.ass"
    ass.write_text(_ass_header(font_name) + "\n".join(events), encoding="utf-8")
    srt = ass_to_srt(ass)
    print_ok(f"Whisper 자막 {len(events)}줄 생성 (ASS + SRT)")
    return ass


def ass_to_srt(ass_path: Path) -> Path:
    """ASS 자막 → YouTube 업로드용 SRT 변환"""
    srt_path = ass_path.with_suffix(".srt")
    def _srt_ts(ass_ts: str) -> str:
        # ASS: H:MM:SS.cc → SRT: HH:MM:SS,mmm
        h, m, rest = ass_ts.split(":")
        s, cs = rest.split(".")
        ms = int(cs) * 10
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"

    content = ass_path.read_text(encoding="utf-8")
    dialogue_re = re.compile(
        r"^Dialogue:\s*\d+,(\d+:\d+:\d+\.\d+),(\d+:\d+:\d+\.\d+),[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,(.*)$",
        re.MULTILINE,
    )
    entries = dialogue_re.findall(content)
    lines = []
    for idx, (start, end, text) in enumerate(entries, 1):
        clean = re.sub(r"\{[^}]*\}", "", text).replace(r"\N", "\n").replace(r"\n", "\n")
        lines.append(f"{idx}\n{_srt_ts(start)} --> {_srt_ts(end)}\n{clean.strip()}\n")
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return srt_path


def generate_ass(script, total_duration, font_name="Hiragino Sans"):
    """폴백용 균등 분배 자막 (Whisper 실패 시)"""
    clean = re.sub(r'[━─―\-]{5,}', '', script)
    clean = re.sub(r'【[^】]*】', '', clean)
    # 줄바꿈 우선 분리 후 문장 부호로 추가 분리
    raw_lines = [l.strip() for l in clean.splitlines() if l.strip() and len(l.strip()) >= 2]
    sentences = []
    for l in raw_lines:
        parts = re.split(r'(?<=[。！？])\s*', l)
        sentences.extend([p.strip() for p in parts if p.strip() and len(p.strip()) >= 2])
    if not sentences: sentences = [script[:40]]

    seg = total_duration / len(sentences)
    events = []
    for i, sent in enumerate(sentences):
        line = _split_line(sent)
        events.append(f"Dialogue: 0,{_ts(i*seg)},{_ts((i+1)*seg - 0.05)},Default,,0,0,0,,{line}")

    SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)
    ass = SUBTITLES_DIR / "subtitles.ass"
    ass.write_text(_ass_header(font_name) + "\n".join(events), encoding="utf-8")
    ass_to_srt(ass)
    return ass


# ══════════════════════════════════════════════════════════════════════════════
# Pillow Ken Burns 씬 클립 생성 (VideoToolbox 인코딩)
# ══════════════════════════════════════════════════════════════════════════════
def make_scene_clip(img_path: Path, duration: float, fps: int, direction: int, out_path: Path):
    """
    Pillow로 Ken Burns 줌/패닝 프레임 생성 후 rawvideo→FFmpeg 파이프로 인코딩.
    h264_videotoolbox 사용 (Apple Silicon GPU 가속).
    direction: 0~7 (8가지 방향 순환)
    """
    try:
        from PIL import Image
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "-q"], check=True)
        from PIL import Image

    W, H = 1920, 1080
    n_frames = int(duration * fps)

    img = Image.open(img_path).convert("RGB")
    scale = max(W / img.width, H / img.height)
    new_w, new_h = int(img.width * scale), int(img.height * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # 정중앙 크롭
    left = (new_w - W) // 2
    top  = (new_h - H) // 2
    frame_img = img.crop((left, top, left + W, top + H))
    frame_bytes = frame_img.tobytes()

    def _run_ffmpeg(codec: str, extra_args: list[str] | None = None):
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{W}x{H}", "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "pipe:0",
            "-vf", "null",
            "-c:v", codec,
            *(extra_args or []),
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            str(out_path),
        ]

        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(n_frames):
                proc.stdin.write(frame_bytes)
            proc.stdin.close()
        except BrokenPipeError:
            if proc.stdin:
                proc.stdin.close()
        stderr = proc.stderr.read().decode("utf-8", "ignore")
        proc.wait()
        return proc.returncode, stderr

    # 중간 클립은 libx264 ultrafast — GPU 압박 없음, 최종 렌더에서 재인코딩됨
    returncode, stderr = _run_ffmpeg("libx264", ["-preset", "ultrafast", "-crf", "18"])
    if returncode != 0:
        raise RuntimeError(f"make_scene_clip FFmpeg 실패: {out_path}\n{stderr[-1200:]}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — 영상 렌더링 (FFmpeg, 롱폼)
# ══════════════════════════════════════════════════════════════════════════════
def render_video(audio_path, srt_path, scene_count, chapters, output_date):
    check_ffmpeg()

    audio_dur  = get_audio_duration(audio_path)
    fps        = VIDEO_FPS
    base = FINAL_DIR / f"{output_date}.mp4"
    if base.exists():
        import time as _time
        suffix = _time.strftime("%H%M%S")
        out_path = FINAL_DIR / f"{output_date}_{suffix}.mp4"
    else:
        out_path = base

    CLIPS_DIR_TMP = OUTPUT_DIR / "clips"

    # total_clips: 씬 이미지 수와 기존 clip 최대 번호 중 큰 값
    existing_mp4s = sorted(CLIPS_DIR_TMP.glob("clip_*.mp4"))
    max_clip_num = max(int(p.stem.split("_")[1]) for p in existing_mp4s) if existing_mp4s else 0
    scene_files = list(SCENES_DIR.glob("scene_*.png")) + list(SCENES_DIR.glob("scene_*.jpg"))
    max_scene_num = max((int(p.stem.split("_")[1]) for p in scene_files), default=scene_count)
    total_clips = max(max_clip_num, max_scene_num)

    # 기존 사용자 클립의 실제 길이를 합산해서 나머지 시간을 파이프라인 클립에 분배
    existing_dur = 0.0
    existing_count = 0
    for i in range(1, total_clips + 1):
        cp = CLIPS_DIR_TMP / f"clip_{i:03d}.mp4"
        if cp.exists() and cp.stat().st_size > 0:
            existing_dur += get_audio_duration(cp)
            existing_count += 1
    pipeline_count = total_clips - existing_count
    if pipeline_count > 0:
        scene_dur = (audio_dur - existing_dur) / pipeline_count
    else:
        scene_dur = audio_dur / total_clips

    print(f"  오디오: {audio_dur:.0f}초 ({audio_dur/60:.1f}분) → {total_clips}클립 (기존mp4 {existing_count}개={existing_dur:.0f}초, 생성 {pipeline_count}개→씬당 {scene_dur:.1f}초)")

    has_intro = (ASSETS_DIR / "intro.mp4").exists()
    has_outro = (ASSETS_DIR / "outro.mp4").exists()

    # 챕터 무드별 합성 BGM
    composite_bgm = build_composite_bgm(chapters, audio_dur) if (chapters or BGM_ZONES) else None
    has_bgm = composite_bgm and Path(composite_bgm).exists()

    # ── Pillow Ken Burns: 씬별 클립 사전 생성 (클립 번호로 직접 매핑) ──────────
    CLIPS_DIR = CLIPS_DIR_TMP
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    clip_paths = []
    print(f"  Ken Burns 씬 클립 생성 중 ({total_clips}개)...")
    for i in range(total_clips):
        clip_num = i + 1
        clip_path = CLIPS_DIR / f"clip_{clip_num:03d}.mp4"
        print(f"    씬 {clip_num}/{total_clips}...", end=" ", flush=True)
        if clip_path.exists() and clip_path.stat().st_size > 0:
            print("재사용")
        else:
            if clip_path.exists() and clip_path.stat().st_size == 0:
                clip_path.unlink()
            # 클립 번호에 대응하는 씬 이미지 직접 탐색 (scene_XXX.png)
            candidates = [
                SCENES_DIR / f"scene_{clip_num:03d}.png",
                SCENES_DIR / f"scene_{clip_num:03d}.jpg",
                SCENES_DIR / f"scene_{clip_num:03d}.jpeg",
                SCENES_DIR / f"scene_{clip_num}.png",
                SCENES_DIR / f"scene_{clip_num}.jpg",
            ]
            img_path = next((c for c in candidates if c.exists()), None)
            if img_path is None:
                raise FileNotFoundError(f"씬 이미지 없음: clip_{clip_num:03d} → scene_{clip_num:03d}.png")
            make_scene_clip(img_path, scene_dur, fps, i, clip_path)
            print("완료")
        clip_paths.append(clip_path)

    # ── 입력 구성 (concat demuxer용 list 파일) ───────────────────────────────
    inputs = []
    idx    = 0

    intro_idx = None
    if has_intro:
        inputs += ["-i", str(ASSETS_DIR / "intro.mp4")]
        intro_idx = idx; idx += 1

    # concat 전 모든 클립을 video-only로 정규화 (스트림 구성 통일)
    # user 제공 클립은 audio 있고, scene 생성 클립은 audio 없어서 concat demuxer가 깨짐
    norm_dir = CLIPS_DIR / "_norm"
    norm_dir.mkdir(exist_ok=True)
    norm_paths = []
    ffmpeg_bin = FFMPEG_FULL if Path(FFMPEG_FULL).exists() else "ffmpeg"
    print(f"  클립 정규화 중 ({len(clip_paths)}개)...")

    def _is_video_only(path: Path) -> bool:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
        streams = r.stdout.strip().splitlines()
        return streams == ["video"]

    for cp in clip_paths:
        norm_p = norm_dir / cp.name
        if not norm_p.exists():
            if _is_video_only(cp):
                # 이미 video-only → hardlink으로 복사 (재인코딩 생략)
                try:
                    import os as _os
                    _os.link(str(cp), str(norm_p))
                except OSError:
                    import shutil as _shutil
                    _shutil.copy2(str(cp), str(norm_p))
            else:
                subprocess.run([
                    ffmpeg_bin, "-y", "-i", str(cp),
                    "-map", "0:v:0",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                    "-r", str(fps), "-pix_fmt", "yuv420p", "-an",
                    str(norm_p),
                ], check=True, capture_output=True)
        norm_paths.append(norm_p)

    # concat demuxer로 씬 연결 → 중간 파일 (모두 video-only로 통일됨)
    clip_list = CLIPS_DIR / "clips.txt"
    clip_list.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in norm_paths),
        encoding="utf-8"
    )
    concat_scenes = CLIPS_DIR / "scenes_concat.mp4"
    subprocess.run([
        ffmpeg_bin, "-y",
        "-f", "concat", "-safe", "0", "-i", str(clip_list),
        "-c", "copy",
        str(concat_scenes),
    ], check=True, capture_output=True)

    scene_concat_idx = idx
    inputs += ["-i", str(concat_scenes)]; idx += 1

    outro_idx = None
    if has_outro:
        inputs += ["-i", str(ASSETS_DIR / "outro.mp4")]
        outro_idx = idx; idx += 1

    voice_idx = idx; inputs += ["-i", str(audio_path)]; idx += 1

    bgm_idx = None
    if has_bgm:
        inputs += ["-i", composite_bgm]
        bgm_idx = idx; idx += 1

    # ── filter_complex ────────────────────────────────────────────────────────
    filters = []

    concat_parts = []
    if intro_idx is not None:
        filters.append(f"[{intro_idx}:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[intro_v]")
        concat_parts.append("[intro_v]")

    filters.append(f"[{scene_concat_idx}:v]setsar=1[scenes_v]")
    concat_parts.append("[scenes_v]")

    if outro_idx is not None:
        filters.append(f"[{outro_idx}:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[outro_v]")
        concat_parts.append("[outro_v]")

    if len(concat_parts) > 1:
        filters.append(f"{''.join(concat_parts)}concat=n={len(concat_parts)}:v=1:a=0[final_v]")
    else:
        filters.append(f"[scenes_v]copy[final_v]")

    # 오디오 믹싱 (voice loudnorm -14 LUFS + BGM_VOLUME 적용)
    if bgm_idx is not None:
        filters.append(f"[{voice_idx}:a]dynaudnorm=f=150:g=15[voice_n]")
        filters.append(f"[voice_n][{bgm_idx}:a]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[main_a]")
    else:
        filters.append(f"[{voice_idx}:a]dynaudnorm=f=150:g=15[main_a]")

    # 인트로 오디오가 있으면 intro 오디오 + main 오디오 순서로 concat
    if intro_idx is not None:
        filters.append(f"[{intro_idx}:a]asetpts=PTS-STARTPTS[intro_a]")
        filters.append(f"[intro_a][main_a]concat=n=2:v=0:a=1[final_a]")
    else:
        filters.append(f"[main_a]acopy[final_a]")

    # 자막 하드서브 (libass 필요)
    final_video_label = "[final_v]"
    ass_file = None
    if srt_path:
        sp = Path(str(srt_path))
        if sp.suffix == ".ass" and sp.exists():
            ass_file = sp
        else:
            candidate = sp.with_suffix(".ass")
            if candidate.exists():
                ass_file = candidate
    ffmpeg_bin = "ffmpeg"
    if ass_file:
        # libass 필요 → ffmpeg-full 사용
        esc = str(ass_file.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"[final_v]ass='{esc}'[final_vs]")
        final_video_label = "[final_vs]"
        ffmpeg_bin = FFMPEG_FULL if Path(FFMPEG_FULL).exists() else "ffmpeg"
        print(f"  자막 하드서브 적용: {ass_file.name} (ffmpeg: {ffmpeg_bin})")

    cmd = [
        ffmpeg_bin, "-y", *inputs,
        "-filter_complex", "; ".join(filters),
        "-map", final_video_label, "-map", "[final_a]",
        "-c:v", "h264_videotoolbox", "-b:v", "5M",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(fps), "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-threads", "2",
        "-max_muxing_queue_size", "512",
        str(out_path),
    ]

    print("  FFmpeg 최종 합성 중 (VideoToolbox, low-memory)...")
    # stderr를 파일로 흘려보내 RAM 축적 방지
    stderr_log = CLIPS_DIR / "render_stderr.log"
    with open(stderr_log, "w") as _log:
        result = subprocess.run(cmd, stderr=_log, stdout=subprocess.DEVNULL)
    if result.returncode != 0:
        print_error("FFmpeg 렌더링 실패")
        log_lines = stderr_log.read_text(errors="replace").splitlines()
        for line in log_lines[-30:]: print(f"  {line}")
        sys.exit(1)

    print_ok(f"영상 저장: {out_path} ({audio_dur/60:.1f}분)")
    return out_path


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — YouTube 업로드
# ══════════════════════════════════════════════════════════════════════════════
def upload_to_youtube(video_path, thumb_choice, metadata):
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        print_error("google-api-python-client 미설치"); sys.exit(1)

    SCOPES     = ["https://www.googleapis.com/auth/youtube.upload"]
    TOKEN_PATH = Path("token.pickle")
    creds      = None

    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f: creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(YOUTUBE_CLIENT_SECRETS).exists():
                print_error(f"client_secrets.json 없음: {YOUTUBE_CLIENT_SECRETS}"); sys.exit(1)
            flow  = __import__("google_auth_oauthlib.flow", fromlist=["InstalledAppFlow"]).InstalledAppFlow
            creds = flow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS, SCOPES).run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as f: pickle.dump(creds, f)

    yt = build("youtube", "v3", credentials=creds)

    # 설명 구성 — "실화 기반 재구성" 프레이밍
    base_desc = metadata.get("description", "")
    full_desc = (
        f"{base_desc}\n\n"
        f"{'─'*38}\n"
        f"📖 {STORY_NOTICE_JP}\n\n"
        f"🎤 {AI_ASSIST_NOTICE_JP}"
    )

    tags       = [t.strip() for t in metadata.get("tags","").split(",") if t.strip()]
    channel_id = metadata.get("channel_id","").strip()
    category   = metadata.get("category_id","22").strip()

    snippet = {
        "title":                metadata.get("title","無題"),
        "description":          full_desc,
        "tags":                 tags,
        "categoryId":           category,
        "defaultLanguage":      "ja",
        "defaultAudioLanguage": "ja",
    }
    if channel_id:
        snippet["channelId"] = channel_id
        print_ok(f"채널: {channel_id}")

    body = {
        "snippet": snippet,
        "status": {
            "privacyStatus":           "private",
            "selfDeclaredMadeForKids": False,
            "madeForKids":             False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4",
                            resumable=True, chunksize=10*1024*1024)

    print("  업로드 중 (비공개)...")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status: print(f"  업로드: {int(status.progress()*100)}%", end="\r")
    print()

    video_id = response["id"]
    print_ok(f"업로드 완료! ID: {video_id}")

    # 썸네일
    thumb = THUMBNAILS_DIR / f"thumb_{thumb_choice}.png"
    if thumb.exists():
        try:
            yt.thumbnails().set(videoId=video_id,
                media_body=MediaFileUpload(str(thumb), mimetype="image/png")).execute()
            print_ok("썸네일 설정 완료")
        except Exception as e:
            print_warn(f"썸네일 수동 설정 필요: {e}")

    # AI 콘텐츠 공시
    try:
        yt.videos().update(part="status", body={
            "id": video_id,
            "status": {"privacyStatus":"private","selfDeclaredMadeForKids":False,
                       "containsSyntheticMedia":True}
        }).execute()
        print_ok("AI 보조 제작 공시 완료")
    except Exception:
        print_warn("YouTube Studio에서 AI 생성 콘텐츠 항목 수동 확인 권장")

    url = f"https://studio.youtube.com/video/{video_id}/edit"
    print(f"\n  🎬 YouTube Studio:\n  {url}")
    return video_id


# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════
def main():
    import argparse
    parser = argparse.ArgumentParser(description="🎌 일본 시니어 롱폼 YouTube 파이프라인")
    parser.add_argument("--script",       required=True)
    parser.add_argument("--thumb",        type=int, choices=[1,2,3])
    parser.add_argument("--skip-images",  action="store_true")
    parser.add_argument("--skip-thumbs",  action="store_true", help="썸네일 생성 건너뜀 (기존 파일 재사용)")
    parser.add_argument("--skip-tts",     action="store_true")
    parser.add_argument("--skip-video",   action="store_true")
    parser.add_argument("--reuse-subs",   action="store_true", help="기존 subtitles.ass 재사용 (Whisper 건너뜀)")
    parser.add_argument("--skip-upload",  action="store_true")
    parser.add_argument("--no-clean",     action="store_true", help="이전 작업 파일 유지 (skip 플래그 쓸 때)")
    args   = parser.parse_args()
    ensure_dirs()

    # 새 영상 시작 시 이전 작업 파일 자동 클리어 (final은 유지)
    if not args.no_clean and not any([args.skip_images, args.skip_tts, args.skip_video]):
        import shutil
        for d in [SCENES_DIR, AUDIO_DIR, THUMBNAILS_DIR, SUBTITLES_DIR,
                  OUTPUT_DIR / "clips"]:
            if d.exists():
                shutil.rmtree(d)
        ensure_dirs()
        print("  🗑️  이전 작업 파일 정리 완료")

    download_bgm_tracks()
    today  = datetime.date.today().isoformat()

    print("\n" + "═"*60)
    print("  🎌 일본 시니어 생애 이야기 — 롱폼 YouTube 파이프라인")
    print("═"*60)

    script   = load_script(args.script)
    metadata = load_metadata()
    chapters = parse_chapters(script)

    print(f"\n  📖 챕터 감지: {len(chapters)}개")
    for i, c in enumerate(chapters[:5], 1):
        print(f"    {i}. {c['title']} ({len(c['body'])}자)")
    if len(chapters) > 5: print(f"    ... 외 {len(chapters)-5}개")

    print("\n🔍 콘텐츠 안전성 검사...")
    if not check_script_safety(script): sys.exit(1)
    print_ok("통과")

    # [1/4] 이미지
    print_step(1, 4, "이미지 생성 중... (Pollinations.ai Flux)")
    scene_count = len(chapters)
    if not args.skip_images:
        scene_count, _ = generate_images(script, chapters, skip_thumbs=getattr(args, "skip_thumbs", False))
        print_ok(f"이미지 완료 (씬 {scene_count}장)")
    else:
        # skip 시 기존 씬 파일 수 카운트
        scene_count = len(
            list(SCENES_DIR.glob("scene_*.png")) +
            list(SCENES_DIR.glob("scene_*.jpg")) +
            list(SCENES_DIR.glob("scene_*.jpeg"))
        )
        print(f"  ⏭️  건너뜀 (기존 씬 {scene_count}장 사용)")

    thumb_choice = args.thumb or prompt_thumbnail_choice()
    print_ok(f"썸네일 확정: thumb_{thumb_choice}.png")

    # [2/4] TTS
    tts_label = f"AivisSpeech:{TTS_VOICE}" if TTS_ENGINE == "aivis" else (f"VOICEVOX:{TTS_VOICE}" if TTS_ENGINE == "voicevox" else TTS_VOICE_EDGE)
    print_step(2, 4, f"보이스오버 생성 중... ({tts_label})")
    audio_path = AUDIO_DIR / "voiceover.mp3"
    if not args.skip_tts:
        audio_path = generate_tts(script)
    else:
        print("  ⏭️  건너뜀")
    if not audio_path.exists():
        print_error(f"오디오 없음: {audio_path}"); sys.exit(1)

    # [3/4] 렌더링
    audio_dur = get_audio_duration(audio_path)
    print_step(3, 4, f"영상 렌더링 중... ({audio_dur/60:.0f}분 분량)")
    video_path = FINAL_DIR / f"{today}.mp4"
    if not args.skip_video:
        font_name  = "Hiragino Sans" if "Hiragino" in find_japanese_font() else "Noto Sans CJK JP"
        existing_ass = SUBTITLES_DIR / "subtitles.ass"
        if args.reuse_subs and existing_ass.exists():
            print(f"  ⏭️  기존 자막 재사용: {existing_ass}")
            srt_path = existing_ass
        else:
            try:
                srt_path = generate_ass_whisper(audio_path, font_name)
            except Exception as e:
                print_warn(f"Whisper 실패 ({e}) → 균등 분배 자막으로 폴백")
                srt_path = generate_ass(script, audio_dur, font_name)
        print_ok(f"자막 생성: {srt_path}")
        video_path = render_video(audio_path, srt_path, scene_count, chapters, today)
    else:
        print("  ⏭️  건너뜀")

    # [4/4] 업로드
    print_step(4, 4, "YouTube 업로드 중... (비공개)")
    if not args.skip_upload:
        if not video_path.exists():
            print_error(f"영상 없음: {video_path}"); sys.exit(1)
        upload_to_youtube(video_path, thumb_choice, metadata)
    else:
        print("  ⏭️  건너뜀")

    print("\n" + "═"*60)
    print("  ✅ 완료!")
    print(f"  📹 {video_path}")
    print("═"*60 + "\n")


if __name__ == "__main__":
    main()
