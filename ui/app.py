"""Gradio chat UI for the coach. Talks to the API, so the API must be running.

Run with `uv run python -m ui.app`, then open http://127.0.0.1:7860. The stats
tab is free. Asking the coach makes paid calls and needs ANTHROPIC_API_KEY.
"""

import os
from typing import Any

import gradio as gr
import httpx
import pandas as pd
from pandas.io.formats.style import Styler

from agent.tools import TOOLS
from analytics.stats import MIN_GAMES

API = os.environ.get("COACH_API_URL", "http://localhost:8000")
COACH_TIMEOUT_S = 300
STATS = [
    t.name
    for t in TOOLS
    if t.name not in ("data_coverage", "compare_to_benchmark", "champion_stats")
]
ALL_CHAMPIONS = "All champions"
ROLES = {
    "All": None,
    "Jungle": "JUNGLE",
    "Top": "TOP",
    "Mid": "MIDDLE",
    "Bot": "BOTTOM",
    "Support": "UTILITY",
}
CHAMPION_COLUMNS = ["Champion", "Games", "Wins", "Win rate %", "KDA", "CS/min", "Note"]
NOT_ENOUGH = "not enough data"
GREY = "color: #9ca3af"

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
    "no_answer": "The local model didn't answer; try again or use Claude.",
}
TOOL_COLUMNS = ["Tool", "Asked for", "Your games", "Benchmark games"]


def _unreachable() -> str:
    return f"Can't reach the API at {API}. Start it with `docker compose up -d`."


def _detail(response: httpx.Response) -> str:
    return f"The API returned {response.status_code}: {response.json().get('detail')}"


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
        return _detail(response), "", empty
    answer = response.json()
    return answer["text"], status_text(answer), tools_table(answer.get("tools", []))


def coverage(client: httpx.Client) -> tuple[str, list[str]]:
    """The data summary, and the champions played, most played first."""
    try:
        response = client.get("/stats/data_coverage")
    except httpx.TransportError:
        return _unreachable(), []
    if response.status_code != 200:
        return f"No data yet: {response.json().get('detail')}", []
    result = response.json()
    player = result["player"]
    patches = player["patches"]
    patch_range = f"{patches[0]} to {patches[-1]}" if patches else "none"
    summary = (
        f"**Your data:** {player['games']} games, {player['jungle_games']} in the jungle, "
        f"from {player['first_game']} to {player['last_game']}, patches {patch_range}."
    )
    return summary, [c["champion"] for c in result["champions"]]


def stat(name: str, champion: str | None, client: httpx.Client) -> tuple[pd.DataFrame, str]:
    params = {"champion": champion} if champion and champion != ALL_CHAMPIONS else {}
    try:
        response = client.get(f"/stats/{name}", params=params)
    except httpx.TransportError:
        return pd.DataFrame(), _unreachable()
    if response.status_code != 200:
        return pd.DataFrame(), _detail(response)
    result = response.json()
    rows = result.get("rows", [])
    note = result.get("note", "")
    if any(row.get("low_sample") for row in rows):
        note = (note + " " if note else "") + f"Rows marked low_sample have under {MIN_GAMES} games: {NOT_ENOUGH}."
    return pd.DataFrame(rows), note


def champion_table(rows: list[dict[str, Any]]) -> Styler:
    """Most played first, with rows under MIN_GAMES greyed and noted, not hidden.

    The note column keeps the warning attached to its row when the table is sorted.
    """
    frame = pd.DataFrame(
        [
            [
                r["champion"],
                r["games"],
                r["wins"],
                r["win_rate_pct"],
                r["kda"],
                r["cs_per_min"],
                NOT_ENOUGH if r["games"] < MIN_GAMES else "",
            ]
            for r in rows
        ],
        columns=CHAMPION_COLUMNS,
    )
    return frame.style.apply(
        lambda row: [GREY if row["Games"] < MIN_GAMES else ""] * len(row), axis=1
    ).format({"Win rate %": "{:.1f}", "KDA": "{:.2f}", "CS/min": "{:.2f}"})


def my_champions(role: str, client: httpx.Client) -> tuple[Styler | pd.DataFrame, str]:
    params = {"role": ROLES[role]} if ROLES[role] else {}
    try:
        response = client.get("/stats/champion_stats", params=params)
    except httpx.TransportError:
        return pd.DataFrame(columns=CHAMPION_COLUMNS), _unreachable()
    if response.status_code != 200:
        return pd.DataFrame(columns=CHAMPION_COLUMNS), _detail(response)
    rows = response.json()["rows"]
    if not rows:
        return pd.DataFrame(columns=CHAMPION_COLUMNS), f"No games in this role ({role})."
    games = sum(r["games"] for r in rows)
    return champion_table(rows), (
        f"{len(rows)} champions, {games} games. Grey rows have under {MIN_GAMES} games: "
        f"{NOT_ENOUGH}. To sort, click a column header, then its ⋮ menu."
    )


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
            gr.Markdown("### My champions")
            role = gr.Radio(list(ROLES), value="All", label="Role")
            champions_note = gr.Markdown()
            champions = gr.Dataframe(
                headers=CHAMPION_COLUMNS, label="Champions", interactive=False
            )
            role.change(lambda r: my_champions(r, client), role, [champions, champions_note])

            gr.Markdown("### Any stat")
            with gr.Row():
                name = gr.Dropdown(STATS, value="win_rates", label="Stat")
                champion = gr.Dropdown([ALL_CHAMPIONS], value=ALL_CHAMPIONS, label="Champion")
            run = gr.Button("Show")
            note = gr.Markdown()
            rows = gr.Dataframe(
                headers=["Pick a stat and press Show"], label="Rows", interactive=False, wrap=True
            )
            run.click(lambda n, c: stat(n, c, client), [name, champion], [rows, note])

        def load() -> tuple[str, gr.Dropdown, Styler | pd.DataFrame, str]:
            summary, played = coverage(client)
            table, table_note = my_champions("All", client)
            choices = gr.Dropdown(choices=[ALL_CHAMPIONS, *played], value=ALL_CHAMPIONS)
            return summary, choices, table, table_note

        app.load(load, None, [data, champion, champions, champions_note])
    return app


if __name__ == "__main__":
    build(httpx.Client(base_url=API, timeout=30)).launch(server_name="127.0.0.1", server_port=7860)
