#!/usr/bin/env python3
"""
YouTube Pipeline Studio — Streamlit 로컬 웹앱
실행: streamlit run app.py
"""

import streamlit as st
import json
import subprocess
import time
import random
import os
from pathlib import Path

# ─── 경로 설정 ────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
META_FILE   = BASE / "metadata.json"
SCRIPT_FILE = BASE / "script.txt"
SCENE_FILE  = BASE / "scene_prompts.json"
CONFIG_FILE = BASE / "video_config.json"
ASSETS_DIR  = BASE / "assets"
OUTPUT_DIR  = BASE / "output"
LOG_FILE    = BASE / "pipeline_ui.log"

MOODS = ["healing", "calm", "warm", "hopeful", "sad", "dramatic"]
MOOD_KR = {
    "healing": "힐링 🌸", "calm": "잔잔 🌊", "warm": "따뜻 ☀️",
    "hopeful": "희망 ✨", "sad": "슬픔 🌧", "dramatic": "드라마 🎭",
}
IMAGE_STYLES = {
    "watercolor": "수채화 일러스트",
    "realistic":  "따뜻한 실사풍",
    "pencil":     "연필 스케치",
}
TTS_VOICES = {
    "kokoro": ["jf_gongitsune (여성)", "jm_kumo (남성)", "jf_alpha (여성2)", "jm_omega (남성2)"],
    "edge":   ["ja-JP-NanamiNeural (여성)", "ja-JP-KeitaNeural (남성)"],
}

# ─── 헬퍼: 파일 로드/저장 ─────────────────────────────────────────────────────
def load_metadata():
    if META_FILE.exists():
        return json.loads(META_FILE.read_text("utf-8"))
    return {"title": "", "description": "", "tags": []}

def save_metadata(data):
    META_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def load_script():
    return SCRIPT_FILE.read_text("utf-8") if SCRIPT_FILE.exists() else ""

def save_script(text):
    SCRIPT_FILE.write_text(text, "utf-8")

def load_scene_prompts():
    if SCENE_FILE.exists():
        return json.loads(SCENE_FILE.read_text("utf-8"))
    return []

def save_scene_prompts(data):
    SCENE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def load_video_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    return {}

def save_video_config(data):
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def parse_bulk_scenes(text: str) -> tuple[list[dict], list[str]]:
    """한 칸 입력 텍스트를 씬 목록으로 파싱.
    양식: 한 줄에  번호 | 무드 | 영어프롬프트
    무드 생략 시 calm, 번호 생략 시 순서대로
    """
    scenes, errors = [], []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        try:
            if len(parts) == 3:
                scene_num, mood, prompt_en = parts
                scene_num = int(scene_num)
            elif len(parts) == 2:
                # 번호 없이 무드 | 프롬프트
                mood, prompt_en = parts
                scene_num = len(scenes) + 1
            elif len(parts) == 1:
                prompt_en = parts[0]
                mood, scene_num = "calm", len(scenes) + 1
            else:
                errors.append(f"줄 {i}: 형식 오류 — {line[:60]}")
                continue
            mood = mood.lower()
            if mood not in MOODS:
                errors.append(f"줄 {i}: 무드 '{mood}' 불명 → calm으로 대체")
                mood = "calm"
            if not prompt_en:
                errors.append(f"줄 {i}: 프롬프트 비어 있음 → 건너뜀")
                continue
            scenes.append({"scene": scene_num, "time_range": "", "prompt_en": prompt_en, "mood": mood})
        except Exception as e:
            errors.append(f"줄 {i}: {e}")
    return scenes, errors


def get_bgm_files(mood: str) -> list[Path]:
    """assets/bgm/{mood}/ 폴더에서 mp3 파일 목록"""
    folder = ASSETS_DIR / "bgm" / mood
    folder.mkdir(parents=True, exist_ok=True)
    return sorted(folder.glob("*.mp3"))

def get_thumbnail_files() -> list[Path]:
    return sorted((OUTPUT_DIR / "thumbnails").glob("thumb_*.png"))

