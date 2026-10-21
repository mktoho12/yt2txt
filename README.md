# yt2txt

YouTube 動画の内容をテキストファイルにする、要約前の下準備用ツールです。要約そのものは別の AI に任せます。

1. yt-dlp で字幕を取得します（動画本体はダウンロードしません）。優先順は 手動字幕(ja) → 自動生成字幕(ja) → 手動字幕(en) → 自動生成字幕(en) です。
   - YouTube が別の言語から機械翻訳した自動字幕（URL に `tlang=` が付くもの）は使いません。
2. VTT からタイムスタンプ・タグ・重複行を取り除き、プレーンテキストにします。
3. 字幕がない場合だけ、yt-dlp で音声を取得し（`-x` 相当）、[ElevenLabs Scribe v2](https://elevenlabs.io/docs/api-reference/speech-to-text/convert) で文字起こしします。
4. `<動画タイトル>.txt` に出力します。先頭にはタイトル・URL・取得元（字幕か文字起こしか）を書きます。

## 必要なもの

| もの | 用途 | 入れ方の例 |
|---|---|---|
| uv | インストールと実行 | https://docs.astral.sh/uv/ |
| deno（推奨） | yt-dlp が YouTube の JS チャレンジを解くのに使う。なければ node 等を使う | `mise use -g deno` |
| ffmpeg | 音声の抽出（字幕がないときだけ） | `sudo apt install ffmpeg` / `mise use -g ffmpeg` |
| ElevenLabs API キー | 文字起こし（字幕がないときだけ） | `~/.config/elevenlabs/api_key` にキーだけを書く。または環境変数 `ELEVENLABS_API_KEY` |

足りないものがあれば、実行時に入れ方を表示して終了します。

## インストール

```sh
uv tool install "git+ssh://git@github.com/mktoho12/yt2txt.git"
# 作業コピーから入れる場合
uv tool install -e .
```

## 使い方

```sh
yt2txt "https://www.youtube.com/watch?v=XXXXXXXXXXX"
yt2txt -o ~/notes "URL"                          # 出力先ディレクトリを指定（既定はカレント）
yt2txt --cookies-from-browser firefox "URL"      # bot 対策・年齢制限で弾かれたとき
yt2txt --cookies-from-browser "chrome:Profile 1" "URL"
```

- 標準出力には出力ファイルのパスだけを出し、進捗は標準エラーに出します。
- 同じタイトルのファイルがあれば上書きします。
- 一時ファイル（音声）は処理が終わると削除します。VTT はメモリ上で処理するので、ファイルを作りません。
- 文字起こしでは、文末か 1.5 秒以上の無音で改行します。音楽部分で Scribe が同じ語を延々と出すことがあるため、同じ短い句が 5 回以上続いたら 3 回に縮めます。

## 開発

```sh
uv sync
uv run pytest
```
