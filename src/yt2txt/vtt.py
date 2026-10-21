"""WebVTT をプレーンテキストに変換する。"""

import html
import re

_TIMING_RE = re.compile(r"^\s*(\d{1,2}:)?\d{2}:\d{2}\.\d{3}\s+-->\s+")
_TAG_RE = re.compile(r"<[^>]*>")


def vtt_to_text(vtt: str) -> str:
    """タイムスタンプ・タグ・重複行を除去して1行1字幕のテキストにする。

    YouTube の自動生成字幕は、前のキューの行が次のキューに繰り返し現れる
    （ロールアップ表示）ため、直前に出力した行と同じ行は捨てる。
    """
    lines: list[str] = []
    for block in re.split(r"\r?\n\s*\r?\n", vtt.replace("﻿", "")):
        block_lines = block.splitlines()
        timing_idx = next(
            (i for i, line in enumerate(block_lines) if _TIMING_RE.match(line)), None
        )
        # ヘッダ・NOTE・STYLE・REGION などタイミング行を持たないブロックは本文ではない
        if timing_idx is None:
            continue
        for raw in block_lines[timing_idx + 1 :]:
            text = html.unescape(_TAG_RE.sub("", raw))
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                lines.append(text)

    deduped: list[str] = []
    for line in lines:
        if deduped and deduped[-1] == line:
            continue
        deduped.append(line)
    return "\n".join(deduped)
