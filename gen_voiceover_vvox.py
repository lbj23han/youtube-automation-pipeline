#!/usr/bin/env python3
"""
script.txt → output/audio/voiceover.mp3  (VoiceVox Engine API)

사전 준비:
  Docker 방식 (권장):
    docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest

  앱 방식:
    https://voicevox.hiroshiba.jp/ 에서 VOICEVOX 다운로드 후 실행
    (앱 실행만 해두면 50021 포트에서 API 자동 시작)

화자 ID (SPEAKER_ID):
  앱 켜진 상태에서 확인:  curl http://localhost:50021/speakers | python3 -m json.tool
  주요 여성 내레이션 화자:
    3  : 春日部つむぎ (ノーマル)  — 따뜻하고 자연스러운 여성
    8  : WhiteCUL    (ノーマル)   — 맑고 차분한 여성
    14 : 冥鳴ひまり  (ノーマル)   — 부드러운 여성
    58 : 栗田まろん  (ノーマル)   — 성숙한 여성 내레이션
  주요 남성 내레이션 화자:
    13 : 青山龍星    (ノーマル)   — 깊고 차분한 남성
"""

import re, json, time, subprocess
import urllib.request, urllib.parse, urllib.error
from pathlib import Path

# ── 설정 ─────────────────────────────────────────────────────────────────────
_VC          = json.loads((Path(__file__).parent / "video_config.json").read_text())
SPEAKER_ID   = _VC["tts"]["speaker_id"]
SPEED_SCALE  = _VC["tts"]["speed_scale"]
PITCH_SCALE  = _VC["tts"]["pitch_scale"]
INTONATION   = _VC["tts"]["intonation_scale"]
VVOX_URL     = "http://localhost:10101"
CHUNK_LIMIT  = _VC["tts"]["chunk_limit"]

# ── 오독 교정 사전 (TTS 전송용, 자막에는 영향 없음) ────────────────────────────
# 확인된 오독 or 오독 가능성 높은 단어 추가
TTS_CORRECTIONS = {
    "御用馬":   "ごようま",
    "御救米":   "おすくいまい",
    "御救小屋": "おすくいごや",
    "御厩":     "おうまや",
    "遠島":     "えんとう",
    "算木":     "さんぎ",
    "馬廻組":   "うままわりぐみ",
    "御馬方":   "おうまかた",
    "御馬改め": "おうまあらため",
    # マタギ物語 추가
    "勢子":     "せこ",
    "仁蔵":     "にぞう",
    "山廻り":   "やままわり",
    # 龍神물語 추가
    "錫杖":     "しゃくじょう",
    "梓巫女":   "あずさみこ",
    "梓弓":     "あずさゆみ",
    "人身御供": "ひとみごくう",
    "白龍湖":   "はくりゅうこ",
    "龍神池":   "りゅうじんいけ",
    "月隠れ":   "つきがくれ",
    # 春日屋おたま 추가
    "春日屋":   "かすがや",
    "有平糖":   "ありへいとう",
    "有平":     "ありへい",
    "薯蕷の皮": "じょうよのかわ",
    "薯蕷":     "じょうよ",
    "練り切り": "ねりきり",
    "葛":       "くず",
    # からたちの花 추가
    "野茨":     "のいばら",
    "御用庭師": "ごようにわし",
    "青物問屋": "あおものとんや",
    "棘垣":     "とげがき",
    "藤兵衛":   "とうべえ",
    "茂吉":     "もきち",
    # 霧の底 추가
    "霧兵衛":   "きりびょうえ",
    "太物屋":   "ふとものや",
    "名主":     "なぬし",
    "五人組":   "ごにんぐみ",
    "組頭":     "くみがしら",
    "外掛け":   "そとがけ",
    "久蔵":     "きゅうぞう",
    # 榊原惣右衛門 추가
    "庭訓往来": "ていきんおうらい",
    "榊原":     "さかきばら",
    "惣右衛門": "そうえもん",
    "仙太":     "せんた",
    "佐吉":     "さきち",
    "大輔":     "だいすけ",
    "富士子":   "ふじこ",
    "小夜":     "さよ",
    "閂":       "かんぬき",
    "蒔絵":     "まきえ",
    "薬箪笥":   "くすりだんす",
    "夕餉":     "ゆうげ",
    "算盤":     "そろばん",
    "手間賃":   "てまちん",
    "勘定方":   "かんじょうかた",
    "根付":     "ねつけ",
    "燭台":     "しょくだい",
    "組紐":     "くみひも",
    "家督":     "かとく",
    "在の町":   "ざいのまち",
    # お結（薩摩の女）추가
    # 인물명
    "お結":         "おゆい",
    "お辰":         "おたつ",
    "直之":         "なおゆき",
    # 지명·시대
    "安芸国":       "あきのくに",
    "享保":         "きょうほう",
    # 농업·생활 용어
    "唐芋":         "からいも",
    "米櫃":         "こめびつ",
    "扶持":         "ふち",
    "畔":           "あぜ",
    "畝":           "うね",
    "水口":         "みずぐち",
    "腐葉":         "ふよう",
    "節くれ立ち":   "ふしくれだち",
    "種芋":         "たねいも",
    "籾":           "もみ",
    "稲束":         "いなたば",
    "嫁入り荷":     "よめいりに",
    "藁":           "わら",
    # 자연·감각 표현
    "海風":         "うみかぜ",
    "雫":           "しずく",
    "斑":           "まだら",
    "欠片":         "かけら",
    "虚しく":       "むなしく",
    # 역사·사회 용어
    "代官所":       "だいかんじょ",
    "庄屋":         "しょうや",
    "父祖":         "ふそ",
    "年貢":         "ねんぐ",
    "百姓":         "ひゃくしょう",
    # 실내·도구
    "囲炉裏端":     "いろりばた",
    "灯明":         "とうみょう",
    "乳飲み子":     "ちのみご",
    # おのぶ（港町の塩）추가
    # 인물명
    "平兵衛門":     "へいべえもん",
    "清兵衛":       "せいべえ",
    "お咲":         "おさき",
    "五郎蔵":       "ごろうぞう",
    "弥八":         "やはち",
    # 지명
    "赤穂":         "あこう",
    # 에도시대 상업·역사 용어
    "廻船":         "かいせん",
    "大店":         "おおだな",
    "薬種":         "やくしゅ",
    "仲買":         "なかがい",
    "金子":         "きんす",
    "船主":         "ふなぬし",
    "人足":         "にんそく",
    "付け届け":     "つけとどけ",
    "舅":           "しゅうと",
    "施療所":       "せりょうじょ",
    "薬包":         "やくほう",
    # 신체·의료
    "癪":           "しゃく",
    "脂汗":         "あぶらあせ",
    "踵":           "かかと",
    # 생활 용품
    "駕籠":         "かご",
    "杓子":         "しゃくし",
    "笊":           "ざる",
    "甕":           "かめ",
    # 기타
    "施し":         "ほどこし",
}

