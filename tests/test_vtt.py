from yt2txt.cli import pick_subtitle, sanitize_filename
from yt2txt.vtt import vtt_to_text

AUTO_VTT = """WEBVTT
Kind: captions
Language: ja

00:00:00.000 --> 00:00:02.000 align:start position:0%

こんにちは<00:00:00.500><c>皆さん</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
こんにちは皆さん


00:00:02.010 --> 00:00:04.000 align:start position:0%
こんにちは皆さん
今日は<00:00:02.500><c>天気</c><00:00:03.000><c>です</c>

00:00:04.000 --> 00:00:04.010 align:start position:0%
今日は天気です

"""

MANUAL_VTT = """WEBVTT

NOTE これはコメント

1
00:00:01.000 --> 00:00:03.000
<i>Hello</i> &amp; welcome

2
00:01:03.000 --> 00:01:05.000
to the show.
"""


def test_auto_captions_are_deduplicated():
    assert vtt_to_text(AUTO_VTT) == "こんにちは皆さん\n今日は天気です"


def test_manual_subtitles_strip_ids_notes_and_tags():
    assert vtt_to_text(MANUAL_VTT) == "Hello & welcome\nto the show."


def _fmt(url="https://example.com/sub?lang=x", ext="vtt"):
    return {"ext": ext, "url": url}


def test_pick_subtitle_priority():
    info = {
        "subtitles": {"en": [_fmt()]},
        "automatic_captions": {"ja": [_fmt()], "en": [_fmt()]},
    }
    assert pick_subtitle(info)[:2] == ("自動生成字幕", "ja")
    info["subtitles"]["ja-JP"] = [_fmt()]
    assert pick_subtitle(info)[:2] == ("手動字幕", "ja-JP")


def test_pick_subtitle_skips_machine_translation():
    info = {
        "subtitles": {},
        "automatic_captions": {
            "ja": [_fmt("https://example.com/sub?lang=en&tlang=ja")],
            "en-orig": [_fmt()],
            "en": [_fmt("https://example.com/sub?lang=en&tlang=en")],
        },
    }
    assert pick_subtitle(info)[:2] == ("自動生成字幕", "en-orig")


def test_pick_subtitle_none():
    info = {"subtitles": {"ko": [_fmt()]}, "automatic_captions": {}}
    assert pick_subtitle(info) is None


def test_sanitize_filename():
    assert sanitize_filename('a/b:c?"d"') == "a_b_c__d_"
    assert len(sanitize_filename("あ" * 200).encode()) <= 200
