# M3 — Source + logs

Estado: en curso. M0, M1 y M2 están completados; **M2 GATE: PASS**. M3-01 a M3-03 están implementados y verificados; M3-04 es el siguiente task packet.

M3 convierte source y logs en evidencia determinista, acotada y consultable desde Diagnostics, sin introducir todavía Codex ni el agent loop. El objetivo observable del milestone es encontrar `sale.order.action_confirm` con módulo/fichero/líneas correctas y recuperar un traceback por ventana/términos desde Diagnostics.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT_CONFIG.md`, `AGENTS.md`, `service/AGENTS.md` y los `AGENTS.md` aplicables. Si un task packet entra en conflicto con el Source of Truth, se detiene y se corrige antes de implementar.

Resultado observable:

```text
Odoo Diagnostics
    ↓
Assistant Service
    ├── source scan válido
    │     └── sale.order.action_confirm → módulo + fichero + líneas + fingerprint
    └── LogProvider válido
          └── ventana + términos → traceback bounded + fingerprint
```

## Orden de ejecución

1. [`M3-01-donor-audit.md`](M3-01-donor-audit.md) — auditoría del scanner donor MIT antes de reutilizar código. Resultado: [`M3_ERPIPE_SCANNER_AUDIT.md`](../../../third_party/M3_ERPIPE_SCANNER_AUDIT.md).
2. [`M3-02-source-contracts-storage.md`](M3-02-source-contracts-storage.md) — contracts y persistencia mínima de scans/source.
3. [`M3-03-source-roots-scan-orchestration.md`](M3-03-source-roots-scan-orchestration.md) — roots, módulos instalados y lifecycle incremental.
4. [`M3-04-manifest-python-ast.md`](M3-04-manifest-python-ast.md) — manifest literal y Python AST.
5. [`M3-05-xml-csv-incremental.md`](M3-05-xml-csv-incremental.md) — XML, CSV de seguridad y cleanup stale.
6. [`M3-06-source-query-evidence.md`](M3-06-source-query-evidence.md) — `find_symbol`, `find_model_extensions` y `read_excerpt`.
7. [`M3-07-file-log-provider.md`](M3-07-file-log-provider.md) — FileLogProvider bounded.
8. [`M3-08-journal-traceback-redaction.md`](M3-08-journal-traceback-redaction.md) — JournalLogProvider, tracebacks, fingerprint y redacción común.
9. [`M3-09-diagnostics-e2e.md`](M3-09-diagnostics-e2e.md) — fixture Odoo 18 + Diagnostics + E2E real de source/logs.
10. [`M3-10-gate.md`](M3-10-gate.md) — gate integral y cierre de M3.

Ejecutar una sola task cada vez. Cada task inspecciona el estado real dejado por la anterior, ejecuta sus verificaciones y se detiene. No avanzar automáticamente a la siguiente.

## Invariantes de M3

- Los scanners/providers sólo reciben roots, paths o units resueltos y validados; nunca escanean el host entero.
- Los defaults de deployment son hints, no contratos. Deben existir overrides configurables sin editar Python.
- Los módulos instalados se obtienen por boundary/runtime Odoo; no se infieren por nombres de carpetas.
- El scanner estático no importa ni ejecuta addons.
- Los manifests sólo se evalúan de forma literal; un manifest dinámico se marca como no evaluable.
- Python se analiza con AST; metaprogramación y monkey patches no resueltos se declaran como limitación.
- XML se parsea sin entidades externas/network; CSV de seguridad representa declaraciones estáticas, no permisos efectivos.
- No clasificar código como `custom` sólo por el path. La provenance debe ser conservadora.
- `source.read_excerpt` sólo lee una ref emitida por el índice y revalida root + fingerprint; no acepta paths libres.
- Source stale no se devuelve como evidencia `checked`.
- Logs se consultan bajo demanda; no se ingieren completos ni se almacenan indefinidamente.
- File/Journal providers aplican caps de tiempo, líneas y bytes server-side.
- JournalLogProvider no usa `shell=True` ni recibe command text libre.
- Todo source/log recuperado se trata como datos no confiables y se redacta antes de salir del provider boundary.
- No introducir `sudo()`, SQL directo a Odoo, `execute_kw`, `execute_method`, shell libre, SQL arbitrario o Python arbitrario.
- M3 no implementa Codex, dynamicTools, RAG documental, QUERY, writes, approvals ni business actions.
- Al terminar M3, source y logs pueden estar operativos, pero el readiness global sigue `DEGRADED` mientras `reasoning_engine` pertenezca a M4.

## Gate de M3

M3 sólo se considera terminado cuando:

- scanner encuentra el método fixture y sus líneas correctas;
- el scan es incremental y un cambio de source invalida el fingerprint anterior;
- XML/CSV y cleanup stale funcionan;
- `find_symbol`, `find_model_extensions` y `read_excerpt` son bounded y seguros;
- FileLogProvider recupera el traceback fixture por ventana/términos;
- JournalLogProvider cumple el mismo contract cuando está configurado y no expone una superficie de shell;
- tracebacks tienen fingerprint estable y agrupación básica;
- secretos del fixture quedan redactados;
- Diagnostics demuestra source + logs sin exponer paths arbitrarios, tokens ni secretos al browser;
- layouts convencionales y no convencionales funcionan mediante autodetección/overrides;
- tests, lint, type-check y regresiones M1/M2 siguen verdes;
- no se ha adelantado M4+.
