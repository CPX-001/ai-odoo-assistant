# ADR-014 - Agente unificado con autoridad host-side

## Estado

Accepted

## Contexto

El router histórico clasificaba cada mensaje como `GENERAL`, `QUERY`,
`HOW_TO`, `EXPLAIN` o `ACTION` y seleccionaba un workflow excluyente. Esa
decisión simplificó los primeros vertical slices, pero fragmentaba peticiones
reales que combinan búsqueda, resolución de datos, varias lecturas y efectos.
También inducía respuestas artificiales de "solo lectura" aunque el usuario
hubiera pedido una operación permitida.

Odoo es extensible en runtime: los modelos y campos útiles dependen de los
módulos instalados, incluidos addons propios, OCA y terceros, de sus versiones,
grupos, compañías, ACL y record rules. Un catálogo estático por módulo o major
no puede representar la capacidad efectiva de una instancia.

La autonomía solicitada no puede convertir al LLM en autoridad. El modelo
puede equivocarse, recibir prompt injection o dividir artificialmente un efecto;
por tanto, riesgo, permiso, autorización y commit deben permanecer fuera del
prompt y de la salida del modelo.

## Decisión

### Un solo turno agéntico

`AgentTurnService` sustituye el clasificador y el dispatcher de workflows. El
ReasoningEngine recibe contexto real de la instancia y un catálogo explícito de
tools de lectura y preview. Puede consultar, resolver y proponer un plan con
dependencias; no declara autoridad, riesgo ni ejecución.

Las antiguas categorías desaparecen del routing y de la UX. El host puede
derivar metadata descriptiva (`needs_read`, `needs_schema`, `needs_write`,
`needs_business_action`, efectos, atomicidad y blast radius) a partir de las
tools normalizadas, sin convertirla en workflows excluyentes.

### Autoridad y ejecución

El flujo autoritativo es:

```text
mensaje/contexto Odoo
  -> lecturas y previews solicitadas por el LLM
  -> normalización de AgentTurnService
  -> ACL/schema/preconditions verificadas por Odoo
  -> Policy Engine host-side
  -> autorización automática o confirmación agrupada
  -> commit host-side
  -> verificación y receipt
  -> respuesta basada en resultados verificados
```

Codex/LLM sólo propone tools y argumentos. Nunca dispone de tools de approval,
commit, ORM genérico, `unlink`, métodos arbitrarios, SQL, Python o shell. El
Assistant Service tampoco accede por SQL a la DB productiva de Odoo. El addon
reconstruye `api.Environment` con el uid y compañías firmados, siempre con
`su=False`; después revalida ACL, record rules, field access y reglas de negocio.

### Modelos y módulos dinámicos

La lista inicial de modelos es una pista acotada, no una allowlist estática ni
una autorización. `odoo.search_models` consulta el registry real instalado y
puede descubrir modelos de Odoo, OCA, terceros o addons propios. Antes de
devolver un candidato y nuevamente antes de cada schema/read/preview, Odoo
comprueba que el modelo:

- existe en el registry de esa base;
- no es abstracto ni transient;
- no pertenece a familias técnicas bloqueadas;
- concede acceso de lectura al usuario real.

`EffectiveModelSchema` y `EffectiveWriteSchema` se calculan bajo el mismo
usuario, compañías y policy. El schema de creación incorpora únicamente
defaults serializables obtenidos mediante `default_get`; los tipos no soportados,
campos sensibles y defaults inválidos se omiten. Generic read/create/patch y
archive funcionan para cualquier modelo runtime que supere estos checks.

La extensibilidad de modelos no habilita métodos dinámicos. Los procesos con
semántica empresarial (confirmar, contabilizar, pagar, enviar, etc.) requieren
una business action tipada y versionada. La primera composición es
`sale.order.build_flow.v1`, con finales `quotation`, `sale_order` e
`invoice_draft`.

### Política y riesgo

La política efectiva es la intersección restrictiva:

```text
system ceiling ∩ administrator policy ∩ user preference ∩ conversation override
```

Los modos son `always_confirm`, `risk_based` y `protected_only`. Una capa
inferior sólo puede restringir. El host liga al plan el snapshot y fingerprint
de toda la política, actor, base, compañías, revisiones, payloads, previews,
dependencias y orden.

El riesgo agregado no suma writes. Usa el riesgo máximo, blast radius, modelos
y compañías, efecto empresarial, dependencias, atomicidad/rollback y el riesgo
propio de una business action completa. Una ejecución multi-write no atómica
sube un nivel hasta `high`; cualquier efecto externo o irreversible es
`protected`. Más de doce writes o alcance no acotable se rechazan o dividen.

La autoejecución conserva siempre
`proposal -> preview -> autorización host-side por política -> commit ->
verification -> audit`. Cuando la política no autoriza automáticamente, existe
una sola confirmación ligada al plan completo.

### Autonomía y datos ausentes

Antes de preguntar se aplica este orden:

```text
mensaje -> conversación -> contexto Odoo -> búsqueda de registros
-> defaults/schema -> inferencia segura -> preguntar
```

Los datos sintéticos sólo se permiten cuando el usuario pide explícitamente un
escenario de prueba/demo/ficticio o la conversación lo autoriza dentro de la
policy superior; se marcan como `AI TEST`. Evidencias y registros nunca pueden
modificar policy, riesgo o autoridad. Las modificaciones de policy por lenguaje
natural sólo pueden proceder del último mensaje directo del usuario.

### Límites host-side

Los límites máximos son 32 tool calls por turn, 12 writes por plan, dos replans
y tres fallos consecutivos. Una llamada canónica no se repite sin un cambio de
precondición/evidencia controlado por el host. Una lectura transitoria puede
reintentarse una vez; un write incierto nunca se repite automáticamente y se
reconcilia por idempotencia, receipt y verificación.

## Consecuencias

- Las peticiones largas pueden combinar lectura y efectos sin caer en una sola
  categoría visible.
- Instalar un addon no exige añadir clases ni rutas por modelo para obtener
  lectura y CRUD escalar seguro; sus modelos aparecen a través del registry
  runtime si el usuario tiene acceso.
- Añadir un proceso de negocio nuevo sí exige una spec/handler tipado, porque la
  semántica y el riesgo no se pueden inferir como autoridad desde el LLM.
- El plan y sus receipts requieren persistencia propia, introducida por la
  migración `0014_agent_plans`.
- Las previews antiguas siguen siendo componentes internos reutilizados, pero
  `/v1/chat/route`, `ChatRoute*` y el enum de workflow dejan de formar parte del
  producto activo.
- El diseño gana autonomía funcional a cambio de más validación determinista en
  el host y de contratos estrictos para planes, policy y receipts.

## Alternativas consideradas

- **Mantener categorías y añadir más workflows.** Rechazada: multiplica ramas y
  no resuelve peticiones combinadas.
- **Exponer ORM o métodos genéricos al LLM.** Rechazada: mezcla propuesta con
  autoridad y rompe el threat model.
- **Allowlist estática de módulos/modelos conocidos.** Rechazada: no cubre OCA,
  terceros ni customizaciones de cada base.
- **Autoaprobar por una etiqueta de riesgo generada por el modelo.** Rechazada:
  el riesgo se deriva de specs y estado host-side.
- **Confirmar cada write.** Rechazada como único modo: añade fricción a cambios
  pequeños sin mejorar la autoridad; se conserva como preferencia configurable.

## Referencias

- `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.1.pdf`
- `docs/ARCHITECTURE.md`
- `docs/UNIFIED_AGENT_RUNTIME.md`
- `migrations/versions/0014_agent_plans.py`
- `service/src/odoo_ai/application/agent_turn.py`
- `service/src/odoo_ai/application/agent_policy.py`
- `addons/odoo_ai_assistant/services/turn_context.py`
