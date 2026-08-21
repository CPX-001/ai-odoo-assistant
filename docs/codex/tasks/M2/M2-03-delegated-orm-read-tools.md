# M2-03 — Tools internos de relectura ORM delegada

## Contexto

- Requiere M2-02 verde.
- El Assistant Service nunca accede por SQL a la DB Odoo; las lecturas vivas se ejecutan dentro de Odoo bajo el usuario real.
- `OdooGateway` ya define `read_records()` y `get_model_metadata()` como frontera estrecha.

## Objetivo

Implementar en el addon endpoints/server handlers internos y acotados para obtener metadata de un modelo delegado y releer registros exactos mediante ORM bajo la identidad firmada, respetando ACL, record rules, field restrictions y multi-company.

## Contratos que NO puedes romper

- `OdooGateway` no se convierte en método genérico;
- delegación M2-01/M2-02;
- shared-secret/machine-auth server-side existente;
- no `sudo()` en el camino normal del agente;
- no SQL directo.

## Debes reutilizar

- shared secret/config de M1 para autenticar el peer Assistant Service cuando aplique;
- delegation codec y scope de M2-01;
- identidad derivada por M2-02;
- modelos/serialización Odoo nativos.

## Debes implementar

### 1. Boundary de autenticación doble

Cada llamada service → Odoo debe demostrar:

1. que proviene del peer Assistant Service según el mecanismo machine-auth del proyecto; y
2. que porta una delegación válida para ese turn/user/scope.

No basta con una cookie del browser ni con enviar `uid` en JSON.

El endpoint debe verificar DB/instancia, expiración, turn, tool scope, model e IDs antes de ejecutar ORM.

### 2. Metadata acotada

Crear una operación explícita equivalente a `fields_get`/`get_model_metadata` que:

- sólo opere sobre el modelo autorizado por la delegación;
- devuelva únicamente atributos útiles y serializables (`type`, `string`, `required`, `readonly`, `relation`, selección u otros estrictamente justificados);
- aplique límites de número de fields/bytes;
- no devuelva código, métodos, contextos enormes ni metadata arbitraria;
- respete restricciones de acceso a fields del usuario efectivo.

No construir todavía `EffectiveModelSchema` completo de M5.

### 3. Relectura exacta de registros

Crear una operación explícita equivalente a `read_records` que:

- sólo acepte modelo/IDs incluidos en la delegación;
- limite cantidad de registros y fields;
- ejecute `.read(...)`/API ORM apropiada bajo el `uid` y contexto multi-company delegados;
- no use `sudo()`;
- deje que ACL, record rules y field access de Odoo sean autoritativos;
- serialice fechas, selection, many2one/x2many y tipos comunes de forma bounded y estable;
- produzca una respuesta mapeable a `RecordSnapshot` sin inventar valores.

### 4. Errores y límites

Mapear AccessError/MissingError/ValidationError y fallos de scope a errores estructurados/sanitizados. No devolver traceback al service ni distinguir detalles que permitan enumerar registros prohibidos.

Aplicar límites server-side para records, fields, request bytes y response bytes. No aceptar domains, order, offset/limit de búsqueda ni nombres de métodos.

## Fuera de scope

- `search_read` arbitrario;
- domain queries;
- writes/create/unlink;
- business actions;
- source/logs;
- ReasoningEngine;
- UI.

## Restricciones

- no `execute_kw`/`execute_method` genérico;
- no `sudo()`;
- no SQL;
- no model/id fuera del token;
- no redirecciones o endpoints dinámicos desde input del modelo;
- el token no se refleja en response/logs.

## Tests obligatorios

Con Odoo real cuando sea posible:

- lectura permitida del registro scoped → PASS;
- otro `res_id` del mismo modelo fuera del scope → DENY;
- otro modelo → DENY;
- tool scope incorrecto → DENY;
- delegación expirada/tampered → DENY;
- field no existente → error controlado;
- exceso de fields/records/bytes → rechazo;
- ORM corre como el usuario delegado, no como admin/public;
- smoke de metadata bounded;
- comprobar ausencia de `sudo(`, `execute_kw`, `execute_method` y SQL en el camino implementado;
- suite/lint/type-check.

## Acceptance criteria

- existen sólo las dos capacidades read/metadata necesarias;
- cualquier lectura está limitada por delegación y permisos Odoo reales;
- no hay acceso genérico a métodos/domains;
- payloads y errores son bounded/sanitizados;
- los handlers pueden ser consumidos por un adapter futuro de `OdooGateway`;
- tests verdes.

## Antes de editar

1. Inspecciona la API correcta de Odoo 18 para crear/usar un env con el uid delegado **sin sudo**.
2. Resume cómo se verificará machine-auth + delegación.
3. Señala cómo se evitará que metadata/field access filtre fields restringidos.

## Después

1. Ejecuta tests Odoo y Python.
2. Informa rutas/handlers finales y límites elegidos.
3. Demuestra una lectura permitida y una denegada por scope/permisos.
4. No avances a M2-04.
