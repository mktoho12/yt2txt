"""ElevenLabs Scribe（音声→テキスト API）による文字起こし。"""

import os
import re
from pathlib import Path

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL_ID = "scribe_v2"
KEY_FILE = Path.home() / ".config/elevenlabs/api_key"
KEY_ENV = "ELEVENLABS_API_KEY"

# この秒数以上の無音があれば改行する
PAUSE_BREAK_SEC = 1.5
# 全角の文末記号の後、または半角の文末記号＋空白の後で改行する
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+")
_REPEAT_RE = re.compile(r"(.{1,12}?)\1{4,}", re.S)


class TranscribeError(Exception):
    pass


def load_api_key() -> str | None:
    """環境変数 ELEVENLABS_API_KEY、なければ ~/.config/elevenlabs/api_key から読む。"""
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    if KEY_FILE.is_file():
        return KEY_FILE.read_text().strip() or None
    return None


def collapse_repeats(text: str) -> str:
    """同じ短い句が5回以上続いたら3回に縮める。

    音楽などで Scribe が「Oh。Oh。Oh。…」のように同じ語を延々と出すことがあるため。
    """
    return _REPEAT_RE.sub(lambda m: m.group(1) * 3, text)


def words_to_text(words: list[dict]) -> str:
    """words 配列を、文末か長い無音で改行したテキストにする。

    日本語はほぼ1文字ずつ返ってくるので、そのまま並べると改行のない1行になってしまう。
    句点は「？Hey,」のように語の先頭に付いて返ることもあるため、つないだ後の文字列で区切る。
    """
    chunks: list[str] = []
    buf = ""
    last_end: float | None = None
    for w in words:
        kind = w.get("type")
        if kind == "audio_event":
            continue
        text = w.get("text", "")
        if kind == "spacing":
            buf += text
            continue
        start = w.get("start")
        if buf.strip() and last_end is not None and start is not None \
                and start - last_end >= PAUSE_BREAK_SEC:
            chunks.append(buf)
            buf = ""
        buf += text
        last_end = w.get("end", last_end)
    chunks.append(buf)

    lines = []
    for chunk in chunks:
        for line in _SENTENCE_SPLIT_RE.split(collapse_repeats(chunk)):
            if line.strip():
                lines.append(line.strip())
    return "\n".join(lines)


def transcribe(audio_path: str, api_key: str) -> tuple[str, str]:
    """音声を文字起こしし、(テキスト, 取得元の説明) を返す。"""
    import requests

    with open(audio_path, "rb") as f:
        try:
            resp = requests.post(
                API_URL,
                headers={"xi-api-key": api_key},
                data={
                    "model_id": MODEL_ID,
                    "tag_audio_events": "false",
                    "timestamps_granularity": "word",
                },
                files={"file": (os.path.basename(audio_path), f)},
                timeout=1800,
            )
        except requests.RequestException as e:
            raise TranscribeError(f"ElevenLabs への接続に失敗しました: {e}") from None
    if resp.status_code != 200:
        raise TranscribeError(
            f"ElevenLabs API がエラーを返しました（HTTP {resp.status_code}）:\n  {resp.text[:500]}"
        )
    data = resp.json()
    text = words_to_text(data.get("words") or []) or (data.get("text") or "").strip()
    lang = data.get("language_code") or "?"
    return text, f"ElevenLabs {MODEL_ID}・言語 {lang}"
