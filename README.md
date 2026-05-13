# YouTube 롱폼 자동화 파이프라인

일본 롱폼 YouTube 채널을 위한 **영상 제작 전 과정 자동화** 시스템.
스크립트와 씬 이미지만 준비하면 자막·BGM·나레이션이 합성된 완성 영상이 나온다.

---

## 자동화 범위

| 단계          | 수동 (이전)              | 자동화 (현재)                                        |
| ------------- | ------------------------ | ---------------------------------------------------- |
| 나레이션 녹음 | 직접 녹음 또는 외주      | AivisSpeech TTS 자동 생성                            |
| 자막 작업     | 타임코드 수동 입력       | Whisper 음성 인식 → ASS 자동 생성                    |
| BGM 편집      | DAW에서 구간별 수동 편집 | `video_config.json` 존 설정 → 자동 크로스페이드 합성 |
| 씬 편집       | 영상 편집 소프트웨어     | 시퀀스 배열 입력 → 자동 배치 및 클립 생성            |
| 최종 렌더     | 인코딩 + 수동 합성       | `render.py` 한 번 실행으로 완성                      |

영상 1편 기준 **편집 시간 약 4~6시간 → 20분 이내**로 단축.

---

## 기술 스택

- **TTS**: AivisSpeech (VoiceVox 호환 로컬 API) — 화자 阿井田 茂（Mid）
- **자막**: faster-whisper (small 모델, ja) — 실제 음성 기준 타임스탬프 추출
- **BGM**: FFmpeg `acrossfade` 필터 — mood별 구간 자동 크로스페이드
- **인코딩**: FFmpeg + Apple VideoToolbox (`h264_videotoolbox`) — M1/M2 하드웨어 가속
- **자막 렌더링**: libass — ASS 형식, 히라기노 폰트
- **언어**: Python 3.11

---

## 워크플로

```
script.txt           →  gen_voiceover_vvox.py  →  voiceover.mp3
씬 이미지 (2×2 그리드)  →  정중앙 크롭              →  N.png × 68
video_config.json    →  scene_sequence 입력     →  render.py  →  YYYY-MM-DD_HHMMSS.mp4
```

### Step 1 — 스크립트 준비

`script.txt`에 일본어 낭독문 작성. TTS 자연스러운 호흡을 위해 `、`마다 줄바꿈.

```
千世は、山あいの宿場町に近い家で暮らしていた。
暮らしていた、と言っても、家族のようにではない。
その家の人々は、
千世を引き取ってやったのだと、
いつも口にしていた。
```

### Step 2 — 나레이션 생성

```bash
source venv/bin/activate
python3 gen_voiceover_vvox.py
# → output/audio/voiceover.mp3
```

**사전 조건**: AivisSpeech 앱 실행 (포트 10101 자동 활성화)

인트로 나레이션이 필요한 경우 별도 텍스트로 합성:

```bash
# 인트로 텍스트를 직접 API 호출로 합성 → output/audio/intro_narration.mp3
```

### Step 3 — 씬 이미지 크롭

외부 도구로 생성한 2×2 그리드 이미지를 `output/scenes/`에 `1-4.png`, `5-8.png` 형식으로 배치.

```bash
python3 - << 'EOF'
from PIL import Image
from pathlib import Path

scenes_dir = Path("output/scenes")
for grid in sorted(scenes_dir.glob("*-*.png"), key=lambda p: int(p.stem.split("-")[0])):
    start, end = map(int, grid.stem.split("-"))
    img = Image.open(grid)
    cx, cy = img.width // 2, img.height // 2
    for i, box in enumerate([
        (0,  0,  cx, cy),
        (cx, 0,  img.width, cy),
        (0,  cy, cx, img.height),
        (cx, cy, img.width, img.height),
    ]):
        img.crop(box).save(scenes_dir / f"{start + i}.png")
    grid.unlink()
EOF
```

> 그리드 배치 순서: 좌상=1번, 우상=2번, 좌하=3번, 우하=4번  
> 크롭 기준: 이미지 정중앙 (cx, cy) — 다른 씬과 픽셀이 절대 혼입되지 않음

### Step 4 — BGM 설정 및 시퀀스 입력 (`video_config.json`)

보이스오버 총 길이를 기준으로 시간대별 mood 지정, `scene_sequence`에 재생 순서 입력.

```json
{
  "tts": {
    "engine": "aivis",
    "speaker_id": 1310138980,
    "speed_scale": 0.9,
    "pitch_scale": 0.0,
    "intonation_scale": 1.0,
    "chunk_limit": 200
  },
  "bgm": {
    "volume": 0.5,
    "crossfade": 3.0,
    "zones": [
      { "end_sec": 40,   "mood": "japanese"  },
      { "end_sec": 320,  "mood": "nostalgic" },
      { "end_sec": 430,  "mood": "tense"     },
      { "end_sec": 700,  "mood": "sad"       },
      { "end_sec": 830,  "mood": "nostalgic" },
      { "end_sec": 920,  "mood": "healing"   },
      { "end_sec": 1150, "mood": "dramatic"  },
      { "end_sec": 1450, "mood": "sad"       },
      { "end_sec": 1750, "mood": "dramatic"  },
      { "end_sec": 1979, "mood": "hopeful"   }
    ]
  },
  "scene_sequence": [1, 2, 3, 1, 4, 5, ...]
}
```

