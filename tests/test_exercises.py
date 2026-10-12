# -*- coding: utf-8 -*-
"""The end-of-chapter tests: what the key holds, which messages ask for it, and
that an answer shown was copied from the key rather than written."""
import asyncio
import os

import pytest
from fastapi import HTTPException

from app import book, exercises
from app.answer import Answer
from app.config import BASE_DIR
from ingest import extract_exercises

pytestmark = pytest.mark.skipif(
    not os.path.exists(exercises.INDEX_PATH),
    reason="key not built -- run ingest.extract_exercises")

# how many questions the book prints in each part, counted on its pages
PRINTED = {1: [30, 10], 2: [30, 15], 3: [20, 25, 20], 4: [10, 15], 5: [10], 6: [], 7: [5]}


def test_the_key_answers_every_question_the_book_prints():
    index = exercises.get_index()
    assert {n: [p["count"] for p in c["parts"]] for n, c in index["chapters"].items()} == PRINTED


def test_every_question_is_on_a_page_that_has_its_picture():
    index = exercises.get_index()
    for chapter in index["chapters"].values():
        for item in chapter["items"]:
            assert item["page"] in chapter["pages"]
        for page in chapter["pages"]:
            image = index["images"][page]
            assert os.path.exists(os.path.join(BASE_DIR, "web", "exercises", image["file"]))


def test_the_built_key_is_the_written_key():
    """The JSON is made by the script; a hand edit to either side shows here."""
    written = extract_exercises.read_key()
    extract_exercises.place(written)
    built = exercises.get_index()["chapters"]
    assert {n: c["items"] for n, c in written.items()} == {n: c["items"] for n, c in built.items()}


def test_an_answer_the_book_does_not_state_says_so():
    items = [i for c in exercises.get_index()["chapters"].values() for i in c["items"]]
    starred = [i for i in items if i["unsure"]]
    assert starred
    # a starred choice carries the note that says why; a starred essay says it
    # in its own first words
    assert all(i.get("note") for i in starred if i["kind"] != "essay")
    assert not [i for i in items if i.get("note") and not i["unsure"]]


@pytest.mark.parametrize("question", [
    "คำสั่ง ping ใช้ทดสอบอะไร", "สายแลนคืออะไร", "บทที่ 3 สอนเรื่องอะไร",
    "เครื่องวัดสายสัญญาณใช้ทดสอบสายแลนอย่างไร"])
def test_a_question_for_the_book_is_not_taken_for_one_about_the_tests(question):
    assert exercises.reply(question, 4) is None


def test_asking_for_a_test_with_no_chapter_means_the_chapter_the_chat_is_on():
    reply = exercises.reply("ทำแบบฝึกหัด", 4)
    assert reply.source == "exercise" and reply.exercise["chapter"] == 4
    assert reply.exercise["open"] is True


def test_with_no_chapter_known_the_asker_is_given_the_list():
    reply = exercises.reply("ขอทำแบบฝึกหัดหน่อย")
    assert [c["chapter"] for c in reply.exercise["menu"]] == [1, 2, 3, 4, 5, 6, 7]


def test_asking_for_another_chapter_gives_the_list_not_the_same_test_again():
    assert "menu" in exercises.reply("ขอเลือกแบบทดสอบบทอื่น", 2).exercise
    assert "menu" in exercises.reply("ขอดูแบบทดสอบท้ายบททุกบท", 2).exercise


def test_a_chapter_named_in_thai_digits_wins_over_the_one_the_chat_is_on():
    assert exercises.reply("ขอแบบทดสอบท้ายบทที่ ๓", 1).exercise["chapter"] == 3


def test_a_chapter_the_book_does_not_have_is_said_to_be_missing():
    reply = exercises.reply("เฉลยบทที่ 9")
    assert "ไม่มีบทที่ 9" in reply.text and "menu" in reply.exercise


def test_one_answer_is_copied_from_the_key_and_opens_at_its_page():
    reply = exercises.reply("เฉลยบทที่ 2 ตอนที่ 1 ข้อ 16")
    item = next(i for i in exercises.get_index()["chapters"][2]["items"]
                if i["part"] == 1 and i["number"] == 16)
    assert f"ตอบ {item['answer']}" in reply.text and item["reason"] in reply.text
    assert reply.exercise["page"] == item["page"] == 73
    assert exercises.NOTICE in reply.text


def test_a_number_in_two_parts_is_answered_for_both():
    reply = exercises.reply("เฉลยข้อ 1 บทที่ 3")
    assert all(f"ตอนที่ {part} " in reply.text for part in (1, 2, 3))
    only = exercises.reply("เฉลยข้อ 1 บทที่ 3 ถูกผิด")
    assert "ตอนที่ 2 (ถูก/ผิด)" in only.text and "ตอนที่ 1 (ปรนัย)" not in only.text


