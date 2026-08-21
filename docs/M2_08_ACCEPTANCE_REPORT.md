# M2-08 — Aceptación E2E desde `sale.order`

Fecha de ejecución: 2026-08-22. Resultado: **PASS**.

## Topología desechable validada

```text
Chromium → Odoo 18 Community HTTP → Assistant Service HTTP
                                  → Odoo HTTP interno → ORM como usuario real
```

Odoo y el Assistant Service se ejecutaron como procesos HTTP separados en
loopback. El service usó su base PostgreSQL propia, migrada a
`0002_m1_03_runtime_tables`, y el addon sólo recibió URLs y rutas de secretos
mediante configuración server-side.

El fixture idempotente creó:

- partner `M2 E2E Customer`;
- comercial interno no administrador `m2-e2e-sales-user`;
- presupuesto visible `S00001`, asignado a ese comercial;
- segundo comercial y presupuesto `S00002`, oculto al primero por la record
  rule estándar de pedidos propios.

El fixture y el navegador reproducibles están en
`tests/e2e/m2_sale_order_fixture.py` y
`tests/e2e/m2_sale_order_browser.mjs`. IDs, DB, URLs, credenciales desechables y
paths se suministran por variables; no hay layout DEV codificado y `sale` no es
dependencia del manifest del addon.

## Evidencia observable

| Comprobación | Resultado | Evidencia |
|---|---:|---|
| Login no-admin y form real | PASS | Chromium abrió el formulario de `S00001` como el usuario comercial. |
| Assets/panel Odoo real | PASS | El panel mostró `sale.order #1` capturado por el web client. |
| Flujo positivo completo | PASS | La UI mostró `S00001`, `state=draft` y el mensaje de relectura ORM. |
| Datos no confiados desde JS | PASS | El request browser contenía sólo pregunta y `ScreenContext`, sin identidad ni `display_name`. |
| Caso negativo manipulado | PASS | Cambiar `res_id` a `S00002` terminó en `access_denied` y no devolvió su nombre. |
| Browser aislado del service | PASS | Único origen observado: Odoo; cero requests del browser al origen del Assistant Service. |
| Secretos/token fuera del browser | PASS | Requests y responses del bridge no contenían token, headers internos ni secretos exactos de prueba. |
| Service health/status | PASS | `/health`: `ok`; status autenticado: `DEGRADED` esperado, DB disponible y migraciones `at_head`. |
| Trazas sanitizadas | PASS | 66 eventos inspeccionados; cero coincidencias de token o secretos de prueba. |
| Addon install/upgrade | PASS | Upgrade real de versión `18.0.2.8.0`; 28 tests del addon sin fallos. |

Salida resumida del harness final:

```json
{"browser_origins":["http://127.0.0.1:18078"],"browser_to_assistant_requests":0,"negative_error":"access_denied","positive_display_name":"S00001","positive_status":"ok"}
```

## Ejecución reproducible

1. Instalar `sale,odoo_ai_assistant` en una base Odoo 18 desechable.
2. Ejecutar el fixture con un shell Odoo:

   ```text
   M2_E2E_LOGIN=... M2_E2E_PASSWORD=... odoo-bin shell -d <db> \
     < tests/e2e/m2_sale_order_fixture.py
   ```

3. Migrar y arrancar el Assistant Service con las variables M1 normales;
   arrancar Odoo con `ODOO_AI_SERVICE_URL`, `ODOO_AI_SHARED_SECRET_FILE` y
   `ODOO_AI_DELEGATION_SECRET_FILE`.
4. Instalar Playwright en un entorno Node desechable y ejecutar el harness con
   las variables documentadas en `tests/e2e/README.md`.

No se introdujo ReasoningEngine, Codex, escritura de negocio ni dependencia
arquitectónica de `sale`. M2-09 no forma parte de esta ejecución.
