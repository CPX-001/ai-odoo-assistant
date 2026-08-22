# M5-08 — Panel multi-workflow, routing y hardening

## Contexto

- Requiere M5-04 y M5-07 verdes.
- M4 ya aporta panel EXPLAIN y la frontera browser → Odoo → Assistant.
- M5 añade QUERY y HOW_TO sin convertir la selección de workflow en una ampliación de autoridad controlada por el modelo.

## Objetivo

Integrar EXPLAIN, QUERY y HOW_TO en la experiencia Odoo de sólo lectura, con routing explícito/bounded, citas por tipo, diagnostics de capabilities y una batería de seguridad transversal.

## Debes implementar

### Routing

Elige la solución más pequeña compatible con el producto real:

- selección explícita server-side/UX de workflow; o
- clasificador bounded que **sólo elige un workflow antes de construir el registry**, sin conceder tools adicionales después.

La decisión de workflow nunca puede provenir de una tool call ni de texto no confiable dentro de Evidence. Si la intención es ambigua, fallar/degradar o pedir reformulación; no ofrecer la unión de todas las tools “por si acaso”.

### Panel

- conservar el flujo M4 EXPLAIN;
- permitir QUERY y HOW_TO;
- estados loading/error/double-submit bounded;
- render de answer/confidence/limitations;
- render de record/query, navigation/schema y document citations según corresponda;
- `t-esc`/text rendering, sin `t-raw`/`innerHTML` para contenido generado;
- nunca incluir delegation/shared secrets, internal URLs, roots o physical paths.

### API/browser boundary

- browser hace requests sólo a Odoo;
- Odoo deriva identidad/compañías/delegación y workflow autorizado server-side;
- Assistant endpoints permanecen autenticados server-to-server;
- errores browser-facing conservan códigos pequeños y accionables.

### Diagnostics/readiness

Exponer estado sanitizado para las nuevas capabilities (`query`, `navigation`, `knowledge`, `how_to`) sin redefinir silenciosamente el significado de `FULLY_READY` fijado en milestones previos. Si el Source of Truth exige cambiar readiness global, detenerse y tratarlo como cambio documental/ADR correspondiente.

### Hardening transversal

Añade pruebas contra:

- prompt injection en records, labels de menú, metadata y documentos;
- workflow confusion/authority escalation;
- argumentos QUERY manipulados;
- refs/fingerprints documentales stale;
- unknown/duplicate App Server events/tool calls;
- canaries de secrets;
- XSS/HTML/Markdown hostil;
- oversized inputs/outputs;
- timeout/interruption y cleanup del runtime.

El registry final de cada workflow debe ser inspeccionable en tests y contener sólo las tools necesarias.

## Fuera de scope

- ACTION/M6;
- writes o approvals;
- chat platform/memoria larga completa;
- auto-navigation/clicks en browser;
- selector genérico de providers.

## Tests obligatorios

- routing EXPLAIN/QUERY/HOW_TO correcto;
- intento de cambiar workflow desde Evidence no amplía tools;
- registry least-privilege por workflow;
- browser network sólo Odoo;
- ACL negativa antes de ejecutar reasoning cuando corresponda;
- XSS para todos los tipos de cita;
- canary no aparece en response/traces;
- engine/knowledge/query unavailable degradan de forma controlada;
- M4 panel tests siguen verdes;
- addon install/update/tests, suite, Ruff y mypy.

## Acceptance criteria

- una única UI soporta los tres workflows read-only sin mezclar autoridad;
- el browser no gana nuevas fronteras de confianza;
- errores/citas son seguros y útiles;
- M5 sigue sin ninguna capacidad M6.

## Después

1. Documenta cómo se elige workflow y qué registry recibe cada uno.
2. Adjunta evidencia de tests XSS/injection/authority confusion.
3. No avances a M5-09.
