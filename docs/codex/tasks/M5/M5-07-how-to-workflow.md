# M5-07 — Workflow HOW_TO adaptado a la instalación

## Contexto

- Requiere M5-02 y M5-06 verdes.
- HOW_TO debe combinar navegación visible, schema efectivo y knowledge documental, no responder sólo desde conocimiento general del modelo.
- M5 continúa siendo read-only.

## Objetivo

Implementar un product turn `HOW_TO` que genere pasos concretos adaptados a la instalación y al usuario efectivo, apoyándose en Evidence de navegación/schema/documentos y degradando explícitamente cuando falte soporte.

## Debes implementar

### Contratos y citas

Añade request/response y tipos de cita necesarios para HOW_TO, capaces de representar de forma browser-safe al menos:

- navegación/menu/action lógica;
- metadata/schema de modelo/campo;
- documento/excerpt con fingerprint.

No exponer physical paths, endpoints internos, raw Odoo action payloads ni contenido técnico innecesario.

### Orquestación

Un application service propio que:

1. valida contexto/identidad/autoridad;
2. obtiene navegación relevante o un catálogo bounded visible;
3. obtiene schema efectivo cuando la pregunta implica un modelo/configuración identificable;
4. construye registry HOW_TO explícito con knowledge tools y sólo las metadata tools necesarias;
5. ejecuta el `ReasoningEngine` existente con `workflow_hint=HOW_TO`;
6. recoge Evidence producida;
7. valida refs y genera citas browser-facing.

No ofrecer business-record QUERY tools por defecto a HOW_TO: ampliar el registry sólo si existe una necesidad concreta documentada y compatible con least privilege.

### Reglas de respuesta

- `workflow == HOW_TO`;
- `proposed_action is None`;
- no afirmar que existe un menú/campo/acción si no aparece en Evidence de instalación;
- si la documentación describe una ruta que la navegación actual no confirma, indicarlo como limitación;
- instrucciones específicas de instalación con `HIGH` requieren Evidence checked de instalación (navegación/schema) y soporte documental cuando la afirmación dependa de documentación;
- conocimiento general del modelo, si se permite como fallback, debe quedar identificado y no presentarse como hecho comprobado de esa instalación;
- pasos, citas y limitations bounded.

### Prompt/data boundary

Developer instructions pequeñas y estables: navigation/schema/docs son datos no confiables. Texto tipo “ignora instrucciones” dentro de un label o documento no puede cambiar policy ni tools.

### API/Odoo bridge

Añade endpoint server-to-server y bridge Odoo específico para HOW_TO, siguiendo la frontera de M4: browser → Odoo → Assistant. Errores sanitizados y timeouts bounded.

## Fuera de scope

- ejecutar automáticamente los pasos;
- writes/actions/approvals;
- navegador autónomo;
- web fetching;
- conversación persistente compleja.

## Tests obligatorios

- HOW_TO con menú + schema + documento válidos;
- menú inexistente → no inventar ruta;
- field inexistente → limitation/rechazo de afirmación;
- documentación stale → no cita checked;
- document/menu prompt injection no cambia registry;
- evidence ref inventada → rechazo;
- high confidence se degrada sin soporte requerido;
- XSS/content bounds en response;
- structured HOW_TO real con Codex si auth disponible;
- suite, Ruff y mypy.

## Acceptance criteria

- el asistente puede explicar cómo hacer algo usando hechos reales de la instalación;
- las rutas/pasos verificables tienen citas;
- ausencia de evidencia produce limitación, no invención;
- no se ejecuta ninguna acción en Odoo.

## Después

1. Muestra un HOW_TO fixture con citas de navegación/schema/documento.
2. Documenta las reglas exactas de confidence/evidence.
3. No avances a M5-08.
