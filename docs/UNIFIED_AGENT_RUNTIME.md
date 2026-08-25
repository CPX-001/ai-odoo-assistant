# Operación del agente unificado

Este documento describe el runtime activo definido por ADR-014. Los informes
M5/M6 anteriores son evidencia histórica de gates, no el mecanismo de routing
actual.

## Qué puede descubrir

El agente no está limitado a una lista de módulos compilada en el Assistant
Service. Al iniciar un turn, Odoo aporta una lista pequeña de modelos visibles
relacionados con la pantalla y el mensaje. Si la petición se refiere a otro
concepto, `odoo.search_models` consulta el registry de la base en ejecución.

Esto cubre modelos aportados por:

- Odoo Community y módulos oficiales instalados;
- OCA;
- proveedores terceros;
- addons propios del cliente.

Un resultado de búsqueda no concede permisos. Odoo repite la comprobación del
modelo y construye el schema efectivo antes de leer o preparar un write.

El agente dispone además de `odoo.get_instance_facts`, que obtiene mediante el
endpoint machine-authenticated de inventario la versión real del servidor y los
nombres técnicos de módulos instalados. No expone la base de datos ni las rutas
físicas de addons. Esta consulta es lazy: no se ejecuta en todos los turnos, pero
sí debe usarse cuando una respuesta pueda cambiar según versión o módulos.

## Capacidad genérica y capacidad tipada

| Necesidad | Cobertura dinámica actual |
| --- | --- |
| Detectar versión/módulos instalados | Inventario runtime machine-authenticated |
| Buscar modelos instalados | Registry runtime + ACL de lectura |
| Consultar registros/agregados | Schema efectivo, domains y campos acotados |
| Explorar addon conocido | Índice estructural acotado + refs fingerprinted |
| Crear un registro | Schema create efectivo + `default_get` real |
| Cambiar campos escalares/many2one | Schema write efectivo, máximo 16 campos |
| Archivar | Acción reversible tipada sobre un registro elegible |
| Borrar | Un registro por proposal ACTION actual, con ACL `unlink` y preview |
| Ejecutar un método empresarial | Sólo business action tipada/versionada |

Los campos x2many, binary, HTML de escritura, referencias polimórficas, JSON y
familias sensibles permanecen fuera del CRUD genérico. No se traducen a command
lists de Odoo desde texto libre.

### Evolución batch

ADR-015 define la evolución de create/patch/delete hacia mutaciones masivas. Ya
existen cuatro piezas separadas:

1. contratos provider-neutral de filas/resultados (`contracts/batch.py`);
2. planner determinista de chunks (`application/batching.py`);
3. orquestador provider-neutral con resultado por fila (`application/batch_execution.py`);
4. helper ORM Odoo que intenta el camino bulk y, si falla, aísla filas mediante
   savepoints (`addons/.../services/batch_tools.py`).

Defaults iniciales para servidores self-hosted modestos:

- create: 50 filas por chunk;
- patch: 50 filas por chunk;
- delete: 100 ids por chunk;
- máximo host-side: 200 filas por chunk;
- un `BatchMutationRequest` en memoria: máximo 500 filas.

Los patches con valores idénticos se agrupan para poder ejecutar un
`recordset.write(vals)`. Creates usan como estrategia objetivo multi-create y
deletes `recordset.unlink()` por chunk.

El modo genérico por defecto es `continue_on_error`: primero se intenta la
operación optimizada del chunk; si Odoo la rechaza, se revierte únicamente ese
savepoint y se reintentan sus filas de forma aislada. Una fila fallida queda sin
aplicar, el resto continúa y el resultado conserva `source_ref` para notificar
exactamente qué dato falló. `atomic_chunk` queda reservado para operaciones cuya
semántica empresarial requiera todo-o-nada.

Una importación grande no se modelará como miles de AgentPlanSteps: se persistirá
como job y alimentará batches acotados. El pipeline de archivos futuro será
parser determinista/streaming -> perfil y muestra -> mapping semántico asistido
por Codex -> validación Odoo -> filas normalizadas persistidas -> ejecución
batch. Codex no será el parser de volumen.

Estas piezas todavía no convierten el tool ACTION individual en un proposal
batch de primera clase; falta cablear preview, authority, receipt y plan como una
única operación masiva antes de exponerlo al ReasoningEngine.

## Resolución de una petición

El ReasoningEngine aplica:

```text
mensaje -> conversación -> pantalla/registro/compañía
-> versión/módulos si son relevantes
-> búsqueda de modelos/registros o retrieval mínimo
-> defaults/schema -> inferencia segura -> pregunta mínima
```

El modelo puede pedir lecturas y previews, pero el host vuelve a validar todas
las llamadas. En la salida estructurada sólo se aceptan pasos que correspondan
exactamente a previews realmente emitidas en ese turn.

El riesgo no es por sí mismo una ambigüedad. Si el usuario ha expresado un
alcance inequívoco (por ejemplo, "todos los pedidos visibles"), Codex no debe
usar una pregunta conversacional como segunda capa de aprobación; el host decide
si corresponde confirmar según el perfil de autonomía del usuario.

