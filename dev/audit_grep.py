"""Grep audit (DEV_PLAN Phase 9): no Brief A/B literal in builder/ (D3). Run from the repo root; exit 1 on a hit."""
import os
import re
import sys

LITERALS = [
    r"Freya Bank", r"4821", r"2026-10-26", r"2026-11-11", r"2026-11-26", r"2026-12-25", r"2027-01-01",
    r"\b10:00\b", r"\b19:00\b", r"12th business day", r"7th business day", r"\b1 to 7\b", r"\b8 to 45\b",
    r"sorry for your loss", r"text message confirming", r"Can you make this payment today", r"Do you confirm\?",
    r"Am I speaking with", r"minimum_payment", r"instalment_amount", r"card_last4", r"date_of_birth", r"phone_last4",
    r"day_month_swapped", r"\brestructuring\b", r"\bqueue `?support`?\b", r"collections team", r"mobile app",
    r"Daniel", r"Reyes", r"\bBrief [AB]\b", r"\brules? \d{1,2} (and|,) \d{1,2}\b",
]
ALLOW_FILES = {"builder/openapi_tools.py"}  # may legitimately quote API names from the OpenAPI file


def main() -> int:
    hits = 0
    for root, _, files in os.walk("builder"):
        for fn in files:
            path = os.path.join(root, fn)
            if not fn.endswith((".py", ".txt", ".tmpl", ".md", ".json")) or path in ALLOW_FILES:
                continue
            with open(path, encoding="utf-8", errors="replace") as f:
                for n, line in enumerate(f, 1):
                    for lit in LITERALS:
                        if re.search(lit, line, re.I):
                            print(f"{path}:{n}: /{lit}/ -> {line.strip()[:100]}")
                            hits += 1
    print(f"{hits} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
