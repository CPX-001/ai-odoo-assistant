# ADR-015 — Mutaciones masivas e ingesta de archivos

## Estado

Accepted

## Contexto

El agente unificado actual modela create, patch y delete como propuestas de un solo registro. Ese diseño es adecuado para cambios interactivos pequeños, pero escala mal para cientos o miles de filas y no sirve como base eficiente para futuras importaciones CSV/XLSX.

El objetivo es permitir operaciones masivas sin convertir a Codex en un parser de hojas de cálculo ni obligarlo a emitir miles de filas como JSON. La instancia objetivo puede ser un servidor self-hosted modesto (CPU convencional, ~12 GB RAM DDR4 y SSD), por lo que deben limitarse memoria, tamaño de prompts, round-trips y llamadas ORM.

## Decisión

### 1. Separar interpretación semántica de procesamiento de volumen

El pipeline futuro de archivos será:

```text
upload Odoo
  -> almacenamiento temporal acotado + hash
  -> parser determinista/streaming CSV/XLSX
  -> perfil de columnas, tipos, cardinalidades y muestra acotada
  -> Codex propone mapping y normalizaciones semánticas
  -> host valida mapping contra EffectiveWriteSchema
  -> resolución de referencias Odoo
  -> filas normalizadas persistidas
  -> BatchMutationRequest acotados
  -> preview/resumen batch
  -> política/autorización
  -> ejecución por chunks
  -> receipts + errores por fila
```

Codex no recibirá el workbook completo salvo archivos diminutos. Para archivos grandes verá headers, muestras representativas, estadísticas acotadas, schemas y únicamente las filas problemáticas necesarias para resolver ambigüedades.

### 2. Contrato batch independiente de archivos

`contracts/batch.py` representa filas ya normalizadas mediante tres familias:

- `create`: valores tipados para un registro nuevo;
- `patch`: `record_id` + cambios tipados;
- `delete`: `record_id`.

Cada fila conserva `source_ref` para poder enlazar errores y receipts con una fila/origen futuro (`sheet:Clientes:42`, `csv:120`, etc.). Un request en memoria queda limitado a 500 filas; una importación grande se persistirá y alimentará múltiples requests, no un payload gigante.

### 3. Chunking host-side y optimización por operación

Defaults iniciales para servidores modestos:

- create: 50 filas/chunk;
- patch: 50 filas/chunk;
- delete: 100 ids/chunk;
- máximo configurable por chunk: 200.

El planner está en `application/batching.py` y no depende de Odoo/Codex/storage.

La futura ejecución Odoo aprovechará la semántica real del ORM:

- create: `model.create([vals, ...])` por chunk;
- delete: `recordset.unlink()` por chunk;
- patch con valores idénticos: agrupar ids y usar `recordset.write(vals)`;
- patch heterogéneo: filas acotadas dentro del chunk, sin fingir un multi-update heterogéneo inexistente.

### 4. Validar antes de escribir

La importación tendrá una fase de preflight completa siempre que sea razonablemente posible. El mapper puede corregir automáticamente transformaciones deterministas y de intención evidente, por ejemplo:

- espacios sobrantes;
- booleanos y formatos de fecha/decimal inequívocos;
- aliases de cabecera con match fuerte contra schema;
- nombre/código externo que resuelva de forma única a un many2one.

No se autoelige una referencia cuando existen varios candidatos plausibles. Las ambigüedades materiales se muestran agrupadas y se pide una única decisión reutilizable, no una pregunta por fila.

### 5. Resolución de campos y relaciones

Para una columna como `product` cuyos valores son nombres pero Odoo espera `product_id`, Codex puede inferir que la intención es una relación a producto usando header + muestra + schema. El host debe convertir esa inferencia en una regla explícita y después resolver cada valor mediante Odoo.

Orden orientativo de resolución de many2one:

1. external/xml id explícito;
2. id interno explícito cuando proceda;
3. código/clave única conocida por schema/regla;
4. nombre exacto normalizado que produzca un único registro;
5. candidatos semánticos/fuzzy sólo como sugerencia, nunca como selección silenciosa ambigua.

### 6. Transacciones, errores y reanudación

No se mantendrá una transacción Odoo abierta durante un workbook enorme. La unidad de commit será el chunk.

El modo por defecto será `atomic_chunk`: si una fila provoca una excepción material durante el commit, se revierte ese chunk. El futuro modo `continue_on_error` podrá aislar filas con savepoints y producir errores por fila cuando el usuario prefiera maximizar throughput sobre atomicidad.

Los jobs de importación deberán ser idempotentes/reanudables y persistir progreso fuera del thread de Codex.

### 7. Seguridad y autoridad

Batching no altera las fronteras de autoridad:

- se ejecuta con el usuario Odoo real, sin `sudo()`;
- ACL, record rules, field access, compañías y reglas de negocio siguen mandando;
- Codex propone mappings/intención, no autoridad;
- los límites de chunk, tamaño de job y reintentos son host-side;
- `Acceso completo` elimina confirmaciones adicionales del Assistant, pero no permisos de Odoo ni límites anti-loop/recursos.

## Consecuencias

- Las operaciones masivas dejan de consumir un AgentPlanStep por registro.
- Un archivo de miles de filas no necesita entrar completo en contexto LLM.
- Se puede optimizar create/delete y updates homogéneos con primitivas ORM reales.
- Hace falta una segunda fase para integrar BatchMutation con preview/approval/execution.
- Hace falta una tercera fase para upload, parsing, mapping semántico, resolución de referencias y UI de importación.
- El límite actual de un registro por proposal continúa vigente hasta completar la segunda fase; ADR-015 no pretende ocultar esa limitación temporal.

## Alternativas consideradas

### Emitir un tool call por fila desde Codex

Descartado: eleva tokens, latencia, planes, approvals y llamadas ORM de forma lineal y hace impracticables importaciones grandes.

### Entregar el Excel completo a Codex y dejarle generar writes

Descartado para el camino general: alto consumo de RAM/contexto, validación débil, difícil reanudación y poca trazabilidad. Codex se reserva para inferencia semántica acotada.

### Usar directamente el importador estándar de Odoo

Útil como referencia y posible adapter futuro, pero no cubre por sí solo mapping semántico, reparación asistida, preview del agente, jobs reanudables ni operaciones bulk genéricas fuera de importación.

### Una transacción única para todo el archivo

Descartado como default: bloqueos largos, rollback costoso y mala recuperación en servidores modestos.

## Referencias

- `docs/adr/ADR-014-unified-host-authorized-agent.md`
- `docs/UNIFIED_AGENT_RUNTIME.md`
- `service/src/odoo_ai/contracts/batch.py`
- `service/src/odoo_ai/application/batching.py`
