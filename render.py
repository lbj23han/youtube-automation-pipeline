#!/usr/bin/env python3
"""
render.py — 최종 렌더링 단일 스크립트

구조:
  output/clips/clip_NNN.mp4    포지션별 클립 (있는 것 유지, 없는 것은 scene_NNN.png 로 생성)
  output/scenes/scene_NNN.png  포지션별 씬 이미지 (1~148)
  output/audio/voiceover.mp3   보이스오버
  output/audio/intro_narration.mp3  인트로 나레이션 (있으면 intro.mp4 에 합성)
  assets/intro.mp4             인트로 영상 (없으면 건너뜀)
  assets/bgm_*.mp3             BGM 파일들

출력:
  output/audio/bgm_composite.mp3  (없으면 생성)
  output/final/YYYY-MM-DD.mp4
"""

import json, re, subprocess, sys, tempfile, datetime
from pathlib import Path

# ── 경로 ─────────────────────────────────────────────────────────────────────
CLIPS_DIR   = Path("output/clips")
SCENES_DIR  = Path("output/scenes")
AUDIO_DIR   = Path("output/audio")
SUBS_DIR    = Path("output/subtitles")
ASSETS_DIR  = Path("assets")
FINAL_DIR   = Path("output/final")
NORM_DIR    = CLIPS_DIR / "_norm"

SCRIPT      = Path("script.txt")
VOICEOVER   = AUDIO_DIR / "voiceover.mp3"
TIMING_FILE = AUDIO_DIR / "chunks_timing.json"
INTRO_NAR   = AUDIO_DIR / "intro_narration.mp3"
BGM         = AUDIO_DIR / "bgm_composite.mp3"
SUBS        = SUBS_DIR  / "subtitles.ass"
INTRO       = ASSETS_DIR / "intro.mp4"
VIDEO_CFG   = Path("video_config.json")

FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
FFMPEG      = FFMPEG_FULL if Path(FFMPEG_FULL).exists() else "ffmpeg"

W, H, FPS = 1920, 1080, 30

