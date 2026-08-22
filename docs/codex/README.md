# Trabajo con Codex

Las sesiones de implementación deben seguir las instrucciones raíz y locales de `AGENTS.md`, avanzar mediante milestones pequeños y usar task packets con un único resultado observable.

- [`TASK_PACKET_TEMPLATE.md`](TASK_PACKET_TEMPLATE.md): plantilla operativa.
- [`MILESTONES.md`](MILESTONES.md): roadmap resumido.
- [`../DEPLOYMENT_CONFIG.md`](../DEPLOYMENT_CONFIG.md): reglas de autodetección, overrides y portabilidad del layout.
- [`tasks/M0/README.md`](tasks/M0/README.md): M0 completado y detalle de su gate.
- [`tasks/M1/README.md`](tasks/M1/README.md): M1 completado y gate PASS.
- [`tasks/M3/README.md`](tasks/M3/README.md): milestone activo; M3-01 a M3-06 implementados, con M3-07 como siguiente task packet.
- [`../../PLANS.md`](../../PLANS.md): cuándo y cómo mantener un ExecPlan.

Antes de implementar, contrastar siempre el task packet con el Source of Truth y los ADRs aplicables. Si la task toca filesystem, logs, source, servicios, installer o PostgreSQL, revisar también la política de deployment y distinguir explícitamente requisitos reales de defaults/hints del entorno DEV.

M3 es el milestone activo. Ejecutar una sola task cada vez y no avanzar automáticamente a la siguiente sin verificar sus acceptance criteria.
