from unittest import TestCase

from ..runtime.agent.model_catalog import (
    CodexModelCatalogError,
    parse_codex_model_catalog,
)


class TestCodexModelCatalog(TestCase):
    def _payload(self):
        efforts = [
            {"reasoningEffort": "none", "description": "Fast"},
            {"reasoningEffort": "medium", "description": "Balanced"},
            {"reasoningEffort": "max", "description": "Deep"},
        ]
        return {
            "data": [
                {
                    "model": "gpt-5.6",
                    "displayName": "GPT-5.6",
                    "description": "Family alias",
                    "isDefault": True,
                    "supportedReasoningEfforts": efforts,
                    "defaultReasoningEffort": "medium",
                },
                {
                    "model": "gpt-5.6-sol",
                    "displayName": "GPT-5.6 Sol",
                    "description": "Flagship",
                    "isDefault": False,
                    "supportedReasoningEfforts": efforts,
                    "defaultReasoningEffort": "medium",
                },
                {
                    "model": "gpt-5.6-terra",
                    "displayName": "GPT-5.6 Terra",
                    "description": "Balanced",
                    "isDefault": False,
                    "supportedReasoningEfforts": efforts,
                    "defaultReasoningEffort": "medium",
                },
                {
                    "model": "gpt-5.6-luna",
                    "displayName": "GPT-5.6 Luna",
                    "description": "Fast",
                    "isDefault": False,
                    "supportedReasoningEfforts": efforts,
                    "defaultReasoningEffort": "medium",
                },
            ]
        }

    def test_named_variants_share_one_family_and_expose_reasoning_metadata(self):
        catalog = parse_codex_model_catalog(self._payload())
        by_model = {item["model"]: item for item in catalog["models"]}

        self.assertEqual(catalog["default_model"], "gpt-5.6")
        self.assertEqual(by_model["gpt-5.6-sol"]["family"], "gpt-5.6")
        self.assertEqual(by_model["gpt-5.6-sol"]["variant"], "sol")
        self.assertEqual(by_model["gpt-5.6-terra"]["variant"], "terra")
        self.assertEqual(by_model["gpt-5.6-luna"]["variant"], "luna")
        self.assertTrue(by_model["gpt-5.6"]["family_alias"])
        self.assertEqual(by_model["gpt-5.6"]["variant"], "sol")
        self.assertEqual(by_model["gpt-5.6-sol"]["default_reasoning_effort"], "medium")
        self.assertEqual(
            [item["effort"] for item in by_model["gpt-5.6-sol"]["supported_reasoning_efforts"]],
            ["none", "medium", "max"],
        )

    def test_unknown_model_stays_as_an_ungrouped_family(self):
        payload = {
            "data": [
                {
                    "model": "other-model",
                    "displayName": "Other Model",
                    "description": "",
                    "isDefault": True,
                }
            ]
        }
        catalog = parse_codex_model_catalog(payload)
        model = catalog["models"][0]
        self.assertEqual(model["family"], "other-model")
        self.assertIsNone(model["variant"])
        self.assertEqual(model["supported_reasoning_efforts"], [])

    def test_invalid_default_reasoning_effort_is_rejected(self):
        payload = self._payload()
        payload["data"][1]["defaultReasoningEffort"] = "unsupported"
        with self.assertRaises(CodexModelCatalogError):
            parse_codex_model_catalog(payload)

    def test_default_reasoning_effort_without_supported_catalog_is_rejected(self):
        payload = self._payload()
        payload["data"][1]["supportedReasoningEfforts"] = []
        with self.assertRaises(CodexModelCatalogError):
            parse_codex_model_catalog(payload)