def _apply_tts_corrections(text: str) -> str:
    for kanji, yomi in TTS_CORRECTIONS.items():
        text = text.replace(kanji, yomi)
    return text

BASE      = Path(__file__).parent
AUDIO_DIR = BASE / "output/audio"
SCRIPT    = BASE / "script.txt"
OUT       = AUDIO_DIR / "voiceover.mp3"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ── 청크 길이 측정 ───────────────────────────────────────────────────────────
def _get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# ── VoiceVox 서버 체크 ────────────────────────────────────────────────────────
def check_server():
    try:
        urllib.request.urlopen(f"{VVOX_URL}/version", timeout=3)
        return True
    except Exception:
        return False


# ── TTS (한 청크) ─────────────────────────────────────────────────────────────
def synthesize(text: str, out_wav: Path):
    # 1) audio_query (오독 교정 텍스트 사용, 자막용 원문과 분리)
    tts_text = _apply_tts_corrections(text)
    params = urllib.parse.urlencode({"text": tts_text, "speaker": SPEAKER_ID})
    req = urllib.request.Request(
        f"{VVOX_URL}/audio_query?{params}", method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        query = json.loads(resp.read())

    # 파라미터 덮어쓰기
    query["speedScale"]      = SPEED_SCALE
    query["pitchScale"]      = PITCH_SCALE
    query["intonationScale"] = INTONATION

    # 2) synthesis
    body = json.dumps(query).encode()
    params2 = urllib.parse.urlencode({"speaker": SPEAKER_ID})
    req2 = urllib.request.Request(
        f"{VVOX_URL}/synthesis?{params2}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req2, timeout=120) as resp2:
        out_wav.write_bytes(resp2.read())


# ── 스크립트 → 청크 분리 ──────────────────────────────────────────────────────
def split_script(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    paragraphs = re.split(r'\n\s*\n', text)
    sentences = []
    for para in paragraphs:
        parts = re.split(r'(?<=[。！？\n])', para)
        sentences.extend(s.strip() for s in parts if s.strip())

    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > CHUNK_LIMIT:
            if current:
                chunks.append(current.strip())
            current = s
        else:
            current += s
    if current.strip():
        chunks.append(current.strip())
    return chunks


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    if not check_server():
        print("❌ VoiceVox 엔진이 실행되지 않았어요.")
        print()
        print("  Docker 방식 (터미널 새 탭에서 실행):")
        print("    docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-ubuntu20.04-latest")
        print()
        print("  앱 방식:")
        print("    https://voicevox.hiroshiba.jp/ → VOICEVOX 다운로드 후 실행")
        return

    chunks = split_script(SCRIPT)
    print(f"화자 ID: {SPEAKER_ID} | 청크: {len(chunks)}개 | 속도: {SPEED_SCALE}")

    chunk_paths, timing_data = [], []
    cursor = 0.0
    for i, chunk in enumerate(chunks, 1):
        wav = AUDIO_DIR / f"vvox_chunk_{i:03d}.wav"
        mp3 = AUDIO_DIR / f"vvox_chunk_{i:03d}.mp3"
        print(f"  [{i}/{len(chunks)}] {len(chunk)}자...", end=" ", flush=True)
        try:
            synthesize(chunk, wav)
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-q:a", "2", str(mp3)],
                capture_output=True, check=True,
            )
            wav.unlink(missing_ok=True)
            dur = _get_duration(mp3)
            timing_data.append({"text": chunk, "start": round(cursor, 3), "end": round(cursor + dur, 3)})
            cursor += dur
            chunk_paths.append(str(mp3))
            print("완료")
        except Exception as e:
            print(f"❌ {e}")

    if not chunk_paths:
        print("❌ 생성된 청크가 없어요."); return

    if len(chunk_paths) == 1:
        Path(chunk_paths[0]).rename(OUT)
    else:
        list_file = AUDIO_DIR / "vvox_chunks.txt"
        list_file.write_text(
            "\n".join(f"file '{Path(p).resolve()}'" for p in chunk_paths),
            encoding="utf-8",
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", str(OUT)],
            capture_output=True, check=True,
        )
        list_file.unlink(missing_ok=True)
        for p in chunk_paths:
            Path(p).unlink(missing_ok=True)

    TIMING_FILE = AUDIO_DIR / "chunks_timing.json"
    TIMING_FILE.write_text(json.dumps(timing_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ {OUT}")
    print(f"✅ {TIMING_FILE}")


if __name__ == "__main__":
    main()
