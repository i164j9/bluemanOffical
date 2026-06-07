import datetime

from blueman.plugins.manager.Notes import build_note_data, normalize_note_text


class TestNotes:
    def test_normalize_note_text_collapses_lines_and_trims(self) -> None:
        assert normalize_note_text("  hello\nworld  ") == "hello world"

    def test_build_note_data_returns_none_for_blank_text(self) -> None:
        assert build_note_data("  \n  ") is None

    def test_build_note_data_embeds_normalized_body(self) -> None:
        result = build_note_data("hello\nworld", datetime.datetime(2024, 1, 2, 3, 4, 5))

        assert result is not None
        assert "BODY;CHARSET=UTF-8: hello world" in result
        assert "DCREATED:20240102T030400" in result
        assert "LAST-MODIFIED:20240102T030400" in result