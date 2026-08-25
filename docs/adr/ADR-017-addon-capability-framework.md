# ADR-017 — Framework interno de capabilities auto-descubiertas

## Estado

Accepted

## Contexto

La migración a runtime embebido de ADR-016 elimina el Assistant Service como unidad
operacional, pero copiar su composición actual literalmente dejaría otra forma de
acoplamiento: specs de tools, policy metadata, handlers y composición repartidos entre
varios ficheros y registries manuales.

Ese diseño hace que añadir una capacidad nueva obligue a tocar múltiples capas aunque
la operación sea conceptualmente una sola herramienta. El objetivo del addon es ser
extensible sin fragmentarse en addons auxiliares ni convertir modelos Odoo en un
sistema de plugins.

## Decisión

`odoo_ai_assistant` incorpora un pequeño capability host **dentro del propio addon**.

La unidad de extensión es `CapabilityDefinition`, declarada sobre un handler mediante
`@tool(...)`. Una definición contiene nombre/version, descripción, JSON Schema de
entrada/salida, riesgo, tipo de efecto, necesidad de aprobación, guards/grupos, budgets
y el handler concreto.

Los providers viven bajo:

```text
odoo_ai_assistant/runtime/capabilities/providers/
```

y se descubren recursivamente. Añadir un fichero provider con una función decorada no
requiere editar un registry central, `__init__.py`, XML, modelos, relaciones ni el
orquestador.

### Protocolo interno

El framework expone descriptors transport-neutral con forma MCP-like:

- `name`;
- `description`;
- `inputSchema`;
- `outputSchema`;
- metadata host-side de executor/risk/effect/approval/tags.

No se levanta un MCP server adicional. El runtime Codex consume el catálogo mediante un
adapter in-process. Si en el futuro se necesita MCP u OpenAPI real, el transporte se
implementará como adapter del mismo catálogo.

### Una sola abstracción para reads y actions

No existe un plugin system separado para “acciones”. Una lectura, una consulta Odoo,
una action con aprobación, retrieval, diagnóstico o una utilidad host son capabilities
del mismo protocolo. Lo que cambia es su metadata de riesgo/efecto y la policy que
decide si se anuncia o ejecuta.

La discovery no concede autoridad. El host sigue filtrando qué capabilities están
disponibles para cada turn y conserva approval/commit/verification donde corresponda.

### Acceso al runtime Odoo

Cada handler recibe un `CapabilityContext` que contiene el `Environment` efectivo del
usuario del turn (`su=False`). Así las herramientas ORM normales heredan ACLs y record
rules sin volver a cruzar HTTP ni necesitar tokens de machine auth.

El framework no limita artificialmente qué implementación puede escribirse: una
capability explícita puede encapsular servicios de filesystem, procesos, APIs o
facilidades de bajo nivel disponibles al proceso Odoo. Eso no significa que dichas
capacidades se habiliten por defecto.

En particular, el core no introduce ahora una herramienta SQL genérica; hacerlo
cambiaría las invariantes de seguridad actuales y requeriría una decisión explícita.
La arquitectura, sin embargo, no necesitaría cambiar: sería otro provider con schema,
risk/effect, policy y handler claramente declarados.

### Discovery

El loader:

1. recorre `providers/**` de forma determinista;
2. importa los módulos;
3. inspecciona sólo definitions originadas por cada módulo;
4. rechaza nombres o executor ids duplicados;
5. cachea el catálogo por worker Odoo;
6. filtra disponibilidad por contexto antes de anunciarlo al modelo.

Inputs y outputs pasan por validación de JSON Schema acotada y límites de bytes/calls.

## Consecuencias

- añadir una tool normal requiere un único fichero/handler;
- schemas, policy metadata y ejecución convergen en una sola definición;
- desaparecen progresivamente listas paralelas como `agent_tool_specs()` y
  `agent_tool_policy_specs()`;
- el composition root deja de conocer query/actions/retrieval concretos;
- se puede añadir un transporte MCP/OpenAPI sin rehacer providers;
- auto-discovery queda limitada al código instalado dentro del addon; no escanea ni
  ejecuta plugins arbitrarios del host.

## Referencias

- `docs/adr/ADR-016-embedded-odoo-runtime.md`
- `docs/CAPABILITY_FRAMEWORK.md`
- `service/src/odoo_ai/tools/executor.py` (contrato legacy a absorber)
- `service/src/odoo_ai/adapters/agent_tools.py` (composición legacy a retirar)
