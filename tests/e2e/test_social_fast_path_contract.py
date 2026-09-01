from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOCIAL = ROOT / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "social.py"
HOST = ROOT / "addons" / "odoo_ai_assistant" / "models" / "embedded_runtime_host_loop.py"


def _load_social():
    spec = importlib.util.spec_from_file_location("social_contract", SOCIAL)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TestSocialFastPathContract(unittest.TestCase):
    def test_exact_social_messages_are_local_and_business_requests_fall_through(self):
        social = _load_social()
        self.assertEqual(
            social.simple_social_answer("hola", lang="es_ES"),
            "¡Hola! ¿En qué puedo ayudarte?",
        )
        self.assertTrue(
            social.simple_social_answer("thanks", lang="en_US").startswith("You're welcome!")
        )
        self.assertEqual(social.simple_social_answer("adiós", lang="es_ES"), "¡Hasta luego!")
        self.assertIsNone(social.simple_social_answer("hola, crea una factura", lang="es_ES"))
        self.assertIsNone(social.simple_social_answer("crea 30 presupuestos", lang="es_ES"))

    def test_host_answers_social_messages_before_runtime_and_activity_setup(self):
        source = HOST.read_text(encoding="utf-8")
        fast_path = source.index("social_answer = simple_social_answer(")
        self.assertLess(
            fast_path,
            source.index("registry = discover_capabilities_for_env(self.env)", fast_path),
        )
        self.assertLess(fast_path, source.index("settings = self._codex_settings(turn)", fast_path))
        block = source[
            fast_path : source.index("registry = discover_capabilities_for_env(self.env)", fast_path)
        ]
        self.assertNotIn("reasoning.started", block)


if __name__ == "__main__":
    unittest.main()
