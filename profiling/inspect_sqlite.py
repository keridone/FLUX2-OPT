import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    connection = sqlite3.connect(args.database)
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    result: dict[str, object] = {"database": str(args.database), "tables": {}}
    for table in tables:
        columns = [
            {"name": row[1], "type": row[2]}
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        ]
        count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        entry: dict[str, object] = {"row_count": count, "columns": columns}
        if "METRIC" in table.upper() or "GENERIC" in table.upper():
            entry["sample_rows"] = [
                list(row)
                for row in connection.execute(f'SELECT * FROM "{table}" LIMIT 5')
            ]
        result["tables"][table] = entry
    args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
