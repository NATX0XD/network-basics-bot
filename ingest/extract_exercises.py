# -*- coding: utf-8 -*-
"""The end-of-chapter tests: their answers, and a picture of each page.

  ingest/exercise_key_network.md       the answer key, written by hand
  data/raw/network/network-basics.pdf  the scan the pages are read from
      -> data/processed/exercises_network.json
         web/exercises/page-031.jpg ...

The book prints the tests and no answers to them. The key was written from the
book's own chapters, every answer with the page it rests on, and it is the only
thing here that is hand-made: this script reads it, it does not write it. An
answer the book does not state outright is marked with a star in the key and
carried as `unsure`, with the note that says why, so that the page showing it
can say so too.

Which page a question is printed on is written out below rather than read from
the scan. The OCR of those pages drops option letters and runs the true/false
items into one line; a page worked out from that would be wrong in places and
there would be nothing to show which. The table is checked against the key:
a question with no page, or a page with a question the key does not have, stops
the run.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import BASE_DIR, PROCESSED_DIR, RAW_DIR  # noqa: E402
from ingest.extract_book_pages import scan_page  # noqa: E402

KEY_PATH = os.path.join(BASE_DIR, "ingest", "exercise_key_network.md")
PDF_PATH = os.path.join(RAW_DIR, "network", "network-basics.pdf")
OUT_DIR = os.path.join(BASE_DIR, "web", "exercises")
INDEX_PATH = os.path.join(PROCESSED_DIR, "exercises_network.json")

DPI = 110
JPEG_QUALITY = 72

# (chapter, part) -> the pages its questions are on, each with the first and
# the last question printed there. The page number is the one printed on the
# page; from chapter 6 on that is not its position in the scan, which is two
# leaves short (see ingest/extract_book_pages.py).
PAGES: dict[tuple[int, int], list[tuple[int, int, int]]] = {
    (1, 1): [(31, 1, 6), (32, 7, 12), (33, 13, 19), (34, 20, 25), (35, 26, 30)],
    (1, 2): [(35, 1, 1), (36, 2, 5), (37, 6, 9), (38, 10, 10)],
    (2, 1): [(71, 1, 7), (72, 8, 15), (73, 16, 22), (74, 23, 27), (75, 28, 30)],
    (2, 2): [(75, 1, 2), (76, 3, 6), (77, 7, 10), (78, 11, 14), (79, 15, 15)],
    (3, 1): [(111, 1, 7), (112, 8, 14), (113, 15, 20)],
    (3, 2): [(113, 1, 3), (114, 4, 25)],
    (3, 3): [(115, 1, 2), (116, 3, 5), (117, 6, 8), (118, 9, 11), (119, 12, 14),
             (120, 15, 17), (121, 18, 20)],
    (4, 1): [(168, 1, 10)],
    (4, 2): [(169, 1, 3), (170, 4, 6), (171, 7, 10), (172, 11, 14), (173, 15, 15)],
    (5, 1): [(222, 1, 3), (223, 4, 6), (224, 7, 10)],
    (7, 1): [(291, 1, 3), (292, 4, 5)],
}
# Pages of a test that carry practical work only, or carry it beside the
# questions: there is a picture of them, and nothing to reveal on the first kind.
PRACTICAL: dict[int, list[int]] = {4: [173, 174], 5: [225], 6: [261], 7: [292]}

CHAPTER = re.compile(r"^## บทที่ (\d+) (.+?)\s*\((?:แบบทดสอบ )?น\. [\d–\-]+\)\s*$")
PART = re.compile(r"^### ตอนที่ (\d+) (.+?)\s*$")
ROW = re.compile(r"^\|\s*(\d{1,2})\s*(★)?\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$")
STARRED = re.compile(r"^★ ข้อ (\d{1,2}):\s*(.+)$")
ESSAY = re.compile(r"^\*\*(\d{1,2})\. (.+?)\*\*\s*(.*)$")
TABLE_RULE = re.compile(r"^\|[\s:\-|]+\|$")
KINDS = (("ปรนัย", "choice"), ("ถูก/ผิด", "truefalse"), ("อัตนัย", "essay"),
         ("กิจกรรม", "practical"))
KIND_NAMES = {"choice": "ปรนัย", "truefalse": "ถูก/ผิด", "essay": "อัตนัย"}


def kind_of(title: str) -> str:
    for word, kind in KINDS:
        if word in title:
            return kind
    raise SystemExit(f"ไม่รู้ว่าตอนนี้เป็นข้อสอบแบบไหน: {title!r}")


def as_blocks(lines: list[str]) -> list[dict]:
    """The body of a written answer as what the page can draw without a
    Markdown reader: runs of text, and the diagrams, which need their spacing."""
    blocks: list[dict] = []
    text: list[str] = []
    fenced: list[str] | None = None

    def flush() -> None:
        body = "\n".join(text).strip()
        if body:
            blocks.append({"type": "text", "text": body})
        text.clear()

    for line in lines:
        if line.startswith("```"):
            if fenced is None:
                flush()
                fenced = []
            else:
                blocks.append({"type": "pre", "text": "\n".join(fenced)})
                fenced = None
            continue
        if fenced is not None:
            fenced.append(line)
            continue
        if TABLE_RULE.match(line):
            continue
        if line.startswith("|"):
            line = " — ".join(cell.strip() for cell in line.strip("|").split("|"))
        line = line.replace("**", "")
        text.append("• " + line[2:] if line.startswith("- ") else line)
    if fenced is not None:
        raise SystemExit("เฉลยมีบล็อก ``` ที่ไม่ได้ปิด")
    flush()
    return blocks


def read_key(path: str = KEY_PATH) -> dict[int, dict]:
    """The key as {chapter: {title, parts: [...], items: [...]}}, in book order."""
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    chapters: dict[int, dict] = {}
    chapter = part = None
    essay: dict | None = None
    body: list[str] = []

    def close_essay() -> None:
        nonlocal essay
        if essay is not None:
            essay["blocks"] = as_blocks(body)
            if not essay["blocks"]:
                raise SystemExit(f"บทที่ {chapter['chapter']} ข้อ {essay['number']} ไม่มีคำตอบ")
            essay = None
        body.clear()

    for line in lines:
        head = CHAPTER.match(line)
        if head:
            close_essay()
            chapter = {"chapter": int(head.group(1)), "title": head.group(2),
                       "parts": [], "items": []}
            chapters[chapter["chapter"]] = chapter
            part = None
            continue
        if chapter is None:
            continue
        head = PART.match(line)
        if head:
            close_essay()
            part = {"part": int(head.group(1)), "kind": kind_of(head.group(2)),
                    "title": head.group(2)}
            if part["kind"] != "practical":
                chapter["parts"].append(part)
            continue
        if part is None or part["kind"] == "practical" or line.strip() == "---":
            close_essay()
            continue
        if part["kind"] == "essay":
            head = ESSAY.match(line)
            if head:
                close_essay()
                title = head.group(2)
                essay = {"part": part["part"], "kind": "essay",
                         "number": int(head.group(1)),
                         "title": title.replace("★", "").strip(),
                         "unsure": "★" in title}
                chapter["items"].append(essay)
                if head.group(3):
                    body.append(head.group(3))
            elif essay is not None:
                body.append(line)
            continue
        row = ROW.match(line)
        if row:
            chapter["items"].append({
                "part": part["part"], "kind": part["kind"], "number": int(row.group(1)),
                "answer": row.group(3), "reason": row.group(4),
                "unsure": bool(row.group(2))})
            continue
        note = STARRED.match(line)
        if note:
            for item in chapter["items"]:
                if item["part"] == part["part"] and item["number"] == int(note.group(1)):
                    if not item["unsure"]:
                        raise SystemExit(f"หมายเหตุ ★ ของข้อที่ไม่ได้ติด ★: {line}")
                    item["note"] = note.group(2)
                    break
            else:
                raise SystemExit(f"หมายเหตุ ★ ชี้ข้อที่ไม่มีในเฉลย: {line}")
    close_essay()
    return chapters


def place(chapters: dict[int, dict]) -> None:
    """Give every question its page, and stop if the two lists disagree."""
    for chapter in chapters.values():
        n = chapter["chapter"]
        pages: set[int] = set(PRACTICAL.get(n, []))
        for part in chapter["parts"]:
            spans = PAGES.get((n, part["part"]))
            if not spans:
                raise SystemExit(f"บทที่ {n} ตอนที่ {part['part']} ไม่มีเลขหน้าใน PAGES")
            where = {number: page for page, first, last in spans
                     for number in range(first, last + 1)}
            items = [i for i in chapter["items"] if i["part"] == part["part"]]
            keyed = [i["number"] for i in items]
            if keyed != sorted(where):
                raise SystemExit(
                    f"บทที่ {n} ตอนที่ {part['part']}: เฉลยมีข้อ {keyed} "
                    f"แต่ PAGES มีข้อ {sorted(where)}")
            for item in items:
                item["page"] = where[item["number"]]
            part["count"] = len(items)
            pages |= set(where.values())
        chapter["pages"] = sorted(pages)
        if not chapter["pages"]:
            raise SystemExit(f"บทที่ {n} ไม่มีหน้าแบบทดสอบ")
    for (n, part) in PAGES:
        if n not in chapters or part not in {p["part"] for p in chapters[n]["parts"]}:
            raise SystemExit(f"PAGES มีบทที่ {n} ตอนที่ {part} แต่เฉลยไม่มี")


def render(pages: list[int]) -> dict[str, dict]:
    import pymupdf
    from PIL import Image

    if not os.path.exists(PDF_PATH):
        raise SystemExit(f"ไม่พบ {PDF_PATH}")
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in os.listdir(OUT_DIR):
        if name.startswith("page-") and name.endswith(".jpg"):
            os.remove(os.path.join(OUT_DIR, name))
    images: dict[str, dict] = {}
    with pymupdf.open(PDF_PATH) as pdf:
        for page in pages:
            if not 1 <= scan_page(page) <= len(pdf):
                raise SystemExit(f"PDF ไม่มีหน้า {page}")
            pix = pdf[scan_page(page) - 1].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            name = f"page-{page:03d}.jpg"
            image.save(os.path.join(OUT_DIR, name), "JPEG", quality=JPEG_QUALITY,
                       optimize=True)
            images[str(page)] = {"file": name, "width": pix.width, "height": pix.height}
    return images


def main() -> None:
    chapters = read_key()
    place(chapters)
    pages = sorted({page for c in chapters.values() for page in c["pages"]})
    images = render(pages)
    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump({"chapters": {str(n): c for n, c in sorted(chapters.items())},
                   "images": images}, handle, ensure_ascii=False, indent=1)
    size = sum(os.path.getsize(os.path.join(OUT_DIR, i["file"])) for i in images.values())
    for n, chapter in sorted(chapters.items()):
        counts = ", ".join(f"{KIND_NAMES[p['kind']]} {p['count']}" for p in chapter["parts"])
        starred = sum(i["unsure"] for i in chapter["items"])
        print(f"บทที่ {n}: {counts or 'ภาคปฏิบัติอย่างเดียว'} | หน้า {chapter['pages'][0]}-"
              f"{chapter['pages'][-1]} | ติด ★ {starred} ข้อ")
    print(f"{sum(len(c['items']) for c in chapters.values())} ข้อ, "
          f"{len(images)} หน้า, {size / 1e6:.1f} MB -> {INDEX_PATH}")


if __name__ == "__main__":
    main()
