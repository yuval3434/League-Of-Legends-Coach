"""Back up the whole database to backups/lolcoach_<date>_<time>.dump.

Run with `uv run python scripts/backup.py` while the `db` container is up.
pg_dump runs inside the container, so its version matches the server's. The file
is pg_dump's custom format, which is compressed. Restore it with pg_restore.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKUPS = Path(__file__).resolve().parent.parent / "backups"
DUMP = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom'


def main() -> int:
    BACKUPS.mkdir(exist_ok=True)
    target = BACKUPS / f"lolcoach_{datetime.now():%Y-%m-%d_%H%M%S}.dump"
    # Only a finished dump gets the real name, so a failed run can't pass for a backup.
    partial = target.with_suffix(".partial")

    with partial.open("wb") as output:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "sh", "-c", DUMP],
            stdout=output,
            cwd=BACKUPS.parent,
        )
    if result.returncode != 0:
        partial.unlink()
        print("Backup failed: nothing was saved.", file=sys.stderr)
        return result.returncode or 1

    partial.rename(target)
    print(f"{target} ({target.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
