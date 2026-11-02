"""Gradio chat UI for the coach. Talks to the API, so the API must be running.

Run with `uv run python -m ui.app`, then open http://127.0.0.1:7860. The stats
tab is free. Asking the coach makes paid calls and needs ANTHROPIC_API_KEY.
"""

import os
from typing import Any

import gradio as gr
import httpx
import pandas as pd

from agent.tools import TOOLS

API = os.environ.get("COACH_API_URL", "http://localhost:8000")
COACH_TIMEOUT_S = 300
STATS = [t.name for t in TOOLS if t.name not in ("data_coverage", "compare_to_benchmark")]

NO_KEY = (
    "**Asking the coach needs an Anthropic API key**, and each question is a paid "
    "call, usually a few cents to about $0.30. Set `ANTHROPIC_API_KEY` in `.env` and "
    "restart the API. The **Stats** tab works without one."
)
STATUS = {
    "verified": "✓ **Number check passed.** Every number above was found in the coach's data.",
    "unverified": "⚠ **Number check failed.** These numbers weren't found in the coach's data, so don't trust them: {numbers}.",
    "refused": "The coach couldn't answer this question.",
    "truncated": "The answer was cut off. Try a narrower question.",
    "gave_up": "The coach couldn't finish. Try a narrower question.",
}
TOOL_COLUMNS = ["Tool", "Asked for", "Your games", "Benchmark games"]


def _unreachable() -> str:
    return f"Can't reach the API at {API}. Start it with `docker compose up -d`."


def _range(games: dict[str, int] | None) -> str:
    if not games:
        return ""
    low, high = games["min"], games["max"]
    return str(low) if low == high else f"{low}–{high}"


def tools_table(tools: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for tool in tools:
        asked = ", ".join(f"{k}={v}" for k, v in tool["arguments"].items() if v is not None)
        if tool.get("error"):
            rows.append([tool["name"], asked, "failed", ""])
            continue
        benchmark = ""
        if "benchmark_games" in tool:
            benchmark = f"{tool['benchmark_games']} ({tool['benchmark_players']} players)"
            if tool.get("status") == "no_benchmark":
                benchmark += ": no benchmark"
        rows.append([tool["name"], asked or "all", _range(tool.get("your_games")), benchmark])
    return pd.DataFrame(rows, columns=TOOL_COLUMNS)


def status_text(answer: dict[str, Any]) -> str:
    template = STATUS.get(answer["status"], answer["status"])
    numbers = ", ".join(answer.get("caught_numbers") or [])
    return template.format(numbers=numbers)


def ask(question: str, client: httpx.Client) -> tuple[str, str, pd.DataFrame]:
    empty = pd.DataFrame(columns=TOOL_COLUMNS)
    if not question.strip():
        return "Ask a question about your games.", "", empty
    try:
        response = client.post("/coach", json={"question": question}, timeout=COACH_TIMEOUT_S)
    except httpx.TransportError:
        return _unreachable(), "", empty
    if response.status_code == 503:
        return NO_KEY, "", empty
    if response.status_code != 200:
        return f"The API returned {response.status_code}: {response.json().get('detail')}", "", empty
    answer = response.json()
    return answer["text"], status_text(answer), tools_table(answer.get("tools", []))


def coverage(client: httpx.Client) -> str:
    try:
        response = client.get("/stats/data_coverage")
    except httpx.TransportError:
        return _unreachable()
    if response.status_code != 200:
        return f"No data yet: {response.json().get('detail')}"
    player = response.json()["player"]
    patches = player["patches"]
    patch_range = f"{patches[0]} to {patches[-1]}" if patches else "none"
    return (
        f"**Your data:** {player['games']} games, {player['jungle_games']} in the jungle, "
        f"from {player['first_game']} to {player['last_game']}, patches {patch_range}."
    )


def stat(name: str, champion: str, client: httpx.Client) -> tuple[pd.DataFrame, str]:
    params = {"champion": champion.strip()} if champion.strip() else {}
    try:
        response = client.get(f"/stats/{name}", params=params)
    except httpx.TransportError:
        return pd.DataFrame(), _unreachable()
    if response.status_code != 200:
        return pd.DataFrame(), f"The API returned {response.status_code}: {response.json().get('detail')}"
    result = response.json()
    rows = result.get("rows", [])
    note = result.get("note", "")
    if any(row.get("low_sample") for row in rows):
        note = (note + " " if note else "") + "Rows marked low_sample have under 10 games: not enough data."
    return pd.DataFrame(rows), note


def build(client: httpx.Client) -> gr.Blocks:
    with gr.Blocks(title="LoL Coach") as app:
        gr.Markdown(
            "# LoL Coach\nA personal League of Legends jungle coach. Every number comes "
            "from SQL over real match data, and the coach only explains it."
        )
        data = gr.Markdown()
        with gr.Tab("Ask the coach"):
            question = gr.Textbox(
                label="Question", placeholder="How is my farming compared with Silver?", lines=2
            )
            send = gr.Button("Ask", variant="primary")
            reply = gr.Markdown()
            check = gr.Markdown()
            tools = gr.Dataframe(headers=TOOL_COLUMNS, label="Tools called", interactive=False)
            send.click(lambda q: ask(q, client), question, [reply, check, tools])
            question.submit(lambda q: ask(q, client), question, [reply, check, tools])
        with gr.Tab("Stats (free)"):
            with gr.Row():
                name = gr.Dropdown(STATS, value="win_rates", label="Stat")
                champion = gr.Textbox(label="Champion (optional)", placeholder="e.g. Viego")
            run = gr.Button("Show")
            note = gr.Markdown()
            rows = gr.Dataframe(label="Rows", interactive=False, wrap=True)
            run.click(lambda n, c: stat(n, c, client), [name, champion], [rows, note])
        app.load(lambda: coverage(client), None, data)
    return app


if __name__ == "__main__":
    build(httpx.Client(base_url=API, timeout=30)).launch(server_name="127.0.0.1", server_port=7860)
