# M1-10 — Gate de M1

## Contexto

- Ejecutar sólo después de M1-01..M1-09.
- Esta task no añade features. Verifica el milestone contra el Source of Truth y decide PASS/FAIL.

## Objetivo

Demostrar con evidencia ejecutable que el runtime/install de M1 cumple sus acceptance criteria antes de permitir M2.

## No debes implementar

- nuevas features para maquillar una gate fallida;
- ScreenContext/delegación/ORM tools;
- scanner/source/log providers;
- Codex/agent loop/RAG;
- writes/actions.

Si una comprobación falla, corrige sólo el defecto dentro del scope M1 o marca FAIL y explica qué task debe reabrirse.

## Verificaciones obligatorias

### 1. Calidad y boundaries

- suite completa de tests;
- lint;
- type-check;
- contracts siguen libres de FastAPI/Odoo/Codex/storage;
- application no depende de adapters concretos/version checks Odoo.

### 2. Runtime HTTP

- service arranca mediante systemd como usuario no-root;
- escucha sólo en loopback;
- `/health` responde correctamente;
- `/v1/admin/status` devuelve estado estructurado y sanitizado.

### 3. PostgreSQL

- Assistant DB existe separada de Odoo DB;
- migraciones están en `head`;
- Assistant role conecta a Assistant DB;
- conexión real del Assistant role a Odoo DB falla;
- Odoo conserva su acceso normal.

### 4. Bootstrap

En host disposable o entorno suficientemente equivalente:

- primera ejecución crea/actualiza runtime, config, secret, DB, migrations y systemd;
- segunda ejecución es idempotente;
- secretos no aparecen en repo/logs/output sensible;
- no queda root permanente para Odoo/Assistant Service.

### 5. Odoo

- addon placeholder instala/actualiza en Odoo 18 Community;
- health/status del service es visible server-side desde Odoo;
- con service detenido se muestra error controlado;
- browser no habla directamente con Assistant Service;
- no existen todavía features de M2.

### 6. Upgrade/rollback

- runbook existente y coherente;
- migraciones operativas forward-only;
- backup/restore o estrategia compatible está documentada cuando un rollback de schema lo requiera;
- uninstall del addon no purga Assistant DB automáticamente.

## Acceptance criteria final

Sólo marcar **PASS** si se demuestra:

1. fresh Ubuntu/Linux host de test → un bootstrap → service healthy;
2. segunda ejecución idempotente;
3. Assistant role NO puede `CONNECT` a la DB Odoo;
4. installer crea/actualiza runtime y Assistant DB;
5. health es visible desde Odoo;
6. rollback está documentado;
7. tests/lint/type-check verdes.

Si WSL no permite verificar de forma equivalente systemd/fresh-host/bootstrap, el resultado debe ser **CONDITIONAL/FAIL**, nunca PASS por inferencia. Indica exactamente qué prueba falta y cómo ejecutarla en una VM/host Ubuntu limpio.

## Resultado requerido de Codex

Al terminar, entrega una tabla:

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| tests | PASS/FAIL | ... |
| lint | PASS/FAIL | ... |
| type-check | PASS/FAIL | ... |
| health | PASS/FAIL | ... |
| admin status | PASS/FAIL | ... |
| systemd/non-root/loopback | PASS/FAIL | ... |
| Assistant DB migrations | PASS/FAIL | ... |
| Assistant role → Odoo DB denied | PASS/FAIL | ... |
| bootstrap first run | PASS/FAIL | ... |
| bootstrap second run | PASS/FAIL | ... |
| Odoo health visibility | PASS/FAIL | ... |
| upgrade/rollback | PASS/FAIL | ... |

Finaliza con `M1 GATE: PASS`, `M1 GATE: FAIL` o `M1 GATE: CONDITIONAL` y la razón concreta.

No avances a M2.
