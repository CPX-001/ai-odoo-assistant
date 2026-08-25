from odoo_ai.adapters.agent_streaming import AnswerMarkdownDeltaExtractor


def test_extractor_streams_only_answer_markdown_across_arbitrary_chunks() -> None:
    extractor = AnswerMarkdownDeltaExtractor()
    raw = (
        '{"confidence":"high","answer_markdown":"Primera línea\\nSegunda '
        'línea","steps":[{"arguments":{"secret":"never-stream"}}]}'
    )
    chunks = [raw[:7], raw[7:31], raw[31:48], raw[48:59], raw[59:]]

    visible = "".join(extractor.feed(chunk) for chunk in chunks)

    assert visible == "Primera línea\nSegunda línea"
    assert "steps" not in visible
    assert "never-stream" not in visible
    assert extractor.completed is True


def test_extractor_decodes_json_escapes_and_surrogate_pair() -> None:
    extractor = AnswerMarkdownDeltaExtractor()

    visible = "".join(
        extractor.feed(chunk)
        for chunk in (
            '{"answer_markdown":"A \\',
            '"quote\\" y emoji \\uD83D',
            '\\uDE80","confidence":"low"}',
        )
    )

    assert visible == 'A "quote" y emoji 🚀'


def test_extractor_ignores_same_text_inside_other_values() -> None:
    extractor = AnswerMarkdownDeltaExtractor()
    raw = (
        '{"goal":"texto \\"answer_markdown\\" falso",'
        '"answer_markdown":"respuesta visible","steps":[]}'
    )

    visible = extractor.feed(raw)

    assert visible == "respuesta visible"


def test_extractor_fails_closed_when_target_is_not_a_string() -> None:
    extractor = AnswerMarkdownDeltaExtractor()

    assert extractor.feed('{"answer_markdown":null,"steps":[]}') == ""
    assert extractor.completed is True


def test_extractor_stops_before_exceeding_visible_byte_budget() -> None:
    extractor = AnswerMarkdownDeltaExtractor(max_output_bytes=4)

    visible = extractor.feed('{"answer_markdown":"12345","steps":[]}')

    assert visible == "1234"
    assert extractor.completed is True