for d in [CLIPS_DIR, NORM_DIR, FINAL_DIR, SUBS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── video_config.json ────────────────────────────────────────────────────────
_VC = json.loads(VIDEO_CFG.read_text()) if VIDEO_CFG.exists() else {}
_bgm_cfg      = _VC.get("bgm", {})
BGM_VOLUME    = _bgm_cfg.get("volume", 0.25)
BGM_CROSSFADE = _bgm_cfg.get("crossfade", 3.0)
BGM_ZONES     = [(z["end_sec"], z["mood"]) for z in _bgm_cfg.get("zones", [])]
SCENE_SEQUENCE = _VC.get("scene_sequence", [])


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def run(*args, **kw):
    return subprocess.run(list(args), check=True, capture_output=True, **kw)


def get_duration(path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def get_video_info(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,codec_name",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    parts = r.stdout.strip().split(",")
    codec, w, h, fps_str = parts[0], int(parts[1]), int(parts[2]), parts[3]
    num, den = fps_str.split("/")
    fps = int(num) / int(den)
    return codec, w, h, fps


def ass_to_sec(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def sec_to_ass(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


# ── Step 1: 누락 클립 생성 ───────────────────────────────────────────────────
def build_missing_clips():
    """N.mp4 없는 이미지 번호만 N.png 에서 생성. scene_sequence 기반."""
    if not SCENE_SEQUENCE:
        print("❌ video_config.json에 scene_sequence 없음"); sys.exit(1)

    needed = sorted(set(SCENE_SEQUENCE))

    audio_dur = get_duration(VOICEOVER)

    # 기존 클립은 길이 그대로 유지
    existing = {}
    for n in needed:
        p = CLIPS_DIR / f"{n}.mp4"
        if p.exists():
            existing[n] = get_duration(p)

    missing = [n for n in needed if n not in existing]

    # 기존 클립이 시퀀스에서 차지하는 총 시간 계산
    existing_total = sum(existing[n] * SCENE_SEQUENCE.count(n) for n in existing)
    # 나머지 시간을 missing 클립 등장 횟수로 균등분배
    missing_occurrences = sum(SCENE_SEQUENCE.count(n) for n in missing)
    if missing_occurrences > 0:
        clip_dur = (audio_dur - existing_total) / missing_occurrences
    else:
        clip_dur = audio_dur / len(SCENE_SEQUENCE)

    print(
        f"클립 현황: 필요 {len(needed)}종 | 기존 {len(existing)}개 | "
        f"생성 {len(missing)}개 ({clip_dur:.3f}초/개)"
    )

    for i, n in enumerate(missing, 1):
        img_path = SCENES_DIR / f"{n}.png"
        if not img_path.exists():
            print(f"  ⚠️  {n}.png 없음 — 스킵")
            continue
        out = CLIPS_DIR / f"{n}.mp4"
        print(f"  [{i}/{len(missing)}] {n}.mp4 생성...", end=" ", flush=True)
        _make_clip(img_path, clip_dur, out)
        print("완료")

    return audio_dur


def _make_clip(img_path: Path, duration: float, out_path: Path):
    r = subprocess.run([
        FFMPEG, "-y",
        "-loop", "1", "-i", str(img_path),
        "-t", f"{duration:.6f}",
        "-vf", (
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS}"
        ),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-profile:v", "high", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-an",
        str(out_path),
    ], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"클립 생성 실패: {out_path}\n{r.stderr.decode()[-300:]}")


# ── Step 2: 정규화 + concat ──────────────────────────────────────────────────
def normalize_and_concat() -> Path:
    unique_nums = sorted(set(SCENE_SEQUENCE))
    print(f"\n정규화 중 ({len(unique_nums)}종)...")

    norm_map = {}  # n -> Path
    for n in unique_nums:
        cp = CLIPS_DIR / f"{n}.mp4"
        if not cp.exists():
            print(f"  ⚠️  {n}.mp4 없음 — 스킵"); continue
        np_ = NORM_DIR / f"{n}.mp4"
        if not (np_.exists() and np_.stat().st_mtime >= cp.stat().st_mtime):
            subprocess.run([
                FFMPEG, "-y", "-i", str(cp),
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                       f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
                       f"setsar=1,fps={FPS},setpts=PTS-STARTPTS",
                "-map", "0:v:0",
                "-c:v", "h264_videotoolbox", "-b:v", "6M",
                "-bf", "0",
                "-r", str(FPS), "-pix_fmt", "yuv420p", "-an",
                str(np_),
            ], check=True, capture_output=True)
        norm_map[n] = np_

    # 시퀀스 순서대로 concat list 작성
    concat_list = CLIPS_DIR / "clips_norm.txt"
    lines = []
    for n in SCENE_SEQUENCE:
        if n in norm_map:
            lines.append(f"file '{norm_map[n].resolve()}'")
    concat_list.write_text("\n".join(lines))

    scenes_concat = CLIPS_DIR / "scenes_concat.mp4"
    print(f"  concat 중 ({len(lines)}개 엔트리, {len(unique_nums)}종)...")
    subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(scenes_concat),
    ], check=True, capture_output=True)

    dur = get_duration(scenes_concat)
    print(f"  완료: {dur:.1f}초 ({dur/60:.1f}분)")
    return scenes_concat


# ── Step 3: BGM 합성 ─────────────────────────────────────────────────────────
def _bgm_file_for_mood(mood: str):
    folder = ASSETS_DIR / "bgm" / mood
    if folder.exists():
        files = list(folder.glob("*.mp3"))
        if files:
            return str(files[0])
    p = ASSETS_DIR / f"bgm_{mood}.mp3"
    if p.exists():
        return str(p)
    for fallback in ["calm", "healing", "warm"]:
        fp = ASSETS_DIR / f"bgm_{fallback}.mp3"
        if fp.exists():
            return str(fp)
    return None


def build_bgm(audio_dur: float):
    if BGM.exists():
        print(f"\nBGM 캐시 사용: {BGM.name}")
        return

    if not BGM_ZONES:
        print("\n⚠️  video_config.json에 bgm.zones 없음 — BGM 건너뜀")
        return

    print(f"\nBGM 합성 중 ({len(BGM_ZONES)}개 존)...")

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
    if prev < audio_dur - 0.5:
        zone_list.append((audio_dur - prev, zone_list[-1][1] if zone_list else "calm"))

    print(f"  존: {' '.join(f'{m}({d:.0f}s)' for d, m in zone_list)}")

    ALL_MOODS = ["japanese", "calm", "sad", "dramatic", "hopeful", "warm",
                 "healing", "nostalgic", "tense", "wagashi"]
    inputs_cmd, mood_idx, offset_map = [], {}, {}
    for i, mood in enumerate(ALL_MOODS):
        f = _bgm_file_for_mood(mood)
        if f:
            inputs_cmd += ["-stream_loop", "-1", "-i", f]
            mood_idx[mood] = len(mood_idx)
            offset_map[mood] = 0.0

    if not mood_idx:
        print("⚠️  BGM 파일 없음 — 건너뜀"); return

    filters, seg_labels = [], []
    for i, (dur, mood) in enumerate(zone_list):
        m = mood if mood in mood_idx else next(iter(mood_idx))
        src = mood_idx[m]
        start = offset_map[m]
        offset_map[m] += dur
        lbl = f"seg{i}"
        filters.append(
            f"[{src}:a]atrim=start={start:.3f}:duration={dur:.3f},"
            f"asetpts=PTS-STARTPTS[{lbl}]"
        )
        seg_labels.append(f"[{lbl}]")

    cf = BGM_CROSSFADE
    if len(seg_labels) == 1:
        filters.append(f"{seg_labels[0]}volume={BGM_VOLUME}[bgm_out]")
    else:
        prev_lbl = seg_labels[0]
        for i in range(1, len(seg_labels)):
            out_lbl = f"cf{i}"
            filters.append(
                f"{prev_lbl}{seg_labels[i]}acrossfade=d={cf:.1f}:c1=tri:c2=tri[{out_lbl}]"
            )
            prev_lbl = f"[{out_lbl}]"
        filters.append(f"{prev_lbl}volume={BGM_VOLUME}[bgm_out]")

    cmd = [
        FFMPEG, "-y", *inputs_cmd,
        "-filter_complex", "; ".join(filters),
        "-map", "[bgm_out]",
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(BGM),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("⚠️  BGM 합성 실패:", r.stderr.splitlines()[-1] if r.stderr else "")
    else:
        print(f"  완료: {BGM.name}")


# ── Step 4: 자막 준비 ────────────────────────────────────────────────────────
def _ass_header():
    return (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Hiragino Sans,76,&H00FFFFFF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,4,2,2,10,10,80,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _ts(s: float) -> str:
    s = max(0.0, s)
    h, m = int(s // 3600), int((s % 3600) // 60)
    return f"{h}:{m:02d}:{s % 60:05.2f}"


def _split(text: str, max_chars: int = 22) -> str:
    if len(text) <= max_chars:
        return text
    mid = len(text) // 2
    for i in range(mid, min(mid + 6, len(text))):
        if text[i] in "、。！？":
            return text[:i+1] + r"\N" + text[i+1:].strip()
    return text[:mid] + r"\N" + text[mid:]


def generate_subtitles():
    if TIMING_FILE.exists():
        _generate_subtitles_from_chunks()
    else:
        print("  ⚠️  chunks_timing.json 없음 — voiceover를 먼저 재생성하세요")


def _generate_subtitles_from_chunks():
    timing = json.loads(TIMING_FILE.read_text(encoding="utf-8"))
    events = []
    for seg in timing:
        text = seg["text"].strip()
        if not text:
            continue
        start, end = seg["start"], seg["end"]
        dur = end - start

        # 。！？ 경계로 문장 분할 후 글자 수 비례로 시간 배분
        sentences = [s.strip() for s in re.split(r'(?<=[。！？])', text) if s.strip()]
        if not sentences:
            continue
        total_chars = sum(len(s) for s in sentences)
        cursor = start
        for s in sentences:
            s_dur = dur * len(s) / total_chars if total_chars > 0 else dur / len(sentences)
            events.append(
                f"Dialogue: 0,{_ts(cursor)},{_ts(cursor + s_dur)},Default,,0,0,0,,{_split(s)}"
            )
            cursor += s_dur

    SUBS.write_text(_ass_header() + "\n".join(events), encoding="utf-8")
    print(f"  {len(events)}줄 생성 → {SUBS}")


def prepare_subtitles(intro_dur: float):
    needs_regen = not SUBS.exists() or SUBS.stat().st_mtime < VOICEOVER.stat().st_mtime
    if needs_regen:
        print("  자막 재생성 (script forced alignment)...")
        generate_subtitles()
    if not SUBS.exists():
        return None

    pattern = re.compile(
        r"^(Dialogue:[^,]*,)(\d:\d{2}:\d{2}\.\d{2})(,)(\d:\d{2}:\d{2}\.\d{2})(,.*)$"
    )
    lines = SUBS.read_text(encoding="utf-8").splitlines()
    if not any(pattern.match(l) for l in lines):
        return None

    print(f"  자막 shift: +{intro_dur:.2f}초 (인트로 길이)")
    shifted = []
    for line in lines:
        m = pattern.match(line)
        if m:
            start = sec_to_ass(ass_to_sec(m.group(2)) + intro_dur)
            end   = sec_to_ass(ass_to_sec(m.group(4)) + intro_dur)
            line  = f"{m.group(1)}{start}{m.group(3)}{end}{m.group(5)}"
        shifted.append(line)

    tmp = tempfile.NamedTemporaryFile(suffix=".ass", delete=False, mode="w", encoding="utf-8")
    tmp.write("\n".join(shifted))
    tmp.close()
    return Path(tmp.name)


# ── Step 5: 최종 렌더링 ──────────────────────────────────────────────────────
def final_render(scenes_concat: Path) -> Path:
    has_intro     = INTRO.exists()
    has_bgm       = BGM.exists()
    has_intro_nar = INTRO_NAR.exists()
    _now = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = FINAL_DIR / f"{_now}.mp4"
    suffix = 2
    while out_path.exists():
        out_path = FINAL_DIR / f"{_now}_{suffix}.mp4"
        suffix += 1
    TEMP_MAIN     = CLIPS_DIR / "_tmp_main.mp4"

    # ── A: 본영상만 독립 렌더링 (voiceover 0초부터, 자막 0초부터) ─────────────
    print("  [A] 본영상 렌더링...")
    inputs  = ["-i", str(scenes_concat), "-i", str(VOICEOVER)]
    bgm_idx = None
    if has_bgm:
        inputs += ["-i", str(BGM)]; bgm_idx = 2

    fc = []
    if SUBS.exists():
        esc = str(SUBS.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        fc.append(f"[0:v]ass='{esc}'[vout]")
        vmap = "[vout]"
    else:
        vmap = "0:v:0"

    fc.append("[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[voice_n]")
    if bgm_idx is not None:
        fc.append(f"[{bgm_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bgm_a]")
        fc.append("[voice_n][bgm_a]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]")
        amap = "[aout]"
    else:
        amap = "[voice_n]"

    r = subprocess.run([
        FFMPEG, "-y", *inputs,
        "-filter_complex", "; ".join(fc),
        "-map", vmap, "-map", amap,
        "-c:v", "h264_videotoolbox", "-b:v", "5M",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(FPS), "-pix_fmt", "yuv420p",
        "-shortest",
        str(TEMP_MAIN),
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print("❌ 본영상 렌더 실패\n", r.stderr[-500:]); sys.exit(1)
    print(f"     완료 ({get_duration(TEMP_MAIN)/60:.1f}분)")

    # ── B: intro.mp4 원본 그대로 + 본영상 → concat filter ────────────────────
    if has_intro:
        print("  [B] intro + 본영상 concat...")

        # intro.mp4는 이미 완성된 영상 — 오디오 일절 건드리지 않음
        all_inputs = ["-i", str(INTRO), "-i", str(TEMP_MAIN)]
        fc2 = [
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS}[iv]",
            "[0:a]asetpts=PTS-STARTPTS,"
            "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[ia]",
            f"[1:v]setsar=1,fps={FPS}[mv]",
            "[1:a]asetpts=PTS-STARTPTS[ma]",
            "[iv][ia][mv][ma]concat=n=2:v=1:a=1[vout][aout]",
        ]

        r = subprocess.run([
            FFMPEG, "-y", *all_inputs,
            "-filter_complex", "; ".join(fc2),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "h264_videotoolbox", "-b:v", "5M",
            "-c:a", "aac", "-b:a", "192k",
            "-r", str(FPS), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(out_path),
        ], capture_output=True, text=True)
        if r.returncode != 0:
            print("❌ concat 렌더 실패\n", r.stderr[-500:]); sys.exit(1)
        TEMP_MAIN.unlink(missing_ok=True)
    else:
        TEMP_MAIN.rename(out_path)

    actual = get_duration(out_path)
    print(f"✅ 완료: {out_path}  ({actual/60:.1f}분)")
    return out_path


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    if not VOICEOVER.exists():
        print(f"❌ 필수 파일 없음: {VOICEOVER}"); sys.exit(1)

    print("=" * 60)
    print("[1/5] 누락 클립 생성")
    print("=" * 60)
    audio_dur = build_missing_clips()

    print("\n" + "=" * 60)
    print("[2/5] 클립 정규화 + concat")
    print("=" * 60)
    scenes_concat = normalize_and_concat()

    print("\n" + "=" * 60)
    print("[3/5] BGM 합성")
    print("=" * 60)
    build_bgm(audio_dur)

    print("\n" + "=" * 60)
    print("[4/5] 자막 생성 (voiceover 기준 0초, shift 없음)")
    print("=" * 60)
    _timing_newer = TIMING_FILE.exists() and SUBS.exists() and TIMING_FILE.stat().st_mtime > SUBS.stat().st_mtime
    if not SUBS.exists() or SUBS.stat().st_mtime < VOICEOVER.stat().st_mtime or _timing_newer:
        generate_subtitles()

    print("\n" + "=" * 60)
    print("[5/5] 최종 렌더링 (인트로 / 본영상 독립 렌더 후 concat)")
    print("=" * 60)
    final_render(scenes_concat)


if __name__ == "__main__":
    main()
