# M7-02 — Odoo Settings administrable

## Contexto

- Requiere M7-01 verde.
- Actualmente el addon sólo expone Diagnostics; no existe `res.config.settings` para el Assistant.
- La UI debe reflejar el contrato de ownership/provenance de M7-01, no inventar una segunda política de configuración.

## Objetivo

Añadir una superficie Odoo-native de Settings, accesible sólo a administradores del sistema, que muestre configuración efectiva/provenance y permita editar exclusivamente los overrides `ADMIN_MUTABLE` definidos por M7-01.

## Debes implementar

### Settings model/view

Extender `res.config.settings` o una superficie Odoo-native equivalente con secciones claras para:

- conexión Odoo → Assistant ya soportada (`service_url` y referencia de credencial cuando corresponda, nunca secret content);
- source/scanner operational overrides permitidos;
- log provider/selection permitida;
- knowledge roots/options permitidas;
- reasoning/runtime estado/configuración administrable sólo si el contrato M7-01 la clasifica como mutable;
- cualquier otro setting M0-M6 que realmente necesite cambio post-install y pase el boundary de M7-01.

No añadas knobs porque “podrían ser útiles”. Cada campo debe corresponder a un contrato/config consumer real.

### Effective value + provenance

La UI debe distinguir:

- valor efectivo;
- override solicitado/persistido;
- origen/provenance;
- readonly/host-owned;
- validation state;
- si requiere una acción posterior de setup/reload.

Un valor host-only puede aparecer de forma sanitizada para explicar estado, pero no debe renderizar secret/path sensible innecesario ni ser editable.

### Validación UX

- validar formato básico antes de guardar;
- errores específicos y accionables;
- no guardar parcialmente un formulario si un override crítico es inválido;
- no revelar exception/raw response del Assistant.

## Debes reutilizar

- contratos M7-01;
- `AssistantServiceClient`/machine auth existente;
- `ir.config_parameter` sólo para Odoo-side non-secret config que ya tenga sentido persistir allí;
- patrones de permisos `base.group_system` usados en Diagnostics.

## Fuera de scope

- aplicar cambios host-level;
- escribir systemd/config files como root;
- provisionar/rotar secretos;
- crear PostgreSQL roles/DBs;
- editar ActionPolicy/business-action allowlists desde UI;
- M8.

## Restricciones

- browser → Odoo únicamente;
- admin identity derivada server-side;
- no secret contents en fields, DOM, onchange, RPC o logs;
- no file picker/path libre que amplíe roots fuera del envelope;
- no SSRF mediante `service_url`: conservar validación loopback/allowlist del producto;
- no confiar readonly de la vista como enforcement; validar otra vez server-side.

## Tests obligatorios

- non-admin no puede leer/escribir Settings del Assistant;
- host-only se mantiene readonly aunque se manipule RPC;
- secret content nunca aparece en `get_values`, RPC ni vista;
- admin-mutable round-trip válido;
- override inválido no pisa el valor previo;
- path/provider fuera de envelope se rechaza server-side;
- service URL SSRF/credentials/path/query/fragment rechazados según boundary existente;
- XML/views instalables y upgrade del addon;
- suite, Ruff y mypy.

## Acceptance criteria

- existe Settings Odoo-native para el piloto;
- sólo se pueden editar settings clasificados como `ADMIN_MUTABLE`;
- provenance/estado efectivo es comprensible para un técnico;
- no se ha trasladado ningún secreto o privilegio host a Odoo.

## Después

1. Lista todos los campos expuestos y su descriptor M7-01 asociado.
2. Documenta qué sigue requiriendo setup/bootstrap.
3. No avances a M7-03 si la UI puede persistir algo que el runtime no valida de nuevo.

## Estado de implementación

**Implemented / runtime verified.**
