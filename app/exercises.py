# -*- coding: utf-8 -*-
"""The end-of-chapter tests, with the answers written for them.

The book prints a test at the end of each chapter and no answers. The key in
data/processed/exercises_network.json was written from the chapters themselves
(ingest/extract_exercises.py reads it from ingest/exercise_key_network.md) and
is the publisher's in no sense, which every reply that shows an answer says.

Nothing here is asked of the model. Which chapter, which part and which
question a message means are read from the message; the answer is copied from
the key. A message that asks for a test without saying which chapter is given
the chapter the chat was last answered from, if the caller knows it, and the
list of chapters otherwise.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from app.articles import THAI_DIGITS
from app.config import PROCESSED_DIR

log = logging.getLogger(__name__)

INDEX_PATH = os.path.join(PROCESSED_DIR, "exercises_network.json")
IMAGES_URL = "/static/exercises/"

# "ทดสอบ" on its own is not here: "คำสั่ง ping ใช้ทดสอบอะไร" is a question for
# the book.
ASKED = re.compile(r"แบบฝึกหัด|แบบทดสอบ|ข้อสอบ|โจทย์ท้ายบท|ทำโจทย์|เฉลย|ควิซ|quiz", re.I)
CHAPTER = re.compile(r"บท(?:ที่)?\s*(\d{1,2})")
# Asking which tests there are. This is answered with the list even when the
# chat is on a chapter: "เลือกบทอื่น" under chapter 2's test must not open
# chapter 2's test again.
WHICH = re.compile(r"ทุกบท|ทั้งหมด|บทอื่น|บทไหน|เลือกบท|กี่บท|มีบทอะไร")
PART = re.compile(r"ตอน(?:ที่)?\s*(\d)")
NUMBER = re.compile(r"ข้อ(?:ที่)?\s*(\d{1,2})")
KIND_WORDS = (("choice", re.compile(r"ปรนัย|ตัวเลือก|ช้อย")),
              ("truefalse", re.compile(r"ถูก\s*/?\s*ผิด|ถูกหรือผิด")),
              ("essay", re.compile(r"อัตนัย|เขียนตอบ")))
KIND_NAMES = {"choice": "ปรนัย", "truefalse": "ถูก/ผิด", "essay": "อัตนัย"}

NOTICE = ("ℹ️ หนังสือไม่ได้พิมพ์เฉลยไว้ เฉลยชุดนี้จัดทำจากเนื้อหาในหนังสือ ไม่ใช่เฉลยของสำนักพิมพ์ "
          "ข้อที่มี ★ หนังสือไม่ได้ระบุคำตอบตรงตัว ควรตรวจกับครูผู้สอน")
PRACTICAL_ONLY = "แบบทดสอบของบทนี้เป็นงานภาคปฏิบัติทั้งหมด จึงไม่มีเฉลยเป็นข้อเขียนครับ"

_index: Optional[dict] = None
_loaded = False


def get_index() -> Optional[dict]:
    """The key, or None when it was never built. Absent is a state, as the
    figures are: the bot answers from the book without its tests. Logged once."""
    global _index, _loaded
    if not _loaded:
        _loaded = True
        if os.path.exists(INDEX_PATH):
            with open(INDEX_PATH, encoding="utf-8") as handle:
                raw = json.load(handle)
            _index = {"chapters": {int(n): c for n, c in raw["chapters"].items()},
                      "images": {int(p): i for p, i in raw["images"].items()}}
        else:
            log.warning("EXERCISES OFF: %s is missing -- run ingest.extract_exercises",
                        INDEX_PATH)
    return _index


def summary(chapter: int) -> Optional[dict]:
    """What a chapter's test holds, for a card that offers it."""
    index = get_index()
    row = index and index["chapters"].get(chapter)
    if not row:
        return None
    return {"chapter": chapter, "title": row["title"],
            "pages": [row["pages"][0], row["pages"][-1]],
            "parts": [{"part": p["part"], "kind": p["kind"], "count": p["count"]}
                      for p in row["parts"]],
            "questions": len(row["items"])}


def listing() -> list[dict]:
    index = get_index()
    return [summary(n) for n in sorted(index["chapters"])] if index else []


def chapter_set(chapter: int) -> Optional[dict]:
    """A chapter's test page by page: the picture, and what is answered on it."""
    index = get_index()
    row = index and index["chapters"].get(chapter)
    if not row:
        return None
    pages = []
    for page in row["pages"]:
        image = index["images"][page]
        pages.append({"page": page, "url": IMAGES_URL + image["file"],
                      "width": image["width"], "height": image["height"],
                      "items": [i for i in row["items"] if i["page"] == page]})
    return {**summary(chapter), "pages": pages, "notice": NOTICE}


