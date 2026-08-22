# M3-10 — Gate integral y cierre de M3

## Contexto

- Requiere M3-01…M3-09 completadas.
- Esta task no añade features.
- El objetivo es decidir PASS/FAIL contra Source of Truth, no declarar éxito ignorando gaps.

## Objetivo

Ejecutar la gate completa de M3, revisar seguridad/boundaries/deployment y cerrar el milestone sólo si todo está comprobado.

## Contratos que NO puedes romper

- Source of Truth;
- `AGENTS.md` aplicables;
- M1 GATE;
- M2 GATE;
- no adelantar M4.

## Debes implementar

Sólo si las verificaciones pasan:
- `docs/M3_GATE_REPORT.md`;
- actualizar estado en `README.md`;
- actualizar `docs/codex/MILESTONES.md`;
- actualizar `docs/codex/tasks/M3/README.md` a estado completado;
- corregir drift documental menor;
- dejar M4 como siguiente milestone, no iniciado.

No añadir features para ocultar un FAIL. Si aparece un defecto inequívocamente de scope M3, corrígelo y vuelve a ejecutar la gate. Si implica nueva arquitectura/invariante, reporta el conflicto y detente.

## Matriz de gate obligatoria

### Calidad

- pytest completo;
- ruff;
- mypy;
- addon tests Odoo 18;
- migrations fresh + upgrade;
- harness reproducible.

### Source

- roots resolved/configurable;
- layout no convencional;
- no host-wide scan;
- manifest literal;
- dynamic manifest no ejecutado;
- Python AST;
- XML;
- CSV security;
- `action_confirm` exact lines;
- `find_model_extensions`;
- excerpt bounded;
- rescan incremental;
- deletion/staleness;
- provenance conservadora.

### Logs

- File provider real fixture;
- Journal provider contract/integration cuando disponible;
- terms/time window;
- max lines/bytes;
- traceback parse;
- fingerprint/grouping;
- secret redaction;
- no full ingest.

### Seguridad

- no `sudo()` en caminos normales source/log;
- no SQL a Odoo;
- no `execute_kw`/`execute_method`;
- no shell libre;
- Journal usa argv fijo, no `shell=True`;
- arbitrary source path reject;
- arbitrary log path/unit reject;
- symlink/path escape reject;
- browser no recibe secrets/tokens;
- source/log evidence bounded.

### Deployment

- conventional layout;
- non-default addons root;
- non-default log file;
- configurable journal unit;
- missing/no-permission states;
- source/log settings no exigen editar Python.

### E2E observable

Desde Diagnostics:
- scan válido;
- `action_confirm` encontrado;
- líneas correctas;
- excerpt correcto;
- traceback encontrado por ventana/terms;
- fingerprint visible/sanitizado;
- cambiar source + rescan invalida stale result.

### Regresiones

- M1 profiles verdes;
- M2 Odoo/browser E2E verde;
- context-read sigue ejecutándose como usuario real.

## Estado esperado después de M3

- `source`: OK;
- `logs`: OK;
- Assistant DB/migrations: OK;
- M2 contextual read: OK;
- `reasoning_engine`: todavía pendiente;
- readiness global: `DEGRADED`, no `FULLY_READY`.

## Acceptance criteria

M3 sólo es PASS si:
- scanner encuentra método fixture y líneas exactas;
- re-scan invalida hash/source stale;
- logs encuentran traceback en ventana acotada;
- redaction/caps funcionan;
- no hay bypass de roots/provider;
- Diagnostics demuestra ambas capacidades;
- suites M1/M2 no retroceden;
- no se ha implementado Codex/RAG/writes;
- no existe conflicto abierto con el Source of Truth.

## Antes de editar

1. Resume el estado real M3.
2. Enumera checks que aún no estén comprobados.
3. Si falta una verificación esencial, no declares gate PASS.

## Después

1. Publica comandos/resultados exactos en `docs/M3_GATE_REPORT.md`.
2. Informa archivos cambiados sólo por cierre/documentación o fixes estrictamente M3.
3. Marca M3 PASS o FAIL de forma explícita.
4. Si PASS, deja como siguiente packet el primero de M4, pero no lo ejecutes.
