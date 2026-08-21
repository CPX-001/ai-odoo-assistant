# Reglas de tests

## Flujo Git

- Trabajar siempre directamente sobre `main`; no crear ramas ni pull requests salvo orden explícita del usuario.

Priorizar:

- unit tests;
- contract tests;
- integración con Odoo 18;
- E2E del vertical slice;
- tests explícitos de seguridad.

Dar especial importancia futura a record rules, restricted fields, multi-company, expiración/replay de delegación, approvals, aislamiento de Codex y prompt injection.

No crear fixtures ni suites hasta que un task packet posterior lo autorice.
