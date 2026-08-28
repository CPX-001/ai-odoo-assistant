from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "addons/odoo_ai_assistant/runtime/agent/answer_stream.py"
spec = importlib.util.spec_from_file_location("p4_answer_stream", MODULE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_final_answer_fragmentation_and_utf8_are_decoded_without_json_leak():
    extractor = module.StructuredFinalAnswerDeltaExtractor()
    chunks = []
    for delta in (
        '{"decision":{"kind":"final_',
        'answer","answer":"España, ping\\u00fcino, acci',
        '\\u00f3n, \\ud83d',
        '\\ude00. Texto suficientemente largo para activar la entrega incremental segura.',
        '","confidence":"high"}}',
    ):
        chunks.extend(extractor.feed(delta))
    text = "".join(chunks)
    assert text == "España, pingüino, acción, 😀. Texto suficientemente largo para activar la entrega incremental segura."
    assert "decision" not in text
    assert "confidence" not in text


def test_non_final_decisions_never_stream_arguments_or_plan_text():
    extractor = module.StructuredFinalAnswerDeltaExtractor()
    value = (
        '{"decision":{"kind":"plan_step_proposal","call_id":"c1",'
        '"capability":"odoo.record.patch","arguments_json":"{\\"secret\\":\\"x\\"}",'
        '"user_summary":"Cambiar registro"}}'
    )
    assert extractor.feed(value) == ()
    assert extractor.emitted_text == ""


def test_invalid_escape_fails_closed():
    extractor = module.StructuredFinalAnswerDeltaExtractor()
    try:
        extractor.feed('{"decision":{"kind":"final_answer","answer":"bad\\q')
    except module.AnswerStreamError:
        pass
    else:
        raise AssertionError("invalid JSON escape accepted")


def test_short_answer_flushes_only_when_answer_field_closes():
    extractor = module.StructuredFinalAnswerDeltaExtractor()
    assert extractor.feed('{"decision":{"kind":"final_answer","answer":"Hola') == ()
    assert extractor.feed('","confidence":"high"}}') == ("Hola",)
