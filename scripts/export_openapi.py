import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    output = Path("contracts/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = create_app().openapi()
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"exported {len(payload['paths'])} paths to {output}")


if __name__ == "__main__":
    main()

