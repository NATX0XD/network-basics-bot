# -*- coding: utf-8 -*-
"""Every page of the textbook as a picture, for the reader on the web page.

  data/raw/network/network-basics.pdf  the scan
  data/processed/corpus_network.jsonl  the chapters' titles
      -> web/book/page-001.jpg ... page-291.jpg
         web/book/pages.json

The scan is 80 MB in one file and has no text layer. A browser asked to open it
would fetch all of it to show page one, and the host this runs on has 512 MB.
A page as a grey JPEG is about 75 kB, and the reader fetches the two it is
showing.

The scan is two leaves short. The page numbers printed at the foot of the
pages run 1..225, then 228..261, then 264..293: the unnumbered title pages of
chapters 6 and 7 are there (227 and 263), and the blank pages facing them (226
and 262) are not. Files are named by the printed number, because that is the
number a reader holding the book sees, and pages.json lists the two that are
missing so the reader can leave their side of the spread empty.

Note for whoever reads the corpus: ingest/extract_book.py numbers pages by
their position in the scan, so a citation into chapter 6 is one less than the
printed page and into chapter 7 two less.

The book is the copyright of SE-EDUCATION Public Company Limited. These files
put the whole of it on the web page; whether to publish them is the owner's
decision and is made at commit time, not here.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import BASE_DIR, RAW_DIR, settings  # noqa: E402

PDF_PATH = os.path.join(RAW_DIR, "network", "network-basics.pdf")
OUT_DIR = os.path.join(BASE_DIR, "web", "book")
INDEX_PATH = os.path.join(OUT_DIR, "pages.json")

DPI = 110
JPEG_QUALITY = 70
# Printed pages the scan does not have. Checked against the folios on the
# pages either side of each: 225 is followed by 228 with one unnumbered page
# between, 261 by 264 likewise.
MISSING = (226, 262)
# The page each chapter opens on: its title page, a right-hand page, as the
# book's own contents list gives it. Checked against the pictures.
CHAPTER_PAGES = {1: 11, 2: 39, 3: 81, 4: 123, 5: 175, 6: 227, 7: 263}
FRONT = [("ปก", 1), ("คำนำ", 5), ("สารบัญ", 7)]


def scan_page(printed: int) -> int:
    """Where in the PDF, counting from 1, the page printed as `printed` is."""
    if printed in MISSING:
        raise SystemExit(f"หน้า {printed} ไม่มีในไฟล์สแกน")
    return printed - sum(1 for gap in MISSING if gap < printed)


def chapter_titles() -> dict[int, str]:
    titles: dict[int, str] = {}
    with open(settings.book_path, encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            titles.setdefault(rec["chapter"], rec["chapter_title"])
    if sorted(titles) != sorted(CHAPTER_PAGES):
        raise SystemExit(f"คลังมีบท {sorted(titles)} แต่ CHAPTER_PAGES มี {sorted(CHAPTER_PAGES)}")
    return titles


def main() -> None:
    import pymupdf
    from PIL import Image

    if not os.path.exists(PDF_PATH):
        raise SystemExit(f"ไม่พบ {PDF_PATH}")
    titles = chapter_titles()
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in os.listdir(OUT_DIR):
        if name.startswith("page-") and name.endswith(".jpg"):
            os.remove(os.path.join(OUT_DIR, name))
    sizes: dict[tuple[int, int], int] = {}
    total = 0
    with pymupdf.open(PDF_PATH) as pdf:
        pages = len(pdf) + len(MISSING)
        for n in range(1, pages + 1):
            if n in MISSING:
                continue
            # the cover is the one page printed in colour
            colour = pymupdf.csRGB if n == 1 else pymupdf.csGRAY
            pix = pdf[scan_page(n) - 1].get_pixmap(dpi=DPI, colorspace=colour)
            image = Image.frombytes("RGB" if n == 1 else "L", (pix.width, pix.height),
                                    pix.samples)
            path = os.path.join(OUT_DIR, f"page-{n:03d}.jpg")
            image.save(path, "JPEG", quality=JPEG_QUALITY, optimize=True)
            sizes[(pix.width, pix.height)] = sizes.get((pix.width, pix.height), 0) + 1
            total += os.path.getsize(path)
    width, height = max(sizes, key=sizes.get)
    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump({
            "pages": pages, "missing": list(MISSING), "width": width, "height": height,
            "sections": [{"title": title, "page": page} for title, page in FRONT]
                        + [{"title": f"บทที่ {n} {titles[n]}", "page": page, "chapter": n}
                           for n, page in sorted(CHAPTER_PAGES.items())],
        }, handle, ensure_ascii=False, indent=1)
    print(f"{pages} หน้า {total / 1e6:.1f} MB ขนาดหน้า {width}x{height} "
          f"(ขนาดอื่น {len(sizes) - 1} แบบ) -> {OUT_DIR}")


if __name__ == "__main__":
    main()
