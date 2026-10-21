from yt2txt.transcribe import words_to_text


def w(text, start, end, kind="word"):
    return {"text": text, "start": start, "end": end, "type": kind}


def test_japanese_breaks_at_sentence_end_and_pause():
    words = [
        w("今", 0.0, 0.1), w("日", 0.1, 0.2), w("は", 0.2, 0.3), w("。", 0.3, 0.3),
        w("(笑)", 0.4, 0.5, "audio_event"),
        w("晴", 0.5, 0.6), w("れ", 0.6, 0.7),
        w("雨", 3.0, 3.1), w("で", 3.1, 3.2), w("す", 3.2, 3.3),
    ]
    assert words_to_text(words) == "今日は。\n晴れ\n雨です"


def test_english_keeps_spacing():
    words = [
        w("Hello", 0.0, 0.3), w(" ", 0.3, 0.3, "spacing"), w("world.", 0.3, 0.6),
        w(" ", 0.6, 0.6, "spacing"), w("Bye", 0.7, 0.9),
    ]
    assert words_to_text(words) == "Hello world.\nBye"


def test_punctuation_at_word_start_breaks_line():
    words = [w("君", 0.0, 0.1), w("は", 0.1, 0.2), w("？Hey,", 0.2, 0.4),
             w(" ", 0.4, 0.4, "spacing"), w("now.", 0.4, 0.6)]
    assert words_to_text(words) == "君は？\nHey, now."


def test_hallucinated_repeats_are_collapsed():
    words = [w("君", 0.0, 0.1), w("Oh。" * 50, 0.1, 9.0)]
    assert words_to_text(words) == "君Oh。\nOh。\nOh。"
