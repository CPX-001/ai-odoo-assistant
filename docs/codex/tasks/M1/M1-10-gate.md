# M1-10 — Gate de M1

## Contexto

- Ejecutar sólo después de M1-01..M1-09.
- Esta task no añade features. Verifica el milestone contra el Source of Truth y decide PASS/FAIL.
- `docs/DEPLOYMENT_CONFIG.md` forma parte de las reglas operativas que deben verificarse.

## Objetivo

Demostrar con evidencia ejecutable que el runtime/install de M1 cumple sus acceptance criteria antes de permitir M2, incluyendo que el producto no dependa accidentalmente del layout del entorno DEV.

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
- application no depende de adapters concretos/version checks Odoo;
- no hay paths/nombres del entorno DEV usados como contratos fuera de hints/defaults claramente sustituibles.

### 2. Runtime HTTP

- service arranca mediante systemd como usuario no-root en el perfil soportado;
- escucha sólo en loopback;
- puerto/config runtime procede de settings centralizados;
- `/health` responde correctamente;
- `/v1/admin/status` devuelve estado estructurado y sanitizado.

### 3. PostgreSQL

- Assistant DB existe separada de Odoo DB;
- migraciones están en `head`;
- Assistant role conecta a Assistant DB;
- en escenario same-cluster, conexión real del Assistant role a Odoo DB falla;
- Odoo conserva su acceso normal;
- host/puerto/nombre/DSN del Assistant son configurables y no dependen de `localhost` como contrato.

### 4. Bootstrap

En host disposable o entorno suficientemente equivalente:

- primera ejecución crea/actualiza runtime, config, secret, DB, migrations y systemd;
- segunda ejecución es idempotente;
- secretos no aparecen en repo/logs/output sensible;
- no queda root permanente para Odoo/Assistant Service;
- `odoo.conf`, service unit, usuario, addons/data/log paths y directorios propios se tratan como facts/configuración, no constantes.

### 5. Portabilidad del layout

Ejecutar una matriz mínima de dos casos:

**A. Convencional**

- config/service/paths típicos del entorno de test.

**B. No convencional**

Usar varias diferencias reales, por ejemplo:

- config en `/srv/...` o sin config autodetectable;
- unit explícito `acme-erp.service` o Odoo sin systemd con `--odoo-user`;
- addons/data/log paths personalizados;
- path con espacios cuando sea válido;
- directorios/puerto/nombre de Assistant DB no-default.

El caso B debe superar preflight/bootstrap usando configuración/overrides, **sin editar Python, XML ni templates** para adaptarlo.

No hace falta cubrir Docker/Odoo.sh/supervisores alternativos completos en M1; sí demostrar que añadirlos después no exige romper application contracts.

### 6. Odoo

- addon placeholder instala/actualiza en Odoo 18 Community;
- health/status del service es visible server-side desde Odoo;
- con service detenido se muestra error controlado;
- browser no habla directamente con Assistant Service;
- Settings/diagnóstico no inventa paths desconocidos ni duplica endpoints como constantes de frontend;
- no existen todavía features de M2.

### 7. Upgrade/rollback

- runbook existente y coherente;
- migraciones operativas forward-only;
- backup/restore o estrategia compatible está documentada cuando un rollback de schema lo requiera;
- uninstall del addon no purga Assistant DB automáticamente;
- upgrade/rollback conserva configuración no-default.

## Acceptance criteria final

Sólo marcar **PASS** si se demuestra:

1. fresh Ubuntu/Linux host de test → un bootstrap → service healthy;
2. segunda ejecución idempotente;
3. Assistant role NO puede acceder a la DB Odoo en el escenario same-cluster;
4. installer crea/actualiza runtime y Assistant DB;
5. health es visible desde Odoo;
6. rollback está documentado;
7. layout no convencional funciona mediante configuración/overrides sin cambios de código;
8. tests/lint/type-check verdes.

Si el entorno actual no permite verificar de forma equivalente systemd/fresh-host/bootstrap, el resultado debe ser **CONDITIONAL/FAIL**, nunca PASS por inferencia. Indica exactamente qué prueba falta y cómo ejecutarla en una VM/host limpio.

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
| conventional deployment | PASS/FAIL | ... |
| non-conventional deployment | PASS/FAIL | ... |
| Odoo health visibility | PASS/FAIL | ... |
| upgrade/rollback | PASS/FAIL | ... |

Finaliza con `M1 GATE: PASS`, `M1 GATE: FAIL` o `M1 GATE: CONDITIONAL` y la razón concreta.

No avances a M2.
