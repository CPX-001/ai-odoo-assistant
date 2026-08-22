# M4-07 — Reasoning capability, Diagnostics y `FULLY_READY`

## Contexto

- Requiere M4-06 verde.
- Tras M3, `source` y `logs` pueden estar `OK`, pero `AdminStatus` sólo admite `DEGRADED|ERROR` y mantiene `reasoning_engine` pendiente.
- M4 debe hacer observable Codex sin filtrar auth, `CODEX_HOME` ni paths de runtime.

## Objetivo

Integrar el estado del ReasoningEngine en capability/readiness y Diagnostics, de forma que una instancia con DB+migrations+source+logs+reasoning operativos pueda reportar `FULLY_READY`, y una instalación sin Codex siga degradada de forma accionable.

## Debes implementar

### Runtime status

Evolucionar los contratos internos de status para incluir:

- component `reasoning_engine`;
- estado `ok|pending|error`;
- detail sanitizado (`operational`, `not_configured`, `runtime_missing`, `auth_unavailable`, `protocol_incompatible`, `error`, etc.);
- `readiness` compatible con `FULLY_READY | DEGRADED | ERROR` según Source of Truth.

Reglas mínimas:

- DB/migrations rotas → `ERROR`;
- capability opcional/pendiente (source/logs/reasoning) → `DEGRADED`;
- todas las capabilities obligatorias operativas → `FULLY_READY`;
- no declarar `FULLY_READY` sólo porque existe el ejecutable Codex.

### Probe/caching

Reutilizar el probe M4-01. No lanzar un model turn costoso por cada `/v1/admin/status`.

Es válido:

- cachear un handshake/probe reciente con TTL pequeño;
- actualizar estado después de un turn real exitoso/fallido;
- persistir capability snapshot sanitizado.

No persistir tokens, auth file path, prompt ni stderr crudo.

### Capability snapshot

Extender la persistencia existente sólo lo necesario para representar reasoning state/provider/version/model cuando sea seguro. Mantén el schema compatible y una migración forward-only si realmente hace falta.

No conviertas `capabilities` JSON en un saco de telemetry arbitrario.

### Odoo Diagnostics

Mostrar a administradores:

- Reasoning Engine state;
- provider `codex`;
- protocol/runtime version si se conoce;
- modelo configurado/detectado si es seguro;
- mensaje de setup accionable cuando falta auth/runtime.

No mostrar:

- `CODEX_HOME` path;
- auth account/token;
- API key;
- stdout/stderr raw;
- developer instructions.

### Deployment

Cualquier selector de runtime/model/home debe proceder de configuración externa/Settings/installer boundary según corresponda. No hardcodear ubicación de `codex`, usuario home ni modelo.

## Fuera de scope

- login OAuth embebido en Odoo;
- selector multi-provider;
- billing/token dashboard;
- auto-update de Codex;
- M5 features.

## Tests obligatorios

- reasoning missing → DEGRADED, no ERROR global si el resto funciona;
- protocol incompatible/auth unavailable → DEGRADED + detail correcto;
- DB/migrations error sigue ERROR;
- source/log/reasoning all OK → FULLY_READY;
- status no ejecuta model turn por request;
- capability snapshot no contiene secrets/paths;
- Odoo Diagnostics sólo admin y payload sanitizado;
- bootstrap/layout no-default no regresa;
- suite, Ruff, mypy, tests Odoo.

## Acceptance criteria

- `reasoning_engine` es una capability observable real;
- `FULLY_READY` sólo aparece cuando se han demostrado las capabilities obligatorias;
- faltar Codex degrada de forma controlada;
- Diagnostics ayuda a configurar sin revelar credenciales.

## Después

1. Documenta tabla exacta de readiness.
2. Muestra status healthy/degraded sin información sensible.
3. No avances a M4-08.
