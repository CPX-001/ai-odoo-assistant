# Arquitectura operativa

Esta referencia resume decisiones del [Source of Truth v1.1](source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.1.pdf). No lo sustituye ni añade decisiones nuevas. La política concreta de autodetección/overrides está en [DEPLOYMENT_CONFIG.md](DEPLOYMENT_CONFIG.md) y el runtime del agente en [UNIFIED_AGENT_RUNTIME.md](UNIFIED_AGENT_RUNTIME.md).

```text
Odoo addon
    ↓
Assistant Service
    ↓
Evidence / Tools / Reasoning
```

## Boundaries

- **Browser/Owl:** captura navegación y ofrece UX. Habla sólo con Odoo durante el MVP; no decide permisos ni aporta identidad confiable.
- **Odoo addon:** deriva identidad, ejecuta ORM bajo el usuario real, gestiona settings, delegación y approvals. No ejecuta el LLM ni scans pesados.
- **Assistant Service:** orquesta turns, retrieval, tools, persistencia y observabilidad. No accede por SQL a la DB Odoo ni usa `sudo()`.
- **ReasoningEngine:** razona y solicita tools dentro de contratos y límites. No posee autoridad Odoo ni conoce detalles de transporte.
- **Source/Log providers:** recuperan evidencia acotada del host; no reciben instrucciones libres del modelo.

## Deployment adaptable

El perfil inicial probado es Odoo 18 Community sobre Linux self-hosted con PostgreSQL, pero el layout del cliente es runtime data, no arquitectura.

No asumir rutas o nombres concretos para `odoo.conf`, service unit, usuario Odoo, addons, `data_dir`, logs o PostgreSQL. Las rutas convencionales pueden usarse como hints de autodetección siempre que exista override explícito.

Prioridad conceptual de resolución:

```text
override de administrador
    ↓
runtime Odoo confirmado
    ↓
metadata de proceso/supervisor
    ↓
config Odoo
    ↓
hints convencionales
```

Si un dato sigue desconocido o ambiguo, se representa como tal y se resuelve por configuración/capability; no se inventa. Odoo Settings será la superficie normal para overrides administrables, mientras los cambios que requieran privilegios del host permanecen detrás del bootstrap/setup boundary.

El Assistant Service puede usar systemd en el perfil MVP aunque Odoo use un supervisor distinto. Igualmente, la Assistant DB puede estar en el mismo cluster PostgreSQL por defecto sin que las interfaces generales dependan de `localhost` o de ese cluster concreto.

## Persistencia separada

El Assistant usa una DB PostgreSQL propia para conversaciones, índices, scans, approvals, auditoría y trazas. No replica datos vivos de negocio ni recibe credenciales SQL de la DB productiva de Odoo.

## Identidad

La identidad efectiva, compañías y contexto de seguridad se derivan server-side. Cada tool vuelve a validar delegación y policy; Odoo aplica ACL, record rules, restricciones de campos y reglas de negocio. `ScreenContext` es sólo una pista de navegación y los registros se releen por ORM bajo el usuario real.

## Runtime schemas y módulos instalados

Los schemas efectivos se descubren en runtime bajo el usuario, compañías y policy actuales. No se crean clases por major de Odoo ni catálogos por módulo. El catálogo de instancia sirve para descubrimiento; sólo `EffectiveModelSchema`/`EffectiveWriteSchema` gobiernan la exposición y validación de fields durante un turn.

La lista inicial de modelos es una pista. `odoo.search_models` consulta el registry real y descubre modelos instalados de Odoo, OCA, terceros o addons propios. Cada candidato se revalida bajo el usuario real antes de buscar, leer o preparar un write. El CRUD genérico escalar se adapta al schema runtime; los métodos y transiciones empresariales siguen necesitando business actions tipadas.

## ReasoningEngine y agente unificado

`ReasoningEngine` es un port estable. Codex App Server por stdio es el adapter inicial y su acoplamiento queda confinado al engine. Cada turn recibe un `ContextPack` compacto y tools explícitas. No existen categorías de routing ni workflows excluyentes: el modelo puede combinar lecturas y propuestas en un único plan.

Codex sólo solicita tools de lectura/preview y propone argumentos. `AgentTurnService`, `ToolExecutor`, el Policy Engine y Odoo validan registry, schemas, ACL, record rules, budgets, riesgo, autorización, commit y verificación. La memoria de producto vive en la DB del Assistant, no en threads de Codex.

### Streaming y recuperación de fallos

El chat puede transportar texto provisional mediante SSE sin cambiar las fronteras de autoridad:

```text
Codex App Server delta
    → Assistant Service SSE
    → relay SSE autenticado de Odoo
    → Owl
```

Los eventos provisionales contienen únicamente texto incremental extraído de `answer_markdown`; nunca incluyen plan, argumentos, fingerprints, receipts, authority ni razonamiento interno. El único estado autoritativo del turn llega en un evento terminal `final`, validado por el Assistant Service y después de nuevo por el bridge Odoo antes de exponerse al navegador. Si el stream se corta, termina sin `final` o entrega un payload no válido, el texto provisional no se acepta como resultado definitivo y se sustituye por un turn fallido conversacional.

