"""Tests for the markdown parser."""

from ppke.parser.markdown import parse_markdown_text
from ppke.parser.models import DepthLevel


SAMPLE_BOOK = """\
# Chapter 1: The Problem of Being

The question of Being has today been forgotten. Even though in our time
we deem it progressive to give our approval to metaphysics again, it is
held that we have been exempted from the exertions of a newly rekindled
gigantomachy peri tes ousias.

Yet the question touched upon is not just any question. It is one which
provided a stimulus for the researches of Plato and Aristotle, only to
subside from then on as a theme for actual investigation.

What these two thinkers achieved was to persist through many alterations
and retouchings down to the logic of Hegel. And what they wrested with
the utmost intellectual effort from the phenomena was cruder and more
naive than what we have today.

# Chapter 2: The Double Task

The question of the meaning of Being must be formulated. If it is a
fundamental question, or indeed the fundamental question, it must be
made transparent in the appropriate way.

We must therefore explain briefly what belongs to any question whatsoever,
so as to make it visible that the question of Being is an eminent one.

Every inquiry is a seeking. Every seeking gets guided beforehand by what
is sought. Inquiry is a cognizant seeking for an entity both with regard
to the fact that it is and with regard to its Being as it is.
"""


def test_parse_chapters():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger", "1927")
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "The Problem of Being"
    assert book.chapters[1].title == "The Double Task"


def test_parse_paragraphs():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger")
    ch1 = book.chapters[0]
    ch2 = book.chapters[1]
    assert ch1.paragraph_count == 3
    assert ch2.paragraph_count == 3


def test_paragraph_ids():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger")
    ch1 = book.chapters[0]
    assert ch1.paragraphs[0].paragraph_id == "{01}.p1"
    assert ch1.paragraphs[1].paragraph_id == "{01}.p2"
    assert ch1.paragraphs[2].paragraph_id == "{01}.p3"

    ch2 = book.chapters[1]
    assert ch2.paragraphs[0].paragraph_id == "{02}.p1"


def test_total_paragraphs():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger")
    assert book.total_paragraphs == 6


def test_all_paragraph_ids():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger")
    ids = book.all_paragraph_ids
    assert len(ids) == 6
    assert ids[0] == "{01}.p1"
    assert ids[-1] == "{02}.p3"


def test_folder_name():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger", "1927")
    assert book.folder_name == "Book_Being_and_Time_Heidegger_1927"


def test_verbatim_text():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger")
    first_para = book.chapters[0].paragraphs[0]
    assert "question of Being has today been forgotten" in first_para.text


def test_no_chapters_fallback():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    book = parse_markdown_text(text, "Test", "Author")
    assert len(book.chapters) == 1
    assert book.chapters[0].title == "Full Text"
    assert book.total_paragraphs == 3


def test_chapter_number_words():
    text = "# Chapter One: Introduction\n\nHello world.\n\n# Chapter Two: Body\n\nContent here."
    book = parse_markdown_text(text, "Test", "Author")
    assert len(book.chapters) == 2
    assert book.chapters[0].number == 1
    assert book.chapters[1].number == 2


def test_default_depth():
    book = parse_markdown_text(SAMPLE_BOOK, "Being and Time", "Heidegger")
    for p in book.all_paragraphs:
        assert p.depth == DepthLevel.LIGHT
