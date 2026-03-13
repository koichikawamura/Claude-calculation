"""
problems.yaml の各問題を Claude API で回答する。
- モード1: ツールなし（テキスト推論のみ）
- モード2: Code Execution Tool あり（Python コードを実際に実行）

最後に正誤まとめ表を出力する。

Usage:
    python run_problems.py
    python run_problems.py --html report.html
"""

import argparse
import html
import os
import yaml
import anthropic

YAML_PATH = "problems.yaml"
MODEL_NO_TOOL   = "claude-haiku-4-5"   # ツールなし
MODEL_WITH_TOOL = "claude-haiku-4-5"   # ツールあり（同じモデルでツールの効果を比較）
MODEL_JUDGE     = "claude-opus-4-6"    # 判定用（正確な数値比較のため強いモデル）

client = anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])


def load_problems(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["problems"]


# ──────────────────────────────────────────────
# モード1: ツールなし
# ──────────────────────────────────────────────

def answer_without_tools(problem: dict) -> str:
    response = client.messages.create(
        model=MODEL_NO_TOOL,
        max_tokens=1024,
        messages=[{"role": "user", "content": problem["prompt"]}],
    )
    texts = [b.text for b in response.content if b.type == "text"]
    return "\n".join(texts)


# ──────────────────────────────────────────────
# モード2: Code Execution Tool あり
# ──────────────────────────────────────────────

def extract_code_execution_result(content) -> list[str]:
    parts = []
    for block in content:
        if block.type == "text":
            parts.append(f"[Claude]: {block.text}")
        elif block.type == "server_tool_use":
            code = getattr(block, "input", {})
            cmd = code.get("cmd", code.get("command", "")) if isinstance(code, dict) else str(code)
            if cmd:
                parts.append(f"[実行コード]:\n{cmd}")
        elif block.type == "bash_code_execution_tool_result":
            result = block.content
            if hasattr(result, "stdout") and result.stdout:
                parts.append(f"[stdout]: {result.stdout.rstrip()}")
            if hasattr(result, "stderr") and result.stderr:
                parts.append(f"[stderr]: {result.stderr.rstrip()}")
    return parts


def answer_with_code_execution(problem: dict) -> str:
    tools = [{"type": "code_execution_20260120", "name": "code_execution"}]
    system = (
        "あなたは数学・統計の専門家です。"
        "計算が必要な問題は必ず code_execution ツールで Python コードを実行して"
        "正確な数値を求めてから回答してください。"
    )
    messages = [{"role": "user", "content": problem["prompt"]}]
    all_parts: list[str] = []

    for _ in range(5):
        response = client.messages.create(
            model=MODEL_WITH_TOOL,
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages,
        )
        all_parts.extend(extract_code_execution_result(response.content))

        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        break

    return "\n".join(all_parts) if all_parts else "(応答なし)"


# ──────────────────────────────────────────────
# 正誤判定
# ──────────────────────────────────────────────

def judge(problem: dict, answer: str) -> bool:
    """Claude に正誤を判定させる。正解なら True を返す。"""
    prompt = f"""以下の問題に対する正解と、モデルの回答を比較して、
モデルの回答が正しいかどうかを判定してください。

【問題】
{problem["prompt"].strip()}

【正解】
{problem["correct_answer"]} （詳細: {problem["correct_answer_detail"]}）

【モデルの回答】
{answer}

判定基準:
- 数値の誤差は小数点以下2桁まで合っていれば正解とする
- 最終的な答えが正しければ途中計算の表記ゆれは問わない

最後の行に「正解」または「不正解」とだけ書いてください。"""

    response = client.messages.create(
        model=MODEL_JUDGE,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    verdict = next((b.text for b in response.content if b.type == "text"), "")
    return "正解" in verdict.splitlines()[-1]


# ──────────────────────────────────────────────
# ターミナル出力
# ──────────────────────────────────────────────

def print_separator(char: str = "─", width: int = 70) -> None:
    print(char * width)


def print_summary(problems: list[dict], results: list[dict]) -> None:
    W = 30
    col1 = "Haiku(ツールなし)"
    col2 = "Haiku(ツールあり)"
    header = f"{'問題':<4}  {'タイトル':<{W}}  {col1:^16}  {col2:^16}"
    sep = "─" * len(header)
    print("\n" + "═" * len(header))
    print("  まとめ: 正誤一覧")
    print("═" * len(header))
    print(header)
    print(sep)
    for p, r in zip(problems, results):
        mark_no  = "○" if r["no_tool"]   else "✗"
        mark_yes = "○" if r["with_tool"] else "✗"
        title = p["title"][:W]
        print(f"問{p['id']}    {title:<{W}}  {mark_no:^16}  {mark_yes:^16}")
    print(sep)
    total_no  = sum(1 for r in results if r["no_tool"])
    total_yes = sum(1 for r in results if r["with_tool"])
    n = len(problems)
    print(f"{'正解数':<4}  {'':.<{W}}  {f'{total_no}/{n}':^16}  {f'{total_yes}/{n}':^16}")
    print("═" * len(header))


# ──────────────────────────────────────────────
# HTML 出力
# ──────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>LLM 計算ベンチマーク結果</title>
<script>
  MathJax = {{
    tex: {{ inlineMath: [['$','$'], ['\\\\(','\\\\)']] }},
    options: {{ skipHtmlTags: ['script','noscript','style','textarea','pre'] }}
  }};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
  body {{ font-family: "Helvetica Neue", Arial, sans-serif; max-width: 960px;
          margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.7; }}
  h1   {{ border-bottom: 2px solid #444; padding-bottom: 8px; }}
  h2   {{ margin-top: 2em; background: #f0f4f8; padding: 8px 12px;
          border-left: 4px solid #4a90d9; }}
  h3   {{ color: #4a90d9; margin-top: 1.4em; }}
  .meta  {{ color: #666; font-size: .9em; margin-bottom: 1.5em; }}
  .prompt {{ background: #fafafa; border: 1px solid #ddd; border-radius: 4px;
             padding: 12px 16px; white-space: pre-wrap; font-size: .95em; }}
  .answer {{ background: #fff8e1; border: 1px solid #ffe082; border-radius: 4px;
             padding: 12px 16px; white-space: pre-wrap; font-size: .93em; }}
  .correct {{ background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 4px;
              padding: 12px 16px; font-size: .95em; }}
  .verdict-ok  {{ color: #2e7d32; font-weight: bold; }}
  .verdict-ng  {{ color: #c62828; font-weight: bold; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1em; }}
  th, td {{ border: 1px solid #ccc; padding: 10px 14px; text-align: center; }}
  th {{ background: #4a90d9; color: #fff; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  td.title {{ text-align: left; }}
  .ok {{ color: #2e7d32; font-size: 1.2em; }}
  .ng {{ color: #c62828; font-size: 1.2em; }}
  .score {{ font-weight: bold; }}
</style>
</head>
<body>
<h1>LLM 計算ベンチマーク結果</h1>
<p class="meta">
  ツールなし: <code>{model_no}</code> &nbsp;/&nbsp;
  ツールあり: <code>{model_with}</code> &nbsp;/&nbsp;
  判定: <code>{model_judge}</code>
</p>

{problem_sections}

<h2>まとめ: 正誤一覧</h2>
<table>
  <tr>
    <th>#</th><th class="title">問題</th><th>カテゴリ</th>
    <th>Haiku<br>ツールなし</th><th>Haiku<br>ツールあり</th>
  </tr>
  {summary_rows}
  <tr>
    <td colspan="3" class="score">正解数</td>
    <td class="score">{total_no}/{n}</td>
    <td class="score">{total_yes}/{n}</td>
  </tr>
</table>
</body>
</html>
"""

PROBLEM_SECTION = """\
<h2>問題 {id}: {title} <small>[{category}]</small></h2>
<h3>プロンプト</h3>
<div class="prompt">{prompt}</div>
<h3>正解</h3>
<div class="correct">{correct_answer}<br><small>{correct_answer_detail}</small></div>

<h3>モード1: ツールなし</h3>
<div class="answer">{answer_no}</div>
<p class="{cls_no}">判定: {mark_no}</p>

<h3>モード2: Code Execution Tool あり</h3>
<div class="answer">{answer_with}</div>
<p class="{cls_with}">判定: {mark_with}</p>
"""

SUMMARY_ROW = """\
  <tr>
    <td>{id}</td>
    <td class="title">{title}</td>
    <td>{category}</td>
    <td class="{cls_no}">{mark_no}</td>
    <td class="{cls_with}">{mark_with}</td>
  </tr>
"""


def render_html(
    problems: list[dict],
    results: list[dict],
    answers_no: list[str],
    answers_with: list[str],
    output_path: str,
) -> None:
    def e(s: str) -> str:
        return html.escape(str(s))

    sections = []
    rows = []
    for p, r, a_no, a_with in zip(problems, results, answers_no, answers_with):
        ok_no   = r["no_tool"]
        ok_with = r["with_tool"]
        sections.append(PROBLEM_SECTION.format(
            id=p["id"], title=e(p["title"]), category=e(p["category"]),
            prompt=e(p["prompt"].strip()),
            correct_answer=e(p["correct_answer"]),
            correct_answer_detail=e(p["correct_answer_detail"]),
            answer_no=e(a_no), answer_with=e(a_with),
            cls_no="verdict-ok"  if ok_no   else "verdict-ng",
            cls_with="verdict-ok" if ok_with else "verdict-ng",
            mark_no="○ 正解"   if ok_no   else "✗ 不正解",
            mark_with="○ 正解" if ok_with else "✗ 不正解",
        ))
        rows.append(SUMMARY_ROW.format(
            id=p["id"], title=e(p["title"]), category=e(p["category"]),
            cls_no="ok"  if ok_no   else "ng",
            cls_with="ok" if ok_with else "ng",
            mark_no="○" if ok_no   else "✗",
            mark_with="○" if ok_with else "✗",
        ))

    total_no  = sum(1 for r in results if r["no_tool"])
    total_yes = sum(1 for r in results if r["with_tool"])
    body = HTML_TEMPLATE.format(
        model_no=MODEL_NO_TOOL, model_with=MODEL_WITH_TOOL, model_judge=MODEL_JUDGE,
        problem_sections="\n".join(sections),
        summary_rows="\n".join(rows),
        total_no=total_no, total_yes=total_yes, n=len(problems),
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"\nHTML を保存しました: {output_path}")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────

def run_problem(problem: dict) -> tuple[dict, str, str]:
    print_separator("═")
    print(f"問題 {problem['id']}: {problem['title']}  [{problem['category']}]")
    print_separator()
    print(f"\n【プロンプト】\n{problem['prompt'].strip()}")
    print(f"\n【正解】{problem['correct_answer']}  ({problem['correct_answer_detail']})")

    # モード1
    print_separator()
    print(f"■ モード1: ツールなし  [{MODEL_NO_TOOL}]")
    print_separator("-")
    answer1 = answer_without_tools(problem)
    print(answer1)
    correct1 = judge(problem, answer1)
    print(f"\n→ 判定: {'○ 正解' if correct1 else '✗ 不正解'}")

    # モード2
    print_separator()
    print(f"■ モード2: Code Execution Tool あり  [{MODEL_WITH_TOOL}]")
    print_separator("-")
    answer2 = answer_with_code_execution(problem)
    print(answer2)
    correct2 = judge(problem, answer2)
    print(f"\n→ 判定: {'○ 正解' if correct2 else '✗ 不正解'}")

    print()
    return {"no_tool": correct1, "with_tool": correct2}, answer1, answer2


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 計算ベンチマーク")
    parser.add_argument("--html", metavar="FILE", help="HTML レポートの出力先ファイル名")
    args = parser.parse_args()

    problems = load_problems(YAML_PATH)
    print(f"問題数: {len(problems)} 問")
    print(f"ツールなし: {MODEL_NO_TOOL}  /  ツールあり: {MODEL_WITH_TOOL}  /  判定: {MODEL_JUDGE}\n")

    results, answers_no, answers_with = [], [], []
    for problem in problems:
        result, a_no, a_with = run_problem(problem)
        results.append(result)
        answers_no.append(a_no)
        answers_with.append(a_with)

    print_summary(problems, results)

    if args.html:
        render_html(problems, results, answers_no, answers_with, args.html)


if __name__ == "__main__":
    main()
