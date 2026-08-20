# M1 — Runtime / install

M1 empieza sólo después de que `M0-06-gate.md` haya dado PASS. Su objetivo es convertir el esqueleto del Assistant Service en un runtime local instalable y observable, sin implementar todavía lectura contextual Odoo, scanner/source, logs, Codex ni agent loop.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, especialmente §§8, 9, 23, 28, 29, 30 y 34.4.

Resultado observable del milestone: un host Ubuntu/Linux de test puede ejecutar un único bootstrap, crear/actualizar el runtime y la DB propia del Assistant, arrancar el service y mostrar su health desde Odoo. Una segunda ejecución es idempotente y el role del Assistant no puede conectar a la DB Odoo.

## Orden de ejecución

1. [`M1-01-fastapi-runtime-health.md`](M1-01-fastapi-runtime-health.md) — runtime FastAPI mínimo y `/health`.
2. [`M1-02-postgres-storage-migrations.md`](M1-02-postgres-storage-migrations.md) — SQLAlchemy, Alembic y conexión exclusiva a la DB Assistant.
3. [`M1-03-runtime-persistence.md`](M1-03-runtime-persistence.md) — `instance_profile`, `capability_snapshot`, `trace_event`.
4. [`M1-04-admin-status-readiness.md`](M1-04-admin-status-readiness.md) — `/v1/admin/status` y readiness estructurado.
5. [`M1-05-bootstrap-foundation.md`](M1-05-bootstrap-foundation.md) — descubrimiento del host, usuario/directorios/config y secreto compartido.
6. [`M1-06-bootstrap-postgres-isolation.md`](M1-06-bootstrap-postgres-isolation.md) — DB/role del Assistant, migraciones e aislamiento respecto a Odoo.
7. [`M1-07-systemd-runtime.md`](M1-07-systemd-runtime.md) — unit systemd, loopback, lifecycle e idempotencia.
8. [`M1-08-odoo-placeholder-health.md`](M1-08-odoo-placeholder-health.md) — addon placeholder mínimo y health visible desde Odoo.
9. [`M1-09-upgrade-rollback-install-tests.md`](M1-09-upgrade-rollback-install-tests.md) — upgrade/rollback documentado y pruebas de instalación repetible.
10. [`M1-10-gate.md`](M1-10-gate.md) — verificación integral y cierre de M1.

Ejecutar una sola task cada vez. Cada task debe partir del estado real dejado por la anterior, ejecutar sus verificaciones y detenerse. No avanzar automáticamente a la siguiente.

## Invariantes de M1

- Assistant DB PostgreSQL separada de la DB Odoo.
- El Assistant Service no recibe credenciales SQL que le permitan acceder a datos vivos de Odoo.
- `odoo_ai_service`: `CONNECT odoo_ai = YES`; `CONNECT <odoo_database> = NO`.
- Runtime local en loopback para el MVP.
- Un único bootstrap privilegiado; Odoo no obtiene root permanente.
- Secretos fuera del repo, prompts y logs.
- El addon de M1 es sólo el mínimo necesario para detectar/configurar health; M2 implementará contexto, delegación y ORM tools.
- No scanner, LogProvider real, Codex, agent loop, RAG ni writes.

## Gate de M1

M1 sólo se considera terminado cuando:

- fresh Ubuntu/Linux host de test → un bootstrap → service healthy;
- segunda ejecución del bootstrap no rompe ni duplica recursos;
- migraciones están al día;
- health/readiness es visible desde Odoo;
- el role del Assistant no puede `CONNECT` a la DB Odoo;
- el runtime escucha sólo en la interfaz prevista;
- upgrade y rollback operativo están documentados;
- tests, lint y type-check siguen verdes.

WSL puede servir como entorno DEV si soporta correctamente PostgreSQL y systemd. Si alguna comprobación de instalación no equivale a un host Ubuntu/Linux soportado, M1 no debe declararse PASS hasta repetir la gate en un host apropiado.