def offer(chapter: Optional[int]) -> Optional[dict]:
    """The card put under an ordinary answer: this chapter has a test."""
    card = summary(chapter) if chapter else None
    # a chapter whose test is practical work only has nothing to offer here
    return {**card, "open": False} if card and card["questions"] else None


def wanted(question: str) -> bool:
    return bool(ASKED.search(question))


def describe(parts: list[dict]) -> str:
    return "\n".join(f"• ตอนที่ {p['part']} {KIND_NAMES[p['kind']]} {p['count']} ข้อ"
                     for p in parts)


def item_text(item: dict) -> str:
    """One answer as plain text, for a chat that cannot draw the page."""
    star = " ★" if item["unsure"] else ""
    head = f"ตอนที่ {item['part']} ({KIND_NAMES[item['kind']]}) ข้อ {item['number']}{star} หน้า {item['page']}"
    if item["kind"] == "essay":
        body = "\n\n".join(b["text"] for b in item["blocks"])
        return f"{head}\n{item['title']}\n{body}"
    text = f"{head}\nตอบ {item['answer']}\n{item['reason']}"
    if item.get("note"):
        text += f"\n★ {item['note']}"
    return text


def reply(question: str, chapter: Optional[int] = None):
    """An Answer to a message about the tests, or None if it is not one.

    `chapter` is the chapter the chat was last answered from. It is used only
    when the message names none.
    """
    from app.answer import Answer   # answer.py imports book.py, which imports this

    if not wanted(question):
        return None
    index = get_index()
    if index is None:
        return None
    asked = question.translate(THAI_DIGITS)
    named = CHAPTER.search(asked)
    n = int(named.group(1)) if named else None if WHICH.search(asked) else chapter
    if n is None or n not in index["chapters"]:
        rows = "\n".join(
            f"• บทที่ {c['chapter']} {c['title']} — "
            + (f"{c['questions']} ข้อ" if c["questions"] else "ภาคปฏิบัติ")
            for c in listing())
        lead = (f"หนังสือมี {len(index['chapters'])} บท ไม่มีบทที่ {n} ครับ "
                if n is not None else "")
        log.info("EXERCISES MENU | %r", question[:60])
        return Answer(
            text=f"{lead}เลือกบทที่อยากทำแบบทดสอบได้เลยครับ\n\n{rows}\n\n{NOTICE}",
            source="exercise", exercise={"menu": listing()})

    row = index["chapters"][n]
    card = {**summary(n), "open": True}
    first, last = row["pages"][0], row["pages"][-1]
    head = (f"แบบทดสอบท้ายบทที่ {n} {row['title']} "
            f"(หน้า {first if first == last else f'{first}-{last}'})")
    if not row["items"]:
        log.info("EXERCISES ch%d practical only | %r", n, question[:60])
        return Answer(text=f"{head}\n\n{PRACTICAL_ONLY}", source="exercise", exercise=card)

    number = NUMBER.search(asked)
    if number:
        part = PART.search(asked)
        kinds = [k for k, pattern in KIND_WORDS if pattern.search(asked)]
        found = [i for i in row["items"] if i["number"] == int(number.group(1))
                 and (not part or i["part"] == int(part.group(1)))
                 and (not kinds or i["kind"] in kinds)]
        if found:
            card["page"] = found[0]["page"]
            body = "\n\n".join(item_text(i) for i in found)
            log.info("EXERCISE ANSWER ch%d %s | %r", n,
                     [(i["part"], i["number"]) for i in found], question[:60])
            return Answer(text=f"{head}\n\n{body}\n\n{NOTICE}", source="exercise",
                          exercise=card)
        return Answer(
            text=(f"{head}\n\nไม่มีข้อ {number.group(1)} ในตอนที่ถามครับ บทนี้มี\n"
                  f"{describe(row['parts'])}"),
            source="exercise", exercise=card)

    log.info("EXERCISES ch%d | %r", n, question[:60])
    return Answer(
        text=(f"{head}\n\n{describe(row['parts'])}\n\n"
              "ลองทำจากรูปแต่ละหน้าก่อน แล้วค่อยเปิดเฉลยดูได้เลยครับ "
              f"หรือพิมพ์ถามเป็นข้อ เช่น เฉลยบทที่ {n} ตอนที่ {row['parts'][0]['part']} ข้อ 1\n\n"
              f"{NOTICE}"),
        source="exercise", exercise=card)
