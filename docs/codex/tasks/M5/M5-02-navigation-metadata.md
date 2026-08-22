# M5-02 — Navegación y metadata visible

## Contexto

- Requiere M5-01 verde.
- HOW_TO debe adaptarse a la instalación real y no puede asumir rutas de menú hardcodeadas.
- Odoo sigue siendo la autoridad sobre qué menús, acciones y modelos son visibles para el usuario efectivo.

## Objetivo

Añadir una capability read-only y acotada para obtener navegación útil de Odoo bajo el usuario real y convertirla en Evidence `METADATA` checked apta para HOW_TO.

## Contratos que NO puedes romper

- browser no llama al Assistant Service ni a endpoints internos;
- ninguna identidad confiable procede de JS;
- `OdooGateway` no se convierte en un cliente RPC genérico;
- no ejecutar acciones arbitrarias ni evaluar código/contextos/domains recibidos del modelo.

## Debes implementar

### Contratos

Tipos pequeños equivalentes a:

- entrada de navegación: id lógico, label, parent/path lógico, sequence opcional;
- action summary: tipo soportado, target model/view modes cuando sea seguro;
- resultado/capability con timestamp y límites.

Los contratos no deben contener URLs internas, physical paths, credentials ni objetos Odoo serializados.

### Boundary Odoo

Crear un endpoint/capability interno específico que:

- use machine auth + delegación/autoridad server-side;
- construya el entorno como usuario efectivo `su=False`;
- devuelva únicamente menús realmente visibles/accesibles;
- resuelva sólo tipos de acción necesarios para navegación HOW_TO;
- aplique caps de profundidad, nodos y bytes;
- normalice labels y modelos de forma determinista;
- rechace action types o payloads no soportados en vez de devolver estructuras crudas.

No devuelvas ni ejecutes `context`, `domain`, server actions, Python expressions o URLs arbitrarias como autoridad para el agente.

### Service

- extender la boundary estable sólo con una operación estrecha de navegación;
- producir Evidence `METADATA` checked con un pointer lógico estable;
- conservar el resultado como datos no confiables frente a prompt injection.

## Fuera de scope

- ejecutar acciones o navegar el browser automáticamente;
- QUERY de registros;
- documentación/RAG;
- writes;
- crawler de toda la UI.

## Tests obligatorios

- usuario ve únicamente sus menús permitidos;
- menú oculto/grupo no permitido no aparece;
- multi-company no amplía visibilidad;
- action type desconocido se ignora/rechaza de forma segura;
- caps de profundidad/nodos/bytes;
- labels adversariales no se interpretan como instrucciones;
- no se filtran domains/contextos/URLs/secrets;
- replay/authority del turn permanece acotada;
- suite, Ruff y mypy.

## Acceptance criteria

- HOW_TO puede conocer una ruta de navegación real sin hardcodearla;
- el resultado está ligado al usuario efectivo y es citable;
- no existe un ejecutor genérico de acciones;
- no se ha implementado todavía HOW_TO.

## Después

1. Muestra un ejemplo sanitizado de árbol/path visible.
2. Lista los action types admitidos y por qué.
3. No avances a M5-03.
