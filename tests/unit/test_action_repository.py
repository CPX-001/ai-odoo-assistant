from odoo_ai.storage.action_repository import _constant_time_text_equal


def test_canonical_payload_comparison_supports_unicode_business_values() -> None:
    canonical = '{"name":"AI TEST Catálogo español"}'

    assert _constant_time_text_equal(canonical, canonical)
    assert not _constant_time_text_equal(
        canonical,
        '{"name":"AI TEST Catalogo espanol"}',
    )
