# M7-04 — Diagnostics estructurado y remediación

## Contexto

- Requiere Goal A verde.
- Diagnostics actual ya comprueba health/readiness/source/logs/reasoning/workflows, pero gran parte de la superficie son strings y mensajes ad hoc.
- M7 debe convertirlo en una herramienta operativa, no sólo un dump de estado.

## Objetivo

Evolucionar Diagnostics a una capability matrix estructurada que indique para cada componente/workflow: estado, causa estable, provenance relevante, última comprobación y remediación segura/accionable.

## Debes implementar

### Diagnostic contract

Definir un resultado versionado/bounded con campos equivalentes a:

- component/capability key estable;
- state/severity;
- reason code estable;
- summary admin-safe;
- `checked_at`/freshness;
- config revision/provenance relevante;
- remediation kind (`settings`, `setup_required`, `retry`, `rescan`, `reindex`, `authenticate_runtime`, `none` o equivalente);
- remediation text bounded;
- diagnostic/evidence ref cuando exista una prueba concreta.

No devolver exception text/raw traceback ni comandos shell construidos desde datos no confiables.

### Cobertura

Como mínimo cubrir:

- Assistant endpoint/machine auth;
- Assistant DB/migrations;
- instance/deployment profile;
- source + último scan;
- logs/provider;
- knowledge/index;
- reasoning/Codex;
- EXPLAIN, QUERY, HOW_TO y ACTION;
- M6 action authority/approval readiness;
- config revision/effective validity M7.

### Odoo UI

Actualizar Diagnostics para renderizar la matriz de forma legible, agrupar errores/warnings y dirigir a Settings o a una acción administrativa permitida cuando proceda.

Los mensajes deben ser suficientemente específicos para que un técnico sepa qué revisar sin exponer secretos.

## Debes reutilizar

- `/v1/admin/status` y status runtime actuales;
- Diagnostics existente;
- config snapshot M7-01..03;
- source/log tests existentes.

## Fuera de scope

- operaciones de mantenimiento nuevas (M7-05);
- ejecutar fixes automáticamente;
- root/systemd commands;
- mostrar raw logs/tracebacks ilimitados;
- M8.

## Restricciones

- admin-only;
- reason codes y states allowlisted;
- response caps;
- ninguna remediación puede ser texto controlado por LLM/documentos/logs;
- no revelar physical paths/secrets salvo información estrictamente necesaria y explícitamente admin-safe.

## Tests obligatorios

- healthy matrix completa;
- cada componente degradado produce code/state/remediation estable;
- config stale/invalid se distingue de provider unavailable;
- auth missing/rejected no revela secret;
- Codex missing/auth/runtime incompatible tiene remediación correcta;
- source/log/knowledge failures sanitizados;
- ACTION authority missing visible sin exponer path/secret;
- unknown backend code no se renderiza como trusted message;
- non-admin denied;
- view install/update;
- suite, Ruff y mypy.

## Acceptance criteria

- un técnico puede localizar el componente roto sin leer consola;
- estado y causa están estructurados, no inferidos de strings;
- remediación dirige a Settings/setup/maintenance sin auto-ejecutar privilegios;
- FULLY_READY no oculta una capability obligatoria rota.

## Después

1. Documenta reason codes/remediation kinds.
2. Señala cualquier capability que aún no pueda diagnosticarse sin consola y por qué.
3. No avances a M7-05 si Diagnostics depende de mensajes libres del backend.