El navegador continúa autenticándose sólo contra Odoo. El shared secret Assistant↔Odoo nunca se entrega a JavaScript y el POST SSE de Odoo conserva la protección CSRF. La preparación ORM —usuario, compañías, policy, capability y modelo— se completa antes de devolver el iterador WSGI; el relay no reutiliza recordsets ni `request.env` una vez que la transacción del controlador ha terminado.

Los fallos esperables del agente se presentan como respuestas del Assistant, no como códigos internos. Cuando Codex sigue disponible, un recovery separado y read-only puede recibir estado de Diagnostics y extractos de logs acotados, redactados y correlacionados con el `turn_id`. Ese recovery no dispone de tools, no repite la operación fallida y no puede escribir. Su salida debe explicar el problema en lenguaje normal y sólo puede ofrecer un reintento/corrección si el host ha marcado explícitamente esa siguiente acción como válida. Si el recovery no puede ejecutarse o su salida filtra identificadores internos, se usa un fallback host-owned corto.

Una pérdida de comunicación o timeout no demuestra que una escritura no llegara a ejecutarse. En esos casos la UI no afirma “no hubo cambios”: marca el resultado como no confirmado y pide comprobar el estado actual antes de repetir una operación. Los códigos técnicos permanecen en logs/Diagnostics.

El perfil actual mantiene un App Server acotado por turn y threads efímeros, con cierre bounded al terminar. No se usa un daemon Codex compartido como memoria de conversación; la continuidad vive en la DB del Assistant. Esto conserva aislamiento entre turns y evita que el estado interno de un proceso defectuoso se convierta en autoridad o memoria de producto.

## Retrieval y evidencia

Primero retrieval estructural y lexical: símbolos/relaciones para source, PostgreSQL FTS para documentos y búsqueda temporal acotada para logs. Los providers de source y logs son obligatorios para `FULLY_READY`. La evidencia recuperada se trata como datos no confiables, se redacta y se entrega en resultados estructurados.

Los scanners/providers reciben roots, units y paths resueltos/validados. No contienen paths de cliente como constantes y nunca escanean todo el host para compensar una detección incompleta.

## Writes, autonomía y riesgo

Los efectos siguen el flujo:

```text
proposal → preview → autorización host-side → commit → verification → audit
```

Odoo sigue siendo la autoridad real: ACL, record rules, field access, compañías y reglas de negocio. Encima de esa autoridad el usuario elige un perfil simple de autonomía del Assistant:

- `strict`: confirma cualquier escritura;
- `balanced`: autoejecuta hasta riesgo moderado;
- `autonomous`: autoejecuta hasta riesgo alto y confirma efectos protegidos;
- `full_access`: no añade confirmaciones del Assistant.

`full_access` no implica `sudo()`, métodos arbitrarios ni eliminación de límites host-side. Sólo retira la capa adicional de confirmación del Assistant. El host sigue calculando riesgo para trazabilidad y UI, pero el riesgo no se convierte por sí mismo en una pregunta conversacional. Si el usuario expresó un alcance inequívoco, Codex debe preparar la acción y dejar que el perfil decida si corresponde confirmar.

La autorización se liga al plan ordenado, payloads, previews, dependencias, actor, base, compañías, revisiones y snapshot de policy. Los business actions usan handlers allowlisted; nunca métodos arbitrarios.

Antes de preguntar se resuelve `mensaje → conversación → contexto Odoo → búsqueda de registros → defaults/schema → inferencia segura → preguntar`. Datos sintéticos sólo en prueba/demo explícita o con autorización, siempre marcados `AI TEST`.

Los límites máximos host-side actuales son 32 tool calls, 12 write steps por plan, dos replans y tres fallos consecutivos. Una llamada canónica no se repite sin cambio de precondición y un write incierto nunca se reintenta automáticamente.

### Mutaciones masivas e importaciones

ADR-015 separa semántica de volumen. El camino objetivo es:

```text
archivo/datos
  → parsing determinista
  → mapping semántico asistido
  → schema/ACL validation
  → filas normalizadas persistidas
  → chunks batch
  → preview/autorización
  → ORM optimizado
  → receipts por origen
```

Codex interpreta headers, muestras y ambigüedades; no procesa miles de filas dentro del prompt. El planner batch ya existe como capa independiente. Create aprovechará multi-create, delete recordsets y patch agrupará valores idénticos antes de ejecutar. La integración del batch con proposals/approval/execution se realiza como fase separada para no mezclar responsabilidades.

## Prohibiciones principales

- `sudo()` en los caminos normales del agente.
- SQL directo del Assistant Service contra Odoo.
- Shell libre, SQL arbitrario o Python arbitrario.
- `execute_method` / `execute_kw` genérico como tool del modelo.
- Identidad confiada desde JavaScript.
- Secretos en prompts.
- Writes sin validación y approval cuando corresponda.
- Checks de major de Odoo dentro de `application`, salvo excepción documentada por ADR.
- Paths/nombres del entorno DEV convertidos en contratos de deployment.

Para contratos, flujos y threat model completos, consultar el Source of Truth.
