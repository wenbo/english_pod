"""Extract structured lesson content (title, dialogue, vocabulary) from EnglishPod PDFs.

The source PDFs are LaTeX output with a stable font-per-role convention, so roles
are recovered from fonts rather than from x positions (which shift per lesson):

    NimbusSanL-Bold  17.2   title
    NimbusSanL-Bold  14.3   section heading
    CMR17            17.2   dialogue speaker label
    NimbusSanL-Regu  17.2   dialogue text / vocabulary term
    CMTI12           14.3   vocabulary part of speech
    CMR12            14.3   vocabulary definition

Justification splits a visual line into several fragments, and long cells wrap
onto further lines, so fragments are bucketed into visual lines by y before the
lines of a cell are joined.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "pdf"
OUT_DIR = ROOT / "build" / "extracted"

FOOTER_Y = 755.0
LINE_BAND = 8.0  # fragments within this many points share a visual line
ROW_GAP = 28.0  # vertical gap that separates two vocabulary rows
TURN_GAP = 30.0  # vertical gap that separates two unlabelled dialogue blocks
HEADINGS = ("Key Vocabulary", "Supplementary Vocabulary")
WORDLIST = ROOT / "build" / "words_alpha.txt"

SPEAKER = "speaker"
TEXT = "text"
TERM = "term"
POS = "pos"
DEFINITION = "definition"
HEADING = "heading"
TITLE = "title"

def load_words():
    path = WORDLIST if WORDLIST.exists() else Path("/usr/share/dict/words")
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return {w.strip().lower() for w in fh}


WORDS = load_words()


def clean(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("⃝", "").replace("̸", "")
    return re.sub(r"\s+", " ", text).strip()


def classify(font, size):
    if "Bold" in font:
        return TITLE if size > 15 else HEADING
    if font.endswith("CMR17"):
        return SPEAKER
    if "CMTI" in font:
        return POS
    if "CMR12" in font:
        return DEFINITION
    if "NimbusSanL-Regu" in font:
        return TEXT  # dialogue text in a dialogue block, term in a vocabulary block
    return None


def read_fragments(path):
    """Return [(role, y, x, text)] for the whole document, in reading order."""
    doc = pymupdf.open(path)
    frags = []
    y_offset = 0.0
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                if line["bbox"][1] > FOOTER_Y:
                    continue
                for span in line["spans"]:
                    text = clean(span["text"])
                    if not text:
                        continue
                    role = classify(span["font"], round(span["size"], 1))
                    if role:
                        frags.append((role, y_offset + span["bbox"][1], span["bbox"][0], text))
        y_offset += page.rect.height
    doc.close()
    frags.sort(key=lambda f: (round(f[1] / LINE_BAND), f[2]))
    return frags


def visual_lines(frags):
    """Group fragments into visual lines: [(y, [text in x order])]."""
    lines = []
    for _role, y, x, text in frags:
        if lines and abs(lines[-1][0] - y) < LINE_BAND:
            lines[-1][1].append((x, text))
        else:
            lines.append((y, [(x, text)]))
    return [(y, [t for _x, t in sorted(parts)]) for y, parts in lines]


# A handful of source PDFs lost the separator before a short function word
# ("bythe chimney", "state-ofthe-art"), and the glyphs carry no gap, so the split has to
# be recovered from the wordlist.
GLUED_TAILS = ("the", "and", "for", "was", "his", "her", "you", "are", "is", "it", "of", "to")
GLUED_HEADS = ("into", "then", "that", "the", "and", "for", "but", "was", "are", "all",
               "as", "at", "by", "in", "on", "of", "to", "up")
NEVER_SPLIT = {"armand"}  # a character name that reads as "arm" + "and"
TOKEN = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)+|[A-Za-z]{5,}")


def word(token):
    return re.sub(r"[^a-z]", "", token.lower()) in WORDS


def split_glued(text):
    def standalone(part):
        """Reject fragments such as the 'ing' of the pig-latin 'alling-cay'."""
        return part.lower() in GLUED_HEADS or part in ("I", "a") or (word(part) and len(part) >= 4)

    def repair(segment):
        """Split a run of glued words, e.g. 'astheArmistice' -> as / the / Armistice."""
        if len(segment) < 5 or word(segment) or segment.lower() in NEVER_SPLIT:
            return None
        # Peel a function word off the end first, so 'intoyou' is not read as 'in to you'.
        for tail in GLUED_TAILS:
            head = segment[: -len(tail)]
            if segment.lower().endswith(tail) and len(head) > 1 and word(head):
                return [head, segment[-len(tail) :]]
        # Only a lowercase segment recurses from the head: a capitalized one is far more
        # likely a proper noun ("Atkins", "Asiago") than a glued sentence opener, and a
        # glued sentence opener is already caught by the tail rule above.
        if segment[0].isupper():
            return None
        for head in GLUED_HEADS:
            rest = segment[len(head) :]
            if segment.lower().startswith(head) and rest:
                tail = [rest] if standalone(rest) else repair(rest)
                if tail:
                    return [segment[: len(head)]] + tail
        return None

    def rejoin(match):
        token = match.group(0)
        # Inside a hyphenated compound the lost separator was a hyphen, not a space.
        sep = "-" if "-" in token else " "
        return "-".join(sep.join(repair(s) or [s]) for s in token.split("-"))

    return TOKEN.sub(rejoin, text)


def join_wrapped(lines):
    """Join wrapped lines, dropping a trailing hyphen only where LaTeX inserted it.

    LaTeX hyphenates inside a word, so the fragment after the break is normally not
    itself a word ("in-" + "ternet"). A hyphen is kept only when the tail stands as a
    word on its own and the merged form does not, which is the signature of a real
    compound such as "short-" + "staffed".
    """
    out = ""
    for line in lines:
        if not out:
            out = line
        elif out.endswith("-"):
            stem, tail = out[:-1], line.split(" ", 1)[0]
            merged = stem.rsplit(" ", 1)[-1] + tail
            keep_hyphen = word(tail) and not word(merged)
            out = out + line if keep_hyphen else stem + line
        else:
            out += " " + line
    return clean(out)


def cell(frags):
    """Join every fragment of one table cell into a single string."""
    return split_glued(join_wrapped([" ".join(parts) for _y, parts in visual_lines(frags)]))


def parse_dialogue(frags):
    """Turns are delimited by speaker labels; a few lessons are unlabelled verse or
    narration, where a vertical gap delimits the blocks instead.

    A speaker label that does not end in ':' has wrapped onto the next label line.
    """
    turns = []
    for frag in frags:
        role, y, _x, text = frag
        if role == SPEAKER:
            if turns and not turns[-1]["raw"].endswith(":"):
                turns[-1]["speaker"] += " " + text.rstrip(":").strip()
                turns[-1]["raw"] = text
            else:
                turns.append({"speaker": text.rstrip(":").strip(), "raw": text, "body": []})
        elif role == TEXT:
            unlabelled = not turns or (not turns[-1]["speaker"] and not turns[-1]["raw"])
            if not turns or (unlabelled and y - turns[-1]["body"][-1][1] > TURN_GAP):
                turns.append({"speaker": "", "raw": "", "body": []})
            turns[-1]["body"].append(frag)
    return [
        {"speaker": clean(t["speaker"]), "text": cell(t["body"])} for t in turns if t["body"]
    ]


def parse_vocab(frags):
    """Split fragments into rows on vertical gaps, then join each column."""
    rows, row_bottom = [], None
    for frag in frags:
        y = frag[1]
        if row_bottom is None or y - row_bottom > ROW_GAP:
            rows.append([])
            row_bottom = y
        row_bottom = max(row_bottom, y)
        rows[-1].append(frag)

    entries = []
    for row in rows:
        entry = {
            "term": cell([f for f in row if f[0] == TEXT]),
            "pos": cell([f for f in row if f[0] == POS]),
            "definition": cell([f for f in row if f[0] == DEFINITION]),
        }
        if entry["term"]:
            entries.append(entry)
    return entries


def extract(path):
    frags = read_fragments(path)

    # The title runs until the first non-bold fragment; its lesson code, e.g. "(C0117)",
    # is set in a smaller bold size that otherwise marks a section heading.
    title_parts = []
    while frags and frags[0][0] in (TITLE, HEADING) and frags[0][3] not in HEADINGS:
        title_parts.append(frags.pop(0)[3])

    sections, current = {"dialogue": [], HEADINGS[0]: [], HEADINGS[1]: []}, "dialogue"
    for frag in frags:
        if frag[0] == HEADING and frag[3] in HEADINGS:
            current = frag[3]
        elif frag[0] == TITLE:
            continue
        else:
            sections[current].append(frag)

    return {
        "id": path.stem.split("_")[1],
        "source": str(path.relative_to(ROOT)),
        "title": clean(" ".join(title_parts)),
        "dialogue": parse_dialogue(sections["dialogue"]),
        "key_vocabulary": parse_vocab(sections[HEADINGS[0]]),
        "supplementary_vocabulary": parse_vocab(sections[HEADINGS[1]]),
    }


def main():
    targets = sorted(PDF_DIR.glob("*/englishpod_*.pdf"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    problems = []
    for path in targets:
        data = extract(path)
        (OUT_DIR / f"{path.stem}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if not data["title"] or not data["dialogue"]:
            problems.append(data["source"])
    print(f"extracted {len(targets)} lessons -> {OUT_DIR}")
    if problems:
        print(f"{len(problems)} incomplete:", *problems, sep="\n  ", file=sys.stderr)


if __name__ == "__main__":
    main()
