"""yt2txt: YouTube 動画を字幕（なければ文字起こし）でテキスト化する。"""

import argparse
import glob
import os
import re
import shutil
import sys
import tempfile

LANG_PRIORITY = ("ja", "en")

INSTALL_HINTS = {
    "yt-dlp": "  uv tool install --reinstall yt2txt で依存ごと入れ直すか、pip install 'yt-dlp[default]'",
    "ElevenLabs API キー": (
        "  https://elevenlabs.io/app/settings/api-keys でキーを作り、次のどちらかで渡してください\n"
        "  - ファイル: mkdir -p ~/.config/elevenlabs && (キーを) ~/.config/elevenlabs/api_key に保存\n"
        "  - 環境変数: export ELEVENLABS_API_KEY=..."
    ),
    "ffmpeg": (
        "  Ubuntu/Debian: sudo apt install ffmpeg\n"
        "  macOS:         brew install ffmpeg\n"
        "  mise:          mise use -g ffmpeg"
    ),
}


class Yt2TxtError(Exception):
    pass


def log(msg: str) -> None:
    print(f"[yt2txt] {msg}", file=sys.stderr)


def missing_dependency(name: str, purpose: str, how: str = "インストール方法") -> Yt2TxtError:
    return Yt2TxtError(f"{name} が見つかりません（{purpose}に必要です）。{how}:\n{INSTALL_HINTS[name]}")


def require_yt_dlp():
    try:
        import yt_dlp
    except ImportError:
        raise missing_dependency("yt-dlp", "動画情報・字幕の取得") from None
    return yt_dlp


def require_transcription_deps() -> str:
    """文字起こしに必要な ffmpeg と API キーを確かめ、API キーを返す。"""
    from .transcribe import load_api_key

    if not shutil.which("ffmpeg"):
        raise missing_dependency("ffmpeg", "音声の抽出")
    api_key = load_api_key()
    if not api_key:
        raise missing_dependency("ElevenLabs API キー", "字幕がない動画の文字起こし", "設定方法")
    return api_key


def detect_js_runtimes() -> dict:
    """yt-dlp に渡す JS ランタイムを決める。

    最近の YouTube は JS チャレンジがあり、yt-dlp は既定では deno しか使わないため、
    deno がなくても node 等があればそれを有効にする。
    """
    found = {name: {"path": None} for name in ("deno", "node", "bun", "quickjs")
             if shutil.which("qjs" if name == "quickjs" else name)}
    if not found:
        log(
            "警告: JS ランタイム（deno 推奨）が見つかりません。YouTube の取得に失敗する場合は"
            " deno を入れてください（例: mise use -g deno / curl -fsSL https://deno.land/install.sh | sh）"
        )
    return found


def _lang_matches(code: str, lang: str) -> bool:
    return code == lang or code.startswith(lang + "-")


def pick_subtitle(info: dict) -> tuple[str, str, dict] | None:
    """優先順 手動ja → 自動ja → 手動en → 自動en で VTT トラックを選ぶ。

    自動生成字幕のうち、YouTube が別言語から機械翻訳したもの（URL に tlang= を含む）は除外する。
    戻り値は (種別, 言語コード, フォーマット dict)。
    """
    for lang in LANG_PRIORITY:
        for kind, key in (("手動字幕", "subtitles"), ("自動生成字幕", "automatic_captions")):
            tracks = info.get(key) or {}
            # 'ja' のような完全一致を 'ja-JP' などより優先する
            codes = sorted((c for c in tracks if _lang_matches(c, lang)), key=lambda c: c != lang)
            for code in codes:
                for fmt in tracks[code]:
                    if fmt.get("ext") == "vtt" and "tlang=" not in fmt.get("url", ""):
                        return kind, code, fmt
    return None


def sanitize_filename(title: str, max_bytes: int = 200) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title).strip(" .")
    while len(name.encode("utf-8")) > max_bytes:
        name = name[:-1]
    return name or "untitled"


