# M4 Codex App Server protocol baseline

Fecha de verificación: 2026-08-22.

## Runtime inspeccionado

- Runtime inspeccionado en Codex para Windows: `codex-cli
  0.149.0-alpha.4.1`.
- Smoke real reproducible en Linux: `@openai/codex 0.149.0`, instalado
  temporalmente fuera del repositorio; el probe devolvió
  `compatible/app-server-jsonl-v2/0.149.0`.
- Transporte elegido para el producto Linux: `codex app-server --stdio
  --strict-config`.
- El comando `codex app-server generate-json-schema --experimental` confirmó
  el protocolo JSONL actual y sus schemas v2.
- Secuencia mínima probada: request `initialize`, response con el mismo `id` y
  notification `initialized`.
- La versión inspeccionada también declara `thread/start`, `turn/start`,
  `outputSchema`, threads `ephemeral`, `approvalPolicy`, `sandbox`,
  `runtimeWorkspaceRoots` y `dynamicTools`.

La documentación pública oficial de Codex y el runtime instalado no exponen un
SDK Python que controle este lifecycle manteniendo App Server como boundary.
Por ello M4-01 usa un cliente JSONL mínimo, sin vendorización del schema y sin
replicar el protocolo completo. Los nombres y shapes concretos quedan en
`odoo_ai.adapters.codex_runtime`; `application`, contracts y Odoo no dependen
de ellos.

## Configuración externa

- `ODOO_AI_CODEX_EXECUTABLE`: path absoluto al runtime seleccionado; no existe
  un path DEV como default de producto.
- `ODOO_AI_CODEX_HOME`: override explícito opcional. Si se omite, Codex resuelve
  su auth bajo el usuario efectivo del Assistant Service.
- `ODOO_AI_CODEX_MODEL`: modelo opcional; ningún nombre de modelo es contrato.
- `ODOO_AI_CODEX_ISOLATED_CWD`: cwd aislado opcional. Si se omite se crea uno
  temporal por proceso.
- `ODOO_AI_CODEX_STARTUP_TIMEOUT_SECONDS` y
  `ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS`: límites externos validados.

El child recibe un allowlist mínimo de variables de proceso, no el DSN,
shared secret, delegation secret ni configuración Odoo. El adapter nunca copia
ni parsea `auth.json`.

## Lifecycle y aislamiento preparados

```text
spawn argv fijo, shell=False
    -> initialize (id correlacionado)
    -> validate bounded response
    -> initialized
    -> future ephemeral thread: approval=never, sandbox=read-only,
       runtimeWorkspaceRoots=[], environments=[], dynamicTools=[]
    -> close stdin
    -> graceful wait
    -> TERM/KILL bounded fallback
```

El probe sólo declara compatibilidad de protocolo. Auth y modelo permanecen
`unknown` hasta que una task posterior obtenga evidencia real de un turn.

El smoke se puede repetir pasando el path absoluto del binario a
`ODOO_AI_CODEX_EXECUTABLE`, activando `ODOO_AI_RUN_CODEX_RUNTIME_SMOKE=1` y
ejecutando `tests/integration/test_codex_runtime_smoke.py`. No necesita login ni
consume un product turn.
