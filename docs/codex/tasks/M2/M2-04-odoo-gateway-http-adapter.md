# M2-04 — Adapter HTTP del OdooGateway

## Contexto

- Requiere M2-03 verde.
- `service/src/odoo_ai/ports/odoo.py` es la frontera estable; esta task crea un adapter concreto fuera de `application`/`contracts`.
- El adapter debe transportar la delegación sin exponerla al ReasoningEngine.

## Objetivo

Implementar en el Assistant Service un adapter HTTP estrecho que satisfaga `OdooGateway` usando exclusivamente los endpoints read/metadata de M2-03, con configuración server-side, límites y errores sanitizados.

## Contratos que NO puedes romper

- firmas públicas de `OdooGateway` salvo cambio mínimo realmente necesario y justificado;
- `contracts`/`application` libres de FastAPI/Odoo transport concreto;
- delegación como credencial interna del turn;
- política de deployment: URLs/config no hardcodeadas.

## Debes reutilizar

- shared-secret loader de M1;
- contracts `RecordRef`, `RecordSnapshot`, `Evidence`;
- config/runtime pattern ya usado por Assistant Service;
- HTTP stdlib o cliente ya presente; no añadir una dependencia grande sin motivo.

## Debes implementar

### 1. Adapter ligado a un turn

La instancia concreta del gateway debe quedar ligada al contexto de autorización del turn: delegación opaca, `turn_id` y configuración del endpoint Odoo. El port no debe necesitar conocer headers/tokens.

Si mantener las firmas actuales requiere una factory por-turn, crea una factory simple. No metas auth kwargs en cada tool call si puede resolverse al construir el adapter.

### 2. Configuración del endpoint Odoo

Resolver la base URL desde configuración server-side autenticada, siguiendo el Source of Truth y `docs/DEPLOYMENT_CONFIG.md`.

- nunca desde JS;
- nunca desde texto del usuario/modelo;
- no asumir `127.0.0.1:8069` como contrato;
- permitir override explícito;
- validar scheme/host/port y rechazar credentials/fragments;
- no seguir redirects automáticamente;
- si el Source of Truth permite que Odoo envíe la URL interna dentro del request autenticado, tratarla como dato server-side y validarla igualmente.

### 3. Operaciones estrechas

Implementar únicamente:

- `get_model_metadata(model)` → llamada al handler metadata M2-03 y mapping a `Evidence`;
- `read_records(records, fields)` → llamada al handler read M2-03 y mapping a `RecordSnapshot`.

No implementar method execution, domains, search genérico ni endpoints dinámicos.

### 4. Robustez

- timeouts cortos y explícitos;
- request/response size caps;
- JSON shape estricto;
- mapping de 401/403/404/429/5xx a errores internos sanitizados;
- no loggear token, secret, headers de auth ni payload completo de records;
- cerrar conexiones correctamente;
- no retries automáticos que amplifiquen un token expirado o una lectura denegada.

## Fuera de scope

- turn orchestration;
- ToolExecutor;
- ReasoningEngine;
- UI;
- queries arbitrarias;
- source/logs/writes.

## Restricciones

- adapter bajo `adapters/`/`infrastructure` o ubicación equivalente, nunca en `contracts`;
- no `execute_kw`;
- no XML-RPC genérico como shortcut;
- no SQL Odoo;
- no URL derivada de prompt.

## Tests obligatorios

- fake HTTP server devuelve metadata válida → `Evidence` correcto;
- read válido → `RecordSnapshot` correcto;
- auth/delegation headers se envían server-side pero no aparecen en error/repr;
- redirect → rechazo;
- timeout → error sanitizado;
- body oversized/malformed → rechazo;
- URL no-default válida → funciona;
- URL con credentials/fragment o inválida → rechazo;
- adapter no expone método genérico;
- contract/boundary tests, Ruff, mypy.

## Acceptance criteria

- existe un adapter concreto sustituible que cumple `OdooGateway`;
- el port sigue technology-neutral;
- delegación permanece fuera de prompts/model output;
- configuración no depende del layout DEV;
- sólo se pueden invocar los dos handlers permitidos;
- tests verdes.

## Antes de editar

1. Inspecciona el port actual y decide si basta una factory per-turn.
2. Resume de dónde saldrá la Odoo gateway URL en el deployment actual y cuál es el override.
3. Lista cualquier cambio de contrato antes de hacerlo.

## Después

1. Ejecuta tests/lint/type-check.
2. Informa config keys/env vars introducidas y por qué.
3. Demuestra un endpoint no-default y un redirect rechazado.
4. No avances a M2-05.
