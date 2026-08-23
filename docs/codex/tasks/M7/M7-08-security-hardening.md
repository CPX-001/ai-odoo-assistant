# M7-08 — Security hardening de superficies administrativas

## Contexto

- Requiere M7-01..M7-07 verdes.
- M7 añade Settings, admin config API, maintenance, observability y lifecycle metadata: son nuevas superficies privilegiadas y deben recibir un threat-model/gate propio.
- No basta con que `base.group_system` o readonly fields aparezcan en la UI; enforcement debe existir server-side.

## Objetivo

Ejecutar una revisión adversarial integral de las nuevas superficies M7 y corregir defects reales sin ampliar scope funcional, demostrando que un usuario, browser, documento, log o LLM no puede convertir product hardening en una vía de escalada.

## Threats/checks obligatorios

### Identity / authorization

- non-admin intentando Settings, diagnostics, maintenance, audit y config apply;
- actor/uid/company enviados por JS son ignorados o rechazados;
- cross-company/cross-database config o audit access;
- replay/double-submit de operaciones administrativas.

### Secrets

Canaries en:

- shared-secret files;
- ACTION authority secret;
- DSNs/env;
- Codex auth/profile metadata;
- config store;
- logs/error messages.

Confirmar ausencia en DOM, RPC, admin API, audit, diagnostic messages, maintenance results y prompts.

### Filesystem / provider boundaries

- `../`, symlink, absolute-path escape, encoded traversal;
- log unit/path/provider tampering;
- source/knowledge root outside setup-approved envelope;
- TOCTOU containment revalidation antes de usar path cuando aplique.

### SSRF / network

- `service_url` y cualquier endpoint mutable no pueden apuntar a arbitrary network/credentials/path/query/fragment;
- browser continúa sin Assistant direct access;
- no generic URL fetch introducido por Settings/maintenance.

### Injection / UI

- XSS/HTML en paths, provider names, diagnostic text, audit summaries y runtime metadata;
- prompt injection contenida en logs/docs/config labels no puede convertirse en maintenance/config instruction;
- reason/remediation text host-controlled.

### Abuse / DoS

- oversized config forms;
- maintenance spam/concurrent rebuilds;
- audit pagination abuse;
- repeated diagnostics/Codex tests;
- bounded inputs/outputs/timeouts/rate or concurrency limits donde sea necesario.

### Regression de ACTION/read-only workflows

- M7 config no puede añadir tools/risks a EXPLAIN/QUERY/HOW_TO;
- no puede habilitar arbitrary models/actions fuera de M6 policy;
- maintenance no puede approve/commit una proposal;
- audit/retention no puede mutar approvals/receipts vivos.

## Debes implementar

- tests adversariales reproducibles para los vectores anteriores;
- fixes mínimos necesarios;
- documentación breve del threat model M7 y residual risks aceptados;
- límites/rate/concurrency server-side sólo donde haya un vector real, sin inventar middleware universal.

## Fuera de scope

- pentest externo formal;
- WAF/network firewall management;
- RBAC empresarial complejo más allá del piloto salvo requirement del Source of Truth;
- cifrado custom de secretos que ya deben permanecer fuera de Odoo;
- M8.

## Restricciones

- no rebajar validadores existentes para facilitar UX;
- no confiar en frontend-only guards;
- no reemplazar failures cerrados por defaults silenciosos;
- no añadir `sudo()` para admin convenience;
- no revelar raw exception en mensajes de hardening.

## Tests obligatorios

Además de la suite adversarial M7:

- suite completa M1-M6;
- Ruff;
- mypy;
- migrations;
- addon install/update;
- browser tests;
- tests con layout no-default;
- canary scan de outputs/audit.

## Acceptance criteria

- las nuevas superficies M7 no permiten privilege escalation, arbitrary filesystem/network access ni secret exfiltration;
- admin actions son explicit/allowlisted/bounded;
- frontend tampering no modifica authority;
- M0-M6 mantienen sus invariantes y registries;
- riesgos residuales están documentados sin disfrazarlos como PASS.

## Después

1. Resume findings reales y fixes.
2. No declares esta task verde sólo por ausencia de findings; registra qué vectores se probaron.
3. No avances al gate si queda una escalada o leak reproducible.