def test_a_question_number_the_part_does_not_have_is_not_answered():
    reply = exercises.reply("เฉลยบทที่ 1 ข้อ 40")
    assert "ไม่มีข้อ 40" in reply.text and "ตอบ " not in reply.text


def test_a_chapter_of_practical_work_only_is_shown_and_never_offered():
    reply = exercises.reply("แบบฝึกหัดบทที่ 6")
    assert reply.text.endswith(exercises.PRACTICAL_ONLY)
    assert exercises.offer(6) is None
    assert exercises.offer(1)["open"] is False
    assert exercises.offer(None) is None


def test_the_page_set_holds_each_question_once():
    for n, printed in PRINTED.items():
        found = exercises.chapter_set(n)
        assert sum(len(p["items"]) for p in found["pages"]) == sum(printed)
        assert all(p["url"].startswith("/static/exercises/page-") for p in found["pages"])
    assert exercises.chapter_set(8) is None


def test_the_chapter_of_an_answer_is_the_one_most_of_it_cites():
    def cited(chapter):
        return book.BookHit(rec={"chapter": chapter}, rrf=0.0)
    assert book.chapter_of([cited(2), cited(4), cited(4)]) == 4
    assert book.chapter_of([cited(2), cited(4)]) == 2
    assert book.chapter_of([]) is None


def test_a_message_about_the_tests_never_reaches_the_search(monkeypatch):
    def searched(*args, **kwargs):
        raise AssertionError("the book was searched")
    monkeypatch.setattr(book, "get_index", searched)
    reply = asyncio.run(book.answer("ทำแบบฝึกหัด", previous="สายแลนคืออะไร", chapter=4))
    assert reply.exercise["chapter"] == 4
    # "อธิบายเพิ่ม" after a test still goes on from the lesson
    assert reply.topic == "สายแลนคืออะไร"


def test_on_line_a_test_is_sent_as_text_once_without_the_book_notice():
    reply = exercises.reply("เฉลยบทที่ 4 ตอนที่ 1 ข้อ 9")
    assert isinstance(reply, Answer)
    messages = reply.for_line_messages()
    assert len(messages) == 1 and messages[0]["type"] == "text"
    assert book.DISCLAIMER not in messages[0]["text"]


def test_the_api_serves_a_chapter_and_refuses_one_that_is_not_there():
    from app import main
    assert asyncio.run(main.exercise_set(3))["questions"] == 65
    assert len(asyncio.run(main.exercise_list())["chapters"]) == 7
    with pytest.raises(HTTPException) as refused:
        asyncio.run(main.exercise_set(8))
    assert refused.value.status_code == 404


# --- the book reader's pages --------------------------------------------------

def test_a_printed_page_is_found_past_the_leaves_the_scan_lacks():
    from ingest.extract_book_pages import MISSING, scan_page

    assert MISSING == (226, 262)
    assert [scan_page(p) for p in (1, 225, 227, 261, 263, 293)] == [1, 225, 226, 260, 261, 291]
    with pytest.raises(SystemExit):
        scan_page(226)


def test_the_reader_has_a_picture_for_every_page_it_lists():
    import json

    folder = os.path.join(BASE_DIR, "web", "book")
    listed = os.path.join(folder, "pages.json")
    if not os.path.exists(listed):
        pytest.skip("book pages not built -- run ingest.extract_book_pages")
    with open(listed, encoding="utf-8") as handle:
        info = json.load(handle)
    for page in range(1, info["pages"] + 1):
        there = os.path.exists(os.path.join(folder, f"page-{page:03d}.jpg"))
        assert there != (page in info["missing"]), page
    assert all(s["page"] not in info["missing"] for s in info["sections"])


def test_practical_work_is_given_a_guide_and_never_counted_as_a_question():
    index = exercises.get_index()
    guided = {n: len(c["guides"]) for n, c in index["chapters"].items() if c["guides"]}
    assert guided == {4: 2, 5: 7, 6: 3, 7: 4}
    assert exercises.summary(6)["questions"] == 0
    page = exercises.chapter_set(6)["pages"][0]
    assert page["items"] == [] and [g["number"] for g in page["guides"]] == [1, 2, 3]
    for chapter in index["chapters"].values():
        for guide in chapter["guides"]:
            assert guide["kind"] == "practical" and guide["blocks"]
            assert guide["page"] in extract_exercises.PRACTICAL[chapter["chapter"]]