### Preguntas teóricas, configuración y HOW_TO

Una pregunta teórica no debe convertirse automáticamente en una respuesta
enciclopédica genérica. Se distingue entre conocimiento realmente general y una
pregunta sobre **esta instalación**.

Para una petición como "¿hay alguna configuración de facturación que habilite
opciones adicionales como analítica?", el comportamiento esperado es:

1. comprobar versión y módulos instalados si pueden cambiar la respuesta;
2. consultar knowledge configurado y leer el excerpt verificado si hay
   documentación relevante;
3. usar schema/navigation runtime cuando aporte una ubicación o capacidad real;
4. si interviene un addon custom/OCA/tercero, verificar que está instalado y,
   cuando no se conoce el símbolo exacto, usar `source.inspect_module` para
   obtener la estructura indexada; después abrir sólo los excerpts relevantes
   mediante refs con fingerprint;
5. responder primero con la conclusión y después sólo con los detalles útiles.

El agente no debe inventar un menú, sección de Settings, checkbox, dependencia o
campo exacto. Si puede validar la funcionalidad pero no la ubicación visual,
debe decirlo expresamente en vez de rellenar el hueco con "seguramente está en
Ajustes". Si el retrieval necesario está temporalmente indisponible, puede dar
orientación general claramente marcada como tal y bajar la confianza, pero no
presentarla como un hecho observado en el servidor.

`source.inspect_module` no concede acceso libre al filesystem: sólo enumera una
cantidad acotada de símbolos del índice persistente de un módulo técnico exacto.
El contenido de código sigue requiriendo `source.read_excerpt`, que vuelve a
validar el fingerprint contra el fichero actual. No se ejecuta shell, grep libre
ni rescan durante el turno.

## Decisión y commit

`AgentTurnService` normaliza el plan. El Policy Engine calcula el riesgo y
resuelve los límites host-side. La confirmación del Assistant se deriva del
**perfil visible del usuario**, no de una intersección oculta que pueda volver
más estricto el selector. Las capas de sistema/administrador/conversación pueden
seguir reduciendo budgets técnicos o desactivar datos sintéticos, pero no
cambiar silenciosamente `confirmation_mode`/`max_auto_risk` elegidos por el
usuario.

Perfiles:

- `strict`: confirma cualquier escritura;
- `balanced`: autoejecuta hasta riesgo moderado;
- `autonomous`: autoejecuta hasta riesgo alto y confirma efectos protegidos;
- `full_access`: no añade confirmaciones del Assistant, incluso para riesgo
  protegido, conservando permisos/reglas reales de Odoo y límites host-side.

Un plan autoautorizado se ejecuta en el mismo turn. Después del commit, la
respuesta mostrada al usuario se deriva del estado host-side real: completado y
verificado, parcial o fallido. El texto previo de Codex no puede afirmar que una
operación sigue "sólo previsualizada" después de que el host ya la ejecutó.

Una denegación ACL/record rule y una `UserError`/`ValidationError` de negocio son
causas distintas de fallo y se reportan como tales; ninguna se presenta como si
faltara otra confirmación.

Estados persistidos:

```text
planning -> awaiting_confirmation | authorized -> executing
-> completed | partial | failed
```

También pueden aparecer `rejected` y `expired`. Cualquier cambio en payload,
orden, dependencias, preview, actor, compañías, revisión, policy o estado stale
invalida la autorización.

## Flujo comercial incluido

`sale.order.build_flow.v1` se ejecuta en una transacción Odoo bajo el usuario
real:

- `quotation`: crea presupuesto borrador (`low`);
- `sale_order`: crea y confirma el presupuesto (`moderate`);
- `invoice_draft`: confirma y crea factura borrador (`high`).

"Crear un presupuesto y validarlo" termina en `sale_order`. No se crea factura
salvo que el usuario la pida o la intención completa la implique claramente.
Contabilizar, pagar o comunicar fuera de Odoo requiere otra acción protegida;
esas capabilities no se exponen por inferencia.

`full_access` no salta reglas de negocio del modelo. Por ejemplo, si Odoo no
permite `unlink()` en el estado actual de un documento, el commit devuelve
`business_rule_rejected`; para automatizar esa intención hace falta una business
action tipada que realice la transición válida, no `sudo()` ni SQL.

## Diagnóstico de modelos de terceros

Si un modelo esperado no aparece, comprobar en orden:

1. el módulo está instalado en esa base y el modelo existe en el registry;
2. el usuario real tiene ACL de lectura;
3. no es abstract/transient ni técnico bloqueado;
4. sus campos útiles pasan field access y los tipos soportados;
5. para writes, el usuario tiene `create`/`write`/`unlink` según la operación.

No se debe ampliar una allowlist en el prompt para resolverlo. La corrección es
instalar/configurar el módulo o los permisos de Odoo, o añadir una business
action tipada si lo que falta es semántica de proceso.