# ─── Streamlit 설정 ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YouTube Pipeline Studio",
    layout="wide",
    page_icon="🎬",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 20px; font-size: 15px; }
    .block-container { padding-top: 1.5rem; }
    .scene-row { background: #f8f9fa; border-radius: 8px; padding: 8px; margin: 4px 0; }
</style>
""", unsafe_allow_html=True)

st.title("🎬 YouTube Pipeline Studio")

tab1, tab2, tab3, tab4 = st.tabs(
    ["📝 스크립트 & 메타", "🎬 씬 빌더", "🎵 BGM 관리", "🚀 실행"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 스크립트 & 메타데이터
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    meta = load_metadata()
    vc   = load_video_config()
    script_text = load_script()

    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("📋 메타데이터")
        title       = st.text_input("제목 (일본어)", value=meta.get("title", ""), key="title_input")
        description = st.text_area("설명", value=meta.get("description", ""), height=140, key="desc_input")
        tags_text   = st.text_area(
            "태그 (줄바꿈으로 구분)",
            value="\n".join(meta.get("tags", [])),
            height=100, key="tags_input"
        )

    with col_right:
        st.subheader("⚙️ 영상 설정")

        tts_cfg = vc.get("tts", {})
        current_engine = tts_cfg.get("engine", "edge")
        engine_idx = 0 if current_engine == "kokoro" else 1
        engine = st.selectbox("TTS 엔진", ["kokoro (Kokoro — 무료·상업)", "edge (Edge TTS)"],
                              index=engine_idx, key="engine_sel")
        engine_key = engine.split(" ")[0]

        voice_list = TTS_VOICES.get(engine_key, TTS_VOICES["kokoro"])
        current_voice = tts_cfg.get("voice", voice_list[0].split(" ")[0])
        voice_idx = next((i for i, v in enumerate(voice_list) if v.startswith(current_voice)), 0)
        voice_sel = st.selectbox("보이스", voice_list, index=voice_idx, key="voice_sel")
        voice_key = voice_sel.split(" ")[0]

        img_cfg = vc.get("image", {})
        style_keys = list(IMAGE_STYLES.keys())
        current_style = img_cfg.get("style", "watercolor")
        style_idx = style_keys.index(current_style) if current_style in style_keys else 0
        style_sel = st.selectbox(
            "이미지 스타일",
            [f"{k} ({v})" for k, v in IMAGE_STYLES.items()],
            index=style_idx, key="style_sel"
        )
        style_key = style_sel.split(" ")[0]

        bgm_vol = st.slider("BGM 볼륨", 0.0, 1.0,
                            float(vc.get("bgm", {}).get("volume", 0.33)), 0.05, key="bgm_vol")
        tts_rate = st.select_slider("TTS 속도", options=["-15%","-12%","-10%","-8%","-5%","0%"],
                                    value=tts_cfg.get("rate", "-8%"), key="tts_rate")
        scene_dur = st.slider("씬 전환 간격 (초)", 10, 60,
                              int(vc.get("image", {}).get("scene_duration", 17)), 1,
                              key="scene_dur", help="미사용 — 씬 개수로 자동 분배됨 (오디오 길이 ÷ 씬 수)", disabled=True)

    st.divider()
    st.subheader("✍️ 나레이션 스크립트")
    script_input = st.text_area("", value=script_text, height=380, key="script_input",
                                label_visibility="collapsed",
                                help="챕터 구분: 【第1章：タイトル】 또는 ━━━ 사용")

    st.subheader("🖼️ 썸네일 설정 (3장)")
    thumb_cfg    = vc.get("thumbnail", {})
    t_texts      = thumb_cfg.get("texts",    ["", "", ""])
    t_pos        = thumb_cfg.get("positions", ["bottom", "center", "bottom"])
    t_prompts    = thumb_cfg.get("prompts",  ["", "", ""])
    pos_opts     = ["bottom", "center", "top"]
    t_cols       = st.columns(3)
    t_vals, p_vals, pr_vals = [], [], []
    for i, col in enumerate(t_cols):
        with col:
            txt = t_texts[i]   if i < len(t_texts)   else ""
            pos = t_pos[i]     if i < len(t_pos)      else pos_opts[i % len(pos_opts)]
            prm = t_prompts[i] if i < len(t_prompts)  else ""
            # 현재 썸네일 이미지 미리보기
            th_path = OUTPUT_DIR / "thumbnails" / f"thumb_{i+1}.png"
            if th_path.exists():
                try:
                    col.image(str(th_path), width='stretch')
                except Exception:
                    col.warning("이미지 손상됨")
            t_vals.append(st.text_input(f"오버레이 텍스트 {i+1}", value=txt, key=f"thumb_txt_{i}"))
            p_vals.append(st.selectbox(f"텍스트 위치 {i+1}", pos_opts,
                                       index=pos_opts.index(pos) if pos in pos_opts else 0,
                                       key=f"thumb_pos_{i}"))
            pr_vals.append(st.text_area(f"이미지 프롬프트 {i+1} (영어)", value=prm,
                                        height=100, key=f"thumb_pr_{i}",
                                        help="Pollinations AI에 전달할 이미지 생성 프롬프트"))

    if st.button("💾 전체 저장", type="primary", key="save_all"):
        meta["title"]       = title
        meta["description"] = description
        meta["tags"]        = [t.strip() for t in tags_text.split("\n") if t.strip()]
        save_metadata(meta)
        save_script(script_input)
        vc.setdefault("tts", {}).update({
            "engine": engine_key, "voice": voice_key, "rate": tts_rate,
        })
        vc.setdefault("image", {})["style"]         = style_key
        vc["image"]["scene_duration"]               = scene_dur
        vc.setdefault("bgm", {})["volume"]          = bgm_vol
        vc.setdefault("thumbnail", {}).update({
            "texts": t_vals, "positions": p_vals,
            "prompts": [p for p in pr_vals],
        })
        save_video_config(vc)
        st.success("✅ 저장 완료")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 씬 빌더
# ═══════════════════════════════════════════════════════════════════════════════
def _chars_to_text(chars: dict) -> str:
    return "\n".join(f"{{{k}}} = {v}" for k, v in chars.items())

def _text_to_chars(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        token, _, desc = line.partition("=")
        token = token.strip().strip("{} ")
        desc  = desc.strip()
        if token and desc:
            result[token] = desc
    return result


with tab2:
    scenes = load_scene_prompts()

    st.subheader(f"🎬 씬 빌더 — {len(scenes)}개 씬")

    # ── 등장인물 토큰 정의 ───────────────────────────────────────────────────
    vc_for_chars = load_video_config()
    existing_chars = vc_for_chars.get("image", {}).get("characters", {})
    CHAR_PLACEHOLDER = """\
{fumie} = elderly Japanese woman, 72 years old, gentle face, short dark-brown hair, neat cardigan, photorealistic
{akio} = elderly Japanese man, 78 years old, short gray hair, black hat, gray cardigan, photorealistic"""

    with st.expander("🧑 등장인물 토큰", expanded=(not existing_chars)):
        st.caption("씬 프롬프트에서 `{이름}` 으로 참조. 형식: `{토큰명} = 영어 묘사`")
        char_text_input = st.text_area(
            "", value=_chars_to_text(existing_chars),
            placeholder=CHAR_PLACEHOLDER,
            height=160, key="char_token_input",
            label_visibility="collapsed",
        )
        if st.button("💾 캐릭터 저장", key="save_chars"):
            parsed_chars = _text_to_chars(char_text_input)
            if parsed_chars:
                vc_now = load_video_config()
                vc_now.setdefault("image", {})["characters"] = parsed_chars
                save_video_config(vc_now)
                st.success(f"✅ {len(parsed_chars)}명 저장 완료 — 토큰: " +
                           ", ".join(f"`{{{k}}}`" for k in parsed_chars))
                st.rerun()
            else:
                st.error("파싱된 캐릭터가 없습니다. 형식을 확인하세요.")

    st.divider()

    # ── 한 번에 씬 일괄 입력 ────────────────────────────────────────────────
    BULK_PLACEHOLDER = """\
# 양식: 번호 | 무드 | 영어 이미지 프롬프트
# 번호 생략 가능 (순서대로), 무드: healing / calm / warm / hopeful / sad / dramatic
# 예시:
1 | calm | elderly Japanese man sitting alone by the window at dusk, quiet apartment interior
2 | warm | two seniors sharing a simple meal at a small kitchen table, warm soft light
3 | hopeful | elderly couple walking side by side in an early spring park, cherry blossoms"""

    with st.expander("📋 씬 일괄 입력", expanded=(len(scenes) == 0)):
        st.caption("한 줄에 씬 하나씩 입력: `번호 | 무드 | 영어프롬프트`  (번호 생략 가능)")
        bulk_text = st.text_area("씬 목록", placeholder=BULK_PLACEHOLDER,
                                 height=280, key="bulk_scene_input",
                                 label_visibility="collapsed")
        b_col1, b_col2 = st.columns([1, 4])
        with b_col1:
            overwrite_bulk = st.checkbox("기존 씬 교체", value=True, key="bulk_overwrite")
        with b_col2:
            if st.button("📥 씬 적용", type="primary", key="bulk_apply"):
                if not bulk_text.strip():
                    st.error("내용을 입력하세요.")
                else:
                    new_scenes, errs = parse_bulk_scenes(bulk_text)
                    if errs:
                        for e in errs:
                            st.warning(e)
                    if new_scenes:
                        result = new_scenes if overwrite_bulk else (scenes + new_scenes)
                        save_scene_prompts(result)
                        st.success(f"✅ {len(new_scenes)}개 씬 적용 완료!")
                        st.rerun()
                    else:
                        st.error("파싱된 씬이 없습니다. 양식을 확인하세요.")

    st.divider()
    btn_row = st.columns([1, 1, 6])
    if btn_row[0].button("➕ 씬 추가", key="add_scene"):
        scenes.append({
            "scene": len(scenes) + 1,
            "time_range": "",
            "prompt_en": "",
            "mood": "calm",
        })
        save_scene_prompts(scenes)
        st.rerun()
    if btn_row[1].button("🗑️ 전체 삭제", key="clear_all_scenes"):
        st.session_state["confirm_clear"] = True
    if st.session_state.get("confirm_clear"):
        st.warning("정말 모든 씬을 삭제할까요?")
        cc1, cc2 = st.columns([1, 6])
        if cc1.button("✅ 확인", key="confirm_clear_yes"):
            save_scene_prompts([])
            st.session_state["confirm_clear"] = False
            st.rerun()
        if cc2.button("취소", key="confirm_clear_no"):
            st.session_state["confirm_clear"] = False
            st.rerun()

    updated_scenes = []
    for i, s in enumerate(scenes):
        with st.expander(
            f"씬 {s.get('scene', i+1)} — {s.get('time_range', '')}  |  무드: {MOOD_KR.get(s.get('mood', 'calm'), s.get('mood', 'calm'))}",
            expanded=False
        ):
            c1, c2, c3 = st.columns([1, 6, 2])
            with c1:
                sc_num = st.number_input("번호", value=int(s.get("scene", i+1)),
                                         min_value=1, key=f"sn_{i}")
                tr = st.text_input("시간", value=s.get("time_range", ""), key=f"tr_{i}")
            with c2:
                pr = st.text_area("이미지 프롬프트 (영어)", value=s.get("prompt_en", ""),
                                  height=100, key=f"pr_{i}")
            with c3:
                mood_list = list(MOOD_KR.keys())
                cur_mood  = s.get("mood", "calm")
                mi = mood_list.index(cur_mood) if cur_mood in mood_list else 1
                md = st.selectbox("BGM 무드", mood_list,
                                  format_func=lambda x: MOOD_KR[x],
                                  index=mi, key=f"md_{i}")
                # 해당 무드 이미지 미리보기
                scene_img = OUTPUT_DIR / "scenes" / f"scene_{int(s.get('scene', i+1))}.png"
                if scene_img.exists():
                    try:
                        st.image(str(scene_img), caption=f"scene_{int(s.get('scene', i+1))}.png",
                                 width='stretch')
                    except Exception:
                        st.warning("이미지 손상됨")
                if st.button("🗑️ 삭제", key=f"del_{i}"):
                    scenes.pop(i)
                    save_scene_prompts(scenes)
                    st.rerun()
            updated_scenes.append({
                "scene": int(sc_num), "time_range": tr,
                "prompt_en": pr, "mood": md,
            })

    if st.button("💾 씬 저장", type="primary", key="save_scenes"):
        save_scene_prompts(updated_scenes)
        st.success(f"✅ {len(updated_scenes)}개 씬 저장 완료")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — BGM 관리 (미리듣기 + 교체)
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🎵 BGM 관리")

    col_mood, col_upload = st.columns([1, 2])

    with col_mood:
        selected_mood = st.selectbox(
            "무드 선택", MOODS,
            format_func=lambda x: MOOD_KR[x],
            key="bgm_mood_sel"
        )

    with col_upload:
        st.caption(f"📂 `assets/bgm/{selected_mood}/` 폴더에 MP3 업로드")
        uploaded = st.file_uploader(
            "MP3 파일 업로드", type=["mp3"], accept_multiple_files=True,
            key=f"upload_{selected_mood}"
        )
        if uploaded:
            dest_dir = ASSETS_DIR / "bgm" / selected_mood
            dest_dir.mkdir(parents=True, exist_ok=True)
            for f in uploaded:
                dest = dest_dir / f.name
                dest.write_bytes(f.read())
            st.success(f"✅ {len(uploaded)}개 파일 업로드 완료")
            st.rerun()

    st.divider()

    bgm_files = get_bgm_files(selected_mood)
    if not bgm_files:
        st.info(f"아직 {MOOD_KR[selected_mood]} 무드 BGM이 없습니다. 위에서 업로드하거나 `bgm_downloader.py`를 실행하세요.")
        st.code(f"python3 bgm_downloader.py --mood {selected_mood}")
    else:
        st.caption(f"{len(bgm_files)}개 트랙")
        for fp in bgm_files:
            row_c1, row_c2, row_c3 = st.columns([3, 1, 6])
            with row_c1:
                st.write(f"🎵 **{fp.stem}**")
                size_kb = fp.stat().st_size // 1024
                st.caption(f"{size_kb:,} KB")
            with row_c2:
                if st.button("🗑️", key=f"del_bgm_{fp}"):
                    fp.unlink()
                    st.rerun()
            with row_c3:
                st.audio(str(fp))

    st.divider()
    st.subheader("📦 BGM 자동 다운로드")
    st.caption("incompetech.com (CC BY 4.0 — 유튜브 수익화 가능) 에서 무드별 BGM 다운로드")
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        dl_mood = st.selectbox("다운로드할 무드", ["전체"] + MOODS,
                               format_func=lambda x: "전체 무드" if x == "전체" else MOOD_KR[x],
                               key="dl_mood")
    with dl_col2:
        st.write("")
        st.write("")
        if st.button("⬇️ 다운로드 시작", key="dl_btn"):
            mood_arg = "" if dl_mood == "전체" else f"--mood {dl_mood}"
            cmd = f"python3 {BASE}/bgm_downloader.py {mood_arg}"
            with st.spinner("다운로드 중..."):
                result = subprocess.run(cmd, shell=True, cwd=str(BASE),
                                        capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                st.success("✅ 다운로드 완료")
            else:
                st.error(f"오류: {result.stderr[-500:]}")
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — 실행
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🚀 영상 생성")

    # 썸네일 미리보기
    thumbs = get_thumbnail_files()
    if thumbs:
        st.subheader("🖼️ 썸네일 선택")
        thumb_cols = st.columns(len(thumbs))
        for i, (col, tp) in enumerate(zip(thumb_cols, thumbs)):
            with col:
                try:
                    col.image(str(tp), caption=tp.name, width='stretch')
                except Exception:
                    col.warning(f"{tp.name} 손상됨")
        thumb_choice = st.radio("사용할 썸네일", [1, 2, 3], horizontal=True, key="thumb_choice")
    else:
        thumb_choice = 1

    st.divider()

    # 실행 옵션
    st.subheader("⚙️ 실행 옵션")
    opt_cols = st.columns(5)
    skip_images = opt_cols[0].checkbox("이미지 스킵", key="skip_img")
    skip_tts    = opt_cols[1].checkbox("TTS 스킵",   key="skip_tts")
    reuse_subs  = opt_cols[2].checkbox("자막 재사용", key="reuse_subs",
                                       help="기존 subtitles.ass 재사용 (Whisper 건너뜀)")
    skip_upload = opt_cols[3].checkbox("업로드 스킵", value=True, key="skip_upload")
    no_clean    = opt_cols[4].checkbox("기존 파일 유지", value=True, key="no_clean")

    # 최종 출력 확인
    final_dir = OUTPUT_DIR / "final"
    final_files = sorted(final_dir.glob("*.mp4")) if final_dir.exists() else []
    if final_files:
        latest = final_files[-1]
        st.info(f"📹 최근 생성 영상: **{latest.name}** ({latest.stat().st_size // 1024 // 1024} MB, {time.strftime('%H:%M', time.localtime(latest.stat().st_mtime))})")

    st.divider()

    # 실행 상태 관리
    if "pipeline_proc" not in st.session_state:
        st.session_state.pipeline_proc = None
        st.session_state.pipeline_log  = []

    # 실행 버튼
    btn_col1, btn_col2 = st.columns([2, 1])
    with btn_col1:
        start_btn = st.button("🚀 영상 생성 시작", type="primary", key="start_btn",
                              disabled=(st.session_state.pipeline_proc is not None))
    with btn_col2:
        stop_btn = st.button("⛔ 중단", key="stop_btn",
                             disabled=(st.session_state.pipeline_proc is None))

    if start_btn:
        flags = ["--script", "script.txt", "--thumb", str(thumb_choice)]
        if skip_images:  flags.append("--skip-images")
        if skip_tts:     flags.append("--skip-tts")
        if reuse_subs:   flags.append("--reuse-subs")
        if skip_upload:  flags.append("--skip-upload")
        if no_clean:     flags.append("--no-clean")

        LOG_FILE.unlink(missing_ok=True)
        LOG_FILE.write_text("")

        proc = subprocess.Popen(
            ["python3", "-u", "run_pipeline.py"] + flags,
            stdout=open(LOG_FILE, "w"),
            stderr=subprocess.STDOUT,
            cwd=str(BASE),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        st.session_state.pipeline_proc = proc
        st.session_state.pipeline_log  = []
        st.rerun()

    if stop_btn and st.session_state.pipeline_proc:
        st.session_state.pipeline_proc.terminate()
        st.session_state.pipeline_proc = None
        st.warning("⛔ 파이프라인 중단됨")

    # 진행 상황 표시
    if st.session_state.pipeline_proc is not None:
        proc = st.session_state.pipeline_proc
        status = proc.poll()

        log_content = LOG_FILE.read_text("utf-8") if LOG_FILE.exists() else ""
        lines = [l for l in log_content.splitlines() if l.strip()]

        # 진행 단계 파싱
        step_done = sum(1 for l in lines if "✅" in l)
        total_steps_hint = 4  # images, tts, render, upload
        progress_val = min(step_done / max(total_steps_hint * 5, 1), 0.99)

        if status is None:
            st.info("⏳ 실행 중...")
            st.progress(progress_val)
        elif status == 0:
            st.success("✅ 완료!")
            st.progress(1.0)
            st.session_state.pipeline_proc = None
            # 최신 mp4 표시
            new_files = sorted(final_dir.glob("*.mp4")) if final_dir.exists() else []
            if new_files:
                st.success(f"📹 생성 완료: **{new_files[-1].name}** ({new_files[-1].stat().st_size // 1024 // 1024} MB)")
        else:
            st.error(f"❌ 오류 발생 (exit code {status})")
            st.session_state.pipeline_proc = None

        # 로그 출력
        log_placeholder = st.empty()
        display_lines = lines[-50:] if lines else ["(로그 대기 중...)"]
        log_placeholder.code("\n".join(display_lines), language=None)

        # 실행 중이면 2초마다 새로고침
        if status is None:
            time.sleep(2)
            st.rerun()

    elif LOG_FILE.exists() and LOG_FILE.stat().st_size > 0:
        # 이전 실행 로그 표시
        with st.expander("📄 마지막 실행 로그"):
            st.code(LOG_FILE.read_text("utf-8")[-5000:], language=None)
