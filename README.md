# Claude-calculation

LLM が間違えやすい算数・統計問題を、**ツールなし**と **Code Execution Tool あり**の2モードで解かせて正誤を比較するベンチマークです。

## 問題一覧

| # | タイトル | カテゴリ |
|---|---------|---------|
| 1 | 実数15個の算術平均 | 基本統計 |
| 2 | 標本標準偏差（8個） | 基本統計 |
| 3 | 対応なし2標本t検定（有意差なし） | t検定 |
| 4 | 対応あり1標本t検定（有意差あり） | t検定 |
| 5 | ピアソン相関係数と有意性検定 | 相関 |

- LLMの出力は確定的ではないため、意外な結果が出る場合もあります。何回か実行してみることを推奨します。

## セットアップ

```bash
uv sync
```

環境変数に Anthropic API キーを設定してください。

```bash
export CLAUDE_API_KEY="sk-ant-..."
```

## 実行

```bash
# ターミナル出力のみ
uv run python run_problems.py

# HTML レポートも生成
uv run python run_problems.py --html report.html
```

HTML レポートはブラウザで開くと MathJax により数式がレンダリングされます。

## モデル構成

| 役割 | モデル |
|------|-------|
| ツールなし回答 | `claude-haiku-4-5` |
| ツールあり回答 | `claude-haiku-4-5` |
| 正誤判定 | `claude-opus-4-6` |

同じモデルを使うことで、ツールの有無だけを変数として比較できます。

## ファイル構成

```
.
├── run_problems.py   # メインスクリプト
├── problems.yaml     # 問題定義
├── pyproject.toml    # 依存関係
└── README.md
```