def explain_download_error(e: Exception) -> Yt2TxtError:
    msg = str(e)
    if re.search(r"Sign in to confirm|not a bot|HTTP Error 429|cookies", msg, re.I):
        return Yt2TxtError(
            f"YouTube にログインを求められ、取得に失敗しました（bot 対策・年齢制限など）:\n  {msg}\n"
            "ブラウザのログイン状態を使って再実行してください。例:\n"
            '  yt2txt --cookies-from-browser firefox "URL"\n'
            '  yt2txt --cookies-from-browser chrome "URL"'
        )
    return Yt2TxtError(f"yt-dlp でエラーが発生しました:\n  {msg}")


class _YtDlpLogger:
    """警告は表示し、エラーは explain_download_error でまとめて表示するので捨てる。"""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        print(f"WARNING: {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        pass


def build_base_opts(yt_dlp, cookies_from_browser: str | None) -> dict:
    opts = {"quiet": True, "no_warnings": False, "noprogress": True, "noplaylist": True,
            "logger": _YtDlpLogger()}
    js_runtimes = detect_js_runtimes()
    if js_runtimes:
        opts["js_runtimes"] = js_runtimes
    if cookies_from_browser:
        # yt-dlp 本体と同じ書式（BROWSER[+KEYRING][:PROFILE][::CONTAINER]）を受け付ける
        parsed = yt_dlp.parse_options(["--cookies-from-browser", cookies_from_browser])
        opts["cookiesfrombrowser"] = parsed.ydl_opts["cookiesfrombrowser"]
    return opts


def fetch_text(url: str, args: argparse.Namespace) -> tuple[dict, str, str]:
    """(動画情報, 本文, 取得元の説明) を返す。"""
    yt_dlp = require_yt_dlp()
    base_opts = build_base_opts(yt_dlp, args.cookies_from_browser)

    try:
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            log("動画情報を取得中...")
            info = ydl.extract_info(url, download=False)
            picked = pick_subtitle(info)
            if picked:
                kind, code, fmt = picked
                log(f"{kind}（{code}）を取得中...")
                # VTT はメモリ上で処理するため一時ファイルは作らない
                vtt = ydl.urlopen(fmt["url"]).read().decode("utf-8", errors="replace")
                from .vtt import vtt_to_text

                text = vtt_to_text(vtt)
                if text.strip():
                    return info, text, f"字幕（{kind}・{code}）"
                log("字幕が空だったため文字起こしに切り替えます")
            else:
                log("日本語・英語の字幕が見つからないため、音声を文字起こしします")
    except yt_dlp.utils.DownloadError as e:
        raise explain_download_error(e) from None

    api_key = require_transcription_deps()
    from .transcribe import TranscribeError, transcribe

    with tempfile.TemporaryDirectory(prefix="yt2txt-") as tmpdir:
        audio_opts = {
            **base_opts,
            "format": "bestaudio/best",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "best"}],
        }
        try:
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                log("音声をダウンロード中...")
                ydl.download([info.get("webpage_url") or url])
        except yt_dlp.utils.DownloadError as e:
            raise explain_download_error(e) from None
        files = glob.glob(os.path.join(tmpdir, "audio.*"))
        if not files:
            raise Yt2TxtError("音声ファイルの取得に失敗しました")
        log("ElevenLabs で文字起こし中...")
        try:
            text, desc = transcribe(files[0], api_key)
        except TranscribeError as e:
            raise Yt2TxtError(str(e)) from None
    # with を抜けた時点で一時ディレクトリ（音声）は削除済み
    return info, text, f"文字起こし（{desc}）"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="yt2txt",
        description="YouTube 動画を字幕（なければ ElevenLabs で文字起こし）でテキスト化します。",
    )
    p.add_argument("url", help="YouTube 動画の URL")
    p.add_argument("-o", "--output-dir", default=".", help="出力先ディレクトリ（既定: カレント）")
    p.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER[:PROFILE]",
        help="bot 対策で失敗する場合に、ブラウザの Cookie を使う（例: firefox, chrome）",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        info, text, source = fetch_text(args.url, args)
    except Yt2TxtError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    title = info.get("title") or info.get("id") or "untitled"
    page_url = info.get("webpage_url") or args.url
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, sanitize_filename(title) + ".txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"タイトル: {title}\nURL: {page_url}\n取得元: {source}\n\n---\n\n{text}\n")
    log(f"出力しました: {out_path}")
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
