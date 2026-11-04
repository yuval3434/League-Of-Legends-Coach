"""The Riot and Anthropic keys: stored only in .env, never shown again.

The settings page can replace a key, but nothing reads one back out: callers
get whether it's set, its last 4 characters, and when it was set. .env stays the
one place secrets live. Inside Docker it's bind-mounted, so it's rewritten in
place: replacing a mounted file by renaming another over it fails.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Development keys from the Riot portal expire 24 hours after they're made.
RIOT_KEY_LIFETIME = timedelta(hours=24)


@dataclass(frozen=True)
class Key:
    """One key's env variable, and the variable holding when it was set."""

    env: str
    set_at_env: str


KEYS = {
    "riot": Key("RIOT_API_KEY", "RIOT_API_KEY_SET_AT"),
    "anthropic": Key("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_SET_AT"),
}


def _parse(line: str) -> tuple[str, str] | None:
    """NAME and value of a `NAME=value` line; None for comments and blanks."""
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    name, value = text.split("=", 1)
    return name.strip(), value.strip().strip('"').strip("'")


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    pairs = (_parse(line) for line in path.read_text(encoding="utf-8").splitlines())
    return dict(pair for pair in pairs if pair)


def write_env(path: Path, values: dict[str, str]) -> None:
    """Set these variables in .env, keeping every other line and comment as it is.

    A variable already in the file is replaced where it stands; a new one is
    added at the end. The file is rewritten in place, not replaced.
    """
    # newline="" keeps "\r\n" as it is, so a Windows .env stays one.
    text = path.open(encoding="utf-8", newline="").read() if path.exists() else ""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    left = dict(values)
    for i, line in enumerate(lines):
        pair = _parse(line)
        if pair and pair[0] in left:
            lines[i] = f"{pair[0]}={left.pop(pair[0])}"
    lines += [f"{name}={value}" for name, value in left.items()]
    with path.open("r+" if path.exists() else "w", encoding="utf-8", newline="") as file:
        file.seek(0)
        file.write(newline.join(lines) + newline)
        file.truncate()


def save_key(path: Path, name: str, value: str, now: datetime | None = None) -> None:
    key = KEYS[name]
    when = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    write_env(path, {key.env: value, key.set_at_env: when})


def key_value(path: Path, name: str) -> str:
    """The stored key itself, for the server's own clients only. Never return it."""
    return read_env(path).get(KEYS[name].env, "")


def describe(path: Path, name: str) -> dict[str, object]:
    """What the settings page may know about a key: never the key itself."""
    env = read_env(path)
    key = KEYS[name]
    value = env.get(key.env, "")
    set_at = env.get(key.set_at_env) or None
    info: dict[str, object] = {
        "set": bool(value),
        # Enough to tell two keys apart, not enough to use one.
        "last4": value[-4:] if len(value) >= 8 else None,
        "set_at": set_at,
    }
    if name == "riot":
        info["expires_at"] = (
            (datetime.fromisoformat(set_at) + RIOT_KEY_LIFETIME).isoformat(timespec="seconds")
            if set_at
            else None
        )
    return info
