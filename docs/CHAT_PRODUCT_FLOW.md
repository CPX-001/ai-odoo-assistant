# Product chat facade

El panel principal del producto es un **chat único**. `EXPLAIN`, `QUERY`, `HOW_TO` y `ACTION`
continúan existiendo como boundaries internos de autoridad y validación, pero ya no son una
decisión que deba tomar el usuario.

## Flujo visible

```text
usuario escribe una petición
        ↓
Odoo añade identidad efectiva + contexto de pantalla
        ↓
routing semántico multilingüe sin tools
        ↓
Codex + tools mínimas necesarias
        ↓
respuesta en el mismo chat
```

El browser no envía una identidad confiable ni selecciona un workflow. El router pide a Codex una
decisión estructurada usando el texto original, el idioma efectivo, un historial reciente acotado,
la pantalla actual y exclusivamente los modelos que Odoo acaba de comprobar como visibles y
legibles para el usuario. Esta fase no recibe tools, registros, secretos ni autoridad de ejecución.
No usa diccionarios de palabras por idioma: interpreta semánticamente la petición en el idioma en
que llegue y devuelve `workflow + target_model` junto con una reformulación autocontenida en el
mismo idioma. Esa reformulación sólo resuelve pronombres o referencias acreditadas por el historial
reciente; Odoo guarda como mensaje del usuario el texto original.

Odoo valida de nuevo ambas decisiones contra su allowlist antes de crear cualquier delegación.
`ScreenContext` sigue siendo una pista: una pregunta puede referirse a otro modelo distinto al que
está abierto, pero nunca a uno que las ACL/record rules hayan dejado fuera. La respuesta se redacta
en el idioma de la petición o, si no está claro, en el idioma efectivo del usuario; los nombres
técnicos de modelo/campo se traducen a operaciones Odoo mediante metadata runtime, no con clases o
aliases específicos de una versión o lengua.

Las peticiones generales de código, módulos, arquitectura o documentación usan un turno de
lectura que puede consultar el índice persistente de source y conocimiento sin exigir un registro
abierto. Si source está degradado, ese turno puede continuar con conocimiento e historial en vez
de convertir la falta de source en un fallo global del chat.

## Memoria

La memoria de producto no depende de threads de Codex:

- conversaciones y mensajes enviados viven en la PostgreSQL propia del Assistant;
- se aíslan por `database + uid` derivados por Odoo;
- el turno general recibe un resumen acotado de mensajes recientes;
- el texto todavía no enviado vive en `localStorage` por host/usuario/conversación para sobrevivir a cierres y
  recargas del panel.

El historial no replica registros de negocio ni añade un sistema de roles propio.

## Índices

Source y knowledge son estado persistente del Assistant, independiente del modelo de razonamiento.
El addon solicita un source rescan y knowledge reindex después de una instalación nueva; el mismo
refresh se solicita durante el upgrade a `18.0.7.6.0`. El trabajo pesado permanece en el Assistant
Service, no en el proceso de Odoo. Si el servicio está temporalmente degradado, install/upgrade no
se revierte y Diagnostics/Maintenance pueden repetir el refresh.

## Writes

La fachada única no amplía autoridad. Una petición de escritura sigue entrando en el boundary
ACTION existente:

```text
proposal → preview → approval → commit → verification
```

ACTION tampoco recorta familias de preview mediante expresiones regulares dependientes del idioma.
Codex puede elegir entre todas las familias preview allowlisted; el host impone el modelo/registro
actual, schemas efectivos, budgets y validaciones. Una corrección del registro abierto debe usar
`record_patch`, nunca degradarse a `record_create`. El texto libre (incluido “sí, hazlo”) no equivale
a aprobación: el commit sólo nace del endpoint explícito de decisión de Odoo.

No se añaden `sudo()`, SQL directo contra Odoo, shell libre, Python arbitrario ni métodos ORM
genéricos para el modelo. Las ACL, record rules, compañías y restricciones de campos del usuario
efectivo siguen siendo la autoridad real.
