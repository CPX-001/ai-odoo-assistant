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

## Capacidad genérica y capacidad tipada

| Necesidad | Cobertura dinámica |
| --- | --- |
| Buscar modelos instalados | Registry runtime + ACL de lectura |
| Consultar registros/agregados | Schema efectivo, domains y campos acotados |
| Crear un registro | Schema create efectivo + `default_get` real |
| Cambiar campos escalares/many2one | Schema write efectivo, máximo 16 campos |
| Archivar | Acción reversible tipada sobre un registro elegible |
| Borrar | Un registro, protegido, con ACL `unlink` y preview |
| Ejecutar un método empresarial | Sólo business action tipada/versionada |

Los campos x2many, binary, HTML de escritura, referencias polimórficas, JSON y
familias sensibles permanecen fuera del CRUD genérico. No se traducen a command
lists de Odoo desde texto libre.

## Resolución de una petición

El ReasoningEngine aplica:

```text
mensaje -> conversación -> pantalla/registro/compañía
-> búsqueda de modelos y registros -> defaults/schema
-> inferencia segura -> pregunta mínima
```

El modelo puede pedir lecturas y previews, pero el host vuelve a validar todas
las llamadas. En la salida estructurada sólo se aceptan pasos que correspondan
exactamente a previews realmente emitidas en ese turn.

## Decisión y commit

`AgentTurnService` normaliza el plan. El Policy Engine calcula el riesgo y la
política efectiva. Un plan autorizado automáticamente pasa al executor; si no,
la UI muestra una única confirmación. El navegador no recibe argumentos
ejecutables, tokens ni autoridad.

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
