from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Detector training placeholder for Shuddho.")
    parser.add_argument("--config", required=True, help="Path to detector config JSON.")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    print("Detector training placeholder")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    print("TODO: connect custom tokenizer, dataset loader, optimizer, and checkpointing.")


if __name__ == "__main__":
    main()

