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

## Fixtures de deployment

Cuando una task toque installer, source, logs, filesystem, supervisor o PostgreSQL:

- no usar un único fixture que replique el host DEV;
- mantener al menos un caso convencional y otro con rutas/nombres no-default;
- probar overrides explícitos y ambigüedad cuando corresponda;
- incluir Odoo con unit arbitrario o sin systemd cuando esa capa sea relevante;
- comprobar que cambiar paths/puertos/nombre de DB no requiere modificar código;
- distinguir restricciones deliberadas del perfil (por ejemplo bind loopback) de assumptions accidentales.

No crear suites fuera del scope autorizado por el task packet activo.
