# M4 reasoning readiness and Diagnostics

Fecha de verificación: 2026-08-22.

## Tabla exacta de readiness

| Assistant DB | Migrations | Source | Logs | Reasoning | Readiness |
|---|---|---|---|---|---|
| error | cualquiera | cualquiera | cualquiera | cualquiera | `ERROR` |
| ok | error | cualquiera | cualquiera | cualquiera | `ERROR` |
| ok | ok | ok | ok | ok | `FULLY_READY` |
| ok | ok | cualquier otro estado | cualquiera | cualquiera | `DEGRADED` |
| ok | ok | cualquiera | cualquier otro estado | cualquiera | `DEGRADED` |
| ok | ok | cualquiera | cualquiera | pending/error | `DEGRADED` |

Un error de DB o una revisión de migraciones distinta al head impide iniciar turns
de forma fiable y domina el resultado global. Source, logs y reasoning son
capabilities obligatorias del perfil `FULLY_READY`, pero su ausencia deja el
servicio observable en `DEGRADED` en vez de ocultar el estado de las otras
capabilities.

## Probe de Codex

`CachedCodexReasoningStatus` reutiliza el lifecycle acotado de M4-01 y ejecuta:

```text
initialize -> initialized -> account/read(refreshToken=false) -> close bounded
```

No inicia `thread/start`, `turn/start` ni un model turn. El resultado se cachea
30 segundos por proceso de API; el TTL puede configurarse con
`ODOO_AI_CODEX_READINESS_TTL_SECONDS` entre 0.1 y 300 segundos.

| Evidencia del probe | Component state | Detail público |
|---|---|---|
| runtime sin seleccionar | pending | `not_configured` |
| ejecutable ausente/no ejecutable | pending | `runtime_missing` |
| initialize/protocolo inválido | pending | `protocol_incompatible` |
| handshake válido, cuenta requerida ausente | pending | `auth_unavailable` |
| handshake válido y cuenta disponible o auth no requerida | ok | `operational` |
| otro fallo sanitizado | pending | `error` |

La mera existencia del ejecutable nunca produce `operational`.

## Snapshot y payload público

El JSONB existente de `capability_snapshot` conserva únicamente estado,
provider `codex`, protocolo, versión y modelo configurado cuando son strings
acotados sin paths. No fue necesaria una migración. La readiness persistida se
recalcula al actualizar source, logs o reasoning.

`/v1/admin/status` aplica una allowlist al JSON público. No expone roots,
`CODEX_HOME`, auth account, tokens, DSN, prompts, stdout/stderr ni configuración
cruda. Odoo Diagnostics muestra estado, provider, protocolo, versión, modelo y
un mensaje de setup accionable para administradores de sistema.

Ejemplos sanitizados del componente y la readiness resultante:

```json
{
  "readiness": "FULLY_READY",
  "components": {
    "reasoning_engine": {
      "state": "ok",
      "detail": "operational",
      "provider": "codex",
      "protocol": "app-server-jsonl-v2",
      "runtime_version": "0.149.0",
      "model": "gpt-5.6-sol"
    }
  }
}
```

```json
{
  "readiness": "DEGRADED",
  "components": {
    "reasoning_engine": {
      "state": "pending",
      "detail": "auth_unavailable",
      "provider": "codex",
      "protocol": "app-server-jsonl-v2",
      "runtime_version": "0.149.0",
      "model": null
    }
  },
  "pending_capabilities": ["reasoning_engine"]
}
```
