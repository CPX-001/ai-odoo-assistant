from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
PICKER = (
    ROOT
    / "addons/odoo_ai_assistant/static/src/components/assistant_model/assistant_model.xml"
)
AUTONOMY_PICKER = (
    ROOT
    / "addons/odoo_ai_assistant/static/src/components/assistant_autonomy/assistant_autonomy.xml"
)
COMPOSER_STYLES = (
    ROOT
    / "addons/odoo_ai_assistant/static/src/components/assistant_panel/assistant_composer.scss"
)


def _picker_dropdown(tree, container_class):
    for container in tree.findall(".//div"):
        if container.attrib.get("class") == container_class:
            return container.find("Dropdown")
    raise AssertionError(f"missing picker container {container_class}")


def test_model_pickers_remain_openable_while_catalog_is_loading():
    tree = ElementTree.parse(PICKER)

    for container_class, saving_state in (
        ("o_ai_assistant_model_picker", "state.modelSaving"),
        ("o_ai_assistant_reasoning_picker", "state.reasoningEffortSaving"),
    ):
        dropdown = _picker_dropdown(tree, container_class)
        assert dropdown is not None
        assert "disabled" not in dropdown.attrib
        trigger = dropdown.find("button")
        assert trigger is not None
        assert trigger.attrib.get("t-att-disabled") == saving_state
        loading = dropdown.find(".//*[@t-if='state.modelLoading']")
        assert loading is not None
        assert "Cargando" in "".join(loading.itertext())


def test_failed_catalog_state_offers_a_retry_without_hiding_the_picker():
    tree = ElementTree.parse(PICKER)
    source = PICKER.read_text(encoding="utf-8")

    assert source.count('t-on-click="retryModelPreferences"') == 2
    assert "No se pudo cargar el catálogo de modelos." in source
    assert "No hay niveles de razonamiento disponibles para este modelo." in source
    assert tree.getroot() is not None


def test_model_menu_uses_compact_tokens_without_selection_ticks_or_duplicate_arrows():
    tree = ElementTree.parse(PICKER)
    dropdown = _picker_dropdown(tree, "o_ai_assistant_model_picker")
    source = ElementTree.tostring(dropdown, encoding="unicode")

    assert "o_ai_assistant_picker_option_token" in source
    assert "fa-check" not in source
    assert "fa-angle-right" not in source


def test_closed_preferences_use_one_compact_pill_row_with_full_accessible_titles():
    model_source = PICKER.read_text(encoding="utf-8")
    autonomy_source = AUTONOMY_PICKER.read_text(encoding="utf-8")
    composer_source = COMPOSER_STYLES.read_text(encoding="utf-8")

    assert 't-esc="reasoningModelPillLabel"' in model_source
    assert 't-esc="reasoningEffortPillLabel"' in model_source
    assert 't-esc="autonomyProfileLabel"' not in autonomy_source
    assert "t-att-title=\"'Autonomía: ' + autonomyProfileLabel\"" in autonomy_source
    assert '"model reasoning autonomy send"' in composer_source
    assert "justify-self: end" in composer_source