- `scene_sequence`: 씬 번호 배열. 중복 허용, 원하는 순서대로 나열
- `zones`의 마지막 `end_sec`는 voiceover 실제 길이에 맞출 것
- **사용 가능한 mood**: `japanese` `warm` `tense` `sad` `dramatic` `hopeful` `healing` `nostalgic` `calm`

### Step 5 — 렌더링

```bash
python3 render.py
# → output/final/YYYY-MM-DD_HHMMSS.mp4
```

render.py 실행 흐름:

1. **누락 클립 생성** — `N.mp4` 없는 씬은 `N.png`에서 자동 생성 (남은 시간 균등 배분)
2. **정규화 + concat** — 전체 클립 CFR 강제, PTS 리셋 후 시퀀스 순서대로 이어붙임
3. **BGM 합성** — mood별 트랙을 구간에 맞게 자르고 crossfade 연결
4. **자막 생성** — Whisper로 voiceover.mp3 음성 인식 → `.ass` 자막 파일
5. **최종 렌더** — 본영상 렌더 후 `assets/intro.mp4` prepend

출력 파일명은 실행할 때마다 `YYYY-MM-DD_HHMMSS.mp4`로 고유하게 생성되며 **기존 파일을 덮어쓰지 않는다.**

---

## 폴더 구조

```
youtube-pipeline/
├── script.txt                  ← 낭독 스크립트 (매번 교체)
├── video_config.json           ← TTS·BGM·시퀀스 설정 (매번 조정)
├── gen_voiceover_vvox.py       ← AivisSpeech TTS 생성
├── render.py                   ← 렌더링 파이프라인 (수정 불필요)
│
├── assets/
│   ├── intro.mp4               ← 인트로 영상 (고정)
│   ├── bgm/
│   │   ├── japanese/  warm/  sad/  tense/  ...
│   └── fonts/
│
└── output/
    ├── scenes/                 ← N.png (1~68, 크롭 후 배치)
    ├── clips/                  ← N.mp4 (기존 + 자동 생성)
    │   └── _norm/              ← 정규화된 클립 캐시
    ├── audio/
    │   ├── voiceover.mp3
    │   ├── intro_narration.mp3
    │   └── bgm_composite.mp3
    ├── subtitles/
    │   └── subtitles.ass
    └── final/
        └── YYYY-MM-DD_HHMMSS.mp4  ← 최종 완성 영상 (실행마다 고유)
```

---

## 초기 설정

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# ffmpeg-full (libass 자막 렌더링 필수)
brew install ffmpeg-full
```

**AivisSpeech 설치**: [aivis-project.com](https://aivis-project.com) — 앱 실행 시 포트 10101 자동 활성화

---

## 트러블슈팅

| 증상                     | 원인                           | 해결                                                  |
| ------------------------ | ------------------------------ | ----------------------------------------------------- |
| 특정 시점 이후 까만 화면 | 일부 `N.mp4` 생성 누락         | `output/scenes/N.png` 파일 존재 여부 확인             |
| 자막 싱크 불일치         | 이전 보이스오버 기준 자막 캐시 | `output/subtitles/subtitles.ass` 삭제 후 재실행       |
| BGM 없음                 | `bgm_composite.mp3` 캐시 참조  | 해당 파일 삭제 후 재실행                              |
| VideoToolbox 오류        | Apple Silicon 아님             | `render.py` 내 `h264_videotoolbox` → `libx264`로 변경 |
| `No such filter: ass`    | 표준 ffmpeg (libass 미포함)    | `brew install ffmpeg-full`                            |

---

## 실제 제작 실적

파이프라인 가동 이후 **매일 1~2편** 페이스로 제작 중.

| 날짜       | 제목 (요약)                                                                        | 길이   |
| ---------- | ---------------------------------------------------------------------------------- | ------ |
| 2026-04-26 | —                                                                                  | 23.7분 |
| 2026-04-27 | —                                                                                  | 12.4분 |
| 2026-04-28 | —                                                                                  | 36.0분 |
| 2026-04-28 | —                                                                                  | 24.6분 |
| 2026-04-29 | —                                                                                  | 31.8분 |
| 2026-04-30 | 【実話風】雪の夜の誓い｜継母に捨てられた双子が、奪われた家を取り戻すまで          | 25.8분 |

> 5일간 총 **6편**, 누적 약 **154분** 분량 완성.  
> 제목 미기재 항목은 업로드 후 추가 예정.

---

## 라이선스 / 저작권

- **BGM**: [Kevin MacLeod (incompetech.com)](https://incompetech.com) — Creative Commons Attribution 4.0
- **TTS 음성**: AivisSpeech 이용 규약 준수
- **스크립트 / 영상**: 본 채널 오리지널 픽션 — 실재 인물·단체와 무관
