# M3-05 — XML, CSV de seguridad y consistencia incremental

## Contexto

- Requiere M3-04 verde.
- El Source of Truth exige XML y CSV de seguridad como parte del scanner estático.
- El estado runtime final puede diferir de lo declarado en XML/CSV; la evidencia debe reflejar esa limitación.

## Objetivo

Completar el scanner estático con XML y CSV de seguridad, y cerrar la consistencia incremental de altas, cambios y borrados.

## Contratos que NO puedes romper

- no ejecutar XML/Python;
- no resolver permisos efectivos desde CSV;
- runtime Odoo sigue siendo autoridad de ACL/record rules;
- paths sólo desde roots validados.

## Debes reutilizar

- parser seguro existente en el repo si lo hay;
- storage M3-02;
- orchestrator M3-03;
- fingerprints M3-04.

## Debes implementar

### 1. XML extractor

Extraer de forma acotada:
- records;
- XML ids;
- model;
- `inherit_id`;
- metadata de views;
- `xpath` relevante;
- actions;
- menus;
- groups/restricciones declaradas.

Persistir `xml_record` con pointer a fichero/líneas cuando sea posible.

No intentar calcular completamente el árbol final de herencias de vistas en M3.

### 2. Seguridad CSV

Parsear `ir.model.access.csv` u otros CSV declarados como seguridad:
- external id;
- model external id;
- group external id;
- read/write/create/unlink flags;
- path/row.

Representar estas entradas como declaraciones estáticas de source. No afirmar que son permisos efectivos del usuario.

### 3. Seguridad del parser

- XML sin resolución de entidades externas/network;
- límites de tamaño/profundidad;
- CSV con límite de columnas/filas/bytes;
- encoding/parse error sanitizado.

### 4. Consistencia incremental

Cubrir:
- fichero modificado → sustituye derivados;
- fichero borrado → elimina derivados;
- módulo desaparecido/desinstalado → no deja símbolos activos del scan actual;
- scan fallido parcial no corrompe el índice anterior válido sin una política explícita.

Definir claramente cuándo un `scan_run` se considera válido.

## Fuera de scope

- aplicar ACL declaradas;
- render final de views;
- ejecutar XPath real contra registry Odoo;
- source search API;
- logs.

## Restricciones

- no entity expansion;
- no network fetch;
- no inferir runtime security desde archivos;
- no persistir XML completo si no es necesario para retrieval.

## Tests obligatorios

- view heredada;
- action/menu;
- group;
- XML malformado;
- entity/DTD hostil;
- CSV válido;
- CSV malformado;
- stale deletion;
- scan parcial;
- límites de tamaño.

## Acceptance criteria

- XML ids y herencias fixture quedan localizables;
- ACL CSV queda indexada como declaración estática con provenance;
- parseos hostiles no salen de límites;
- el índice representa sólo el último scan válido/fingerprint vigente.

## Antes de editar

1. Explica la representación exacta de ACL CSV.
2. Define semántica de scan parcial.
3. Indica parser XML elegido y por qué.

## Después

1. Demuestra XML + CSV fixture.
2. Demuestra cleanup de fichero borrado.
3. Ejecuta tests.
4. No avances a M3-06.
