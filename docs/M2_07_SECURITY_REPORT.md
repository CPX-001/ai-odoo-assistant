# M2-07 — Informe de seguridad de delegación y permisos

Fecha de ejecución: 2026-08-22. Baseline: Odoo 18 Community real, PostgreSQL
16 y addon actualizado sobre una base desechable.

Resultado: **PASS**.

## Matriz ejecutada

| Escenario | Resultado | Evidencia |
|---|---:|---|
| Usuario interno limitado, modelo e ID permitidos | PASS | `read_records` devuelve sólo el registro acotado bajo el `uid` delegado. |
| Modelo sin ACL (`ir.config_parameter`) | PASS | `access_denied`; mismo error sanitizado que un registro inexistente. |
| Record rule | PASS | Un `res.country` fuera de la regla y el pedido de otro comercial no se devuelven. |
| Campo restringido estándar | PASS | `res.users.request` no aparece en el schema efectivo y su lectura explícita es indistinguible de un campo desconocido (`invalid_fields`). |
| Multi-company | PASS | Un `res.partner` de compañía B queda oculto con delegación activa sólo para A. |
| Firma, versión y JSON canónico | PASS | Firma alterada, versión firmada incorrecta, claims duplicados y JSON no canónico se rechazan. |
| Turn, DB, usuario/compañía, modelo, IDs y scope | PASS | Ninguna manipulación amplía autoridad. |
| Límites de records, fields y bytes | PASS | Los excesos terminan en errores acotados antes de exponer datos. |
| Expiración y replay | PASS | Delegación expirada rechazada; cada `(jti, scope)` se consume una sola vez. |
| Identidad aportada por browser | PASS | `uid`, compañías, grupos y `display_name` inyectados se rechazan antes de firmar. |
| Higiene de secretos | PASS | El ledger no almacena tokens; respuestas, trazas y logs inspeccionados no contienen los secretos de prueba. |
| Superficie peligrosa | PASS | Escaneo estático sin `sudo()`, SQL directo, `execute_kw`, `execute_method` ni `SELECT *` en las piezas M2. |

## Corrección aplicada

M2 validaba firma y expiración, pero no consumía de forma persistente una
delegación válida. Se añadió un ledger técnico ORM con unicidad por
`(jti, scope)`. El flujo legítimo conserva exactamente una llamada a
`fields_get` y una a `read_records`; cualquier repetición de uno de esos scopes
se rechaza. El ledger guarda sólo nonce, scope y expiración, nunca el token
firmado, y elimina entradas expiradas mediante `@api.autovacuum`.

La creación del ledger está cerrada con un marcador interno no serializable.
Aunque el ACL técnico permite el `create` que necesita el usuario delegado, una
llamada ORM/RPC normal no puede invocar esa escritura.

## Verificaciones

```text
PYTHONPATH=service/src:. .venv/bin/pytest -q \
  tests/unit/test_delegation_codec.py tests/addon/test_addon_boundaries.py
# 21 passed

odoo-bin --update=odoo_ai_assistant --stop-after-init --test-enable \
  --test-tags=/odoo_ai_assistant ...
# odoo_ai_assistant: 28 tests; 0 failed, 0 errors
```

No se aceptó ninguna excepción a las invariantes del Source of Truth. El nonce
puede aparecer como identificador técnico en el log PostgreSQL de una colisión
concurrente; no es credencial, firma ni token y expira con el ledger.
