"""Verify every translation lines up with its English lesson before rendering.

Usage: python scripts/check_translations.py [ja|zh]   (default: ja)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "build" / "extracted"
TRANSLATED = ROOT / "build" / "translated"

# Chinese has no kana; requiring a Han character (and, for ja, allowing kana too) catches
# an untranslated English string and a translation that landed in the wrong language.
HAN = r"一-鿿㐀-䶿"
KANA = r"぀-ヿ"
LANG_RE = {
    "ja": re.compile(f"[{HAN}{KANA}]"),
    "zh": re.compile(f"[{HAN}]"),
}
KANA_RE = re.compile(f"[{KANA}]")


def problems(lesson, translation, script):
    for key in ("dialogue", "key_vocabulary", "supplementary_vocabulary"):
        got = translation.get(key)
        if not isinstance(got, list) or len(got) != len(lesson[key]):
            yield f"{key}: expected {len(lesson[key])} entries, got {len(got or [])}"
            continue
        for i, entry in enumerate(got):
            if key == "dialogue":
                if not isinstance(entry, str) or not script.search(entry):
                    yield f"dialogue[{i}] not in target language: {entry!r:.60}"
                elif script is LANG_RE["zh"] and KANA_RE.search(entry):
                    yield f"dialogue[{i}] contains Japanese kana: {entry!r:.60}"
            elif not isinstance(entry, dict) or "pos" not in entry or "definition" not in entry:
                yield f"{key}[{i}] missing pos/definition: {entry!r:.60}"
            elif lesson[key][i]["definition"] and not script.search(entry["definition"]):
                yield f"{key}[{i}] definition not in target language: {entry['definition']!r:.60}"
    if not translation.get("title") or not script.search(translation["title"]):
        yield f"title not in target language: {translation.get('title')!r:.60}"


def main(lang="ja"):
    script = LANG_RE[lang]
    missing, broken = [], []
    for path in sorted(EXTRACTED.glob("englishpod_*.json")):
        tr_path = TRANSLATED / f"{path.stem}.{lang}.json"
        if not tr_path.exists():
            missing.append(path.stem.split("_")[1])
            continue
        lesson = json.loads(path.read_text(encoding="utf-8"))
        try:
            translation = json.loads(tr_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            broken.append((path.stem.split("_")[1], [f"invalid JSON: {exc}"]))
            continue
        found = list(problems(lesson, translation, script))
        if found:
            broken.append((path.stem.split("_")[1], found))

    print(f"[{lang}] missing: {len(missing)}  broken: {len(broken)}")
    if missing:
        print("  missing ids:", " ".join(missing))
    for lesson_id, found in broken:
        print(f"  {lesson_id}:", *found, sep="\n    ")
    return 1 if missing or broken else 0


if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "ja"
    sys.exit(main(lang))
