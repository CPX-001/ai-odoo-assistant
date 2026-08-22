# M3-02 — Contratos y persistencia de source

## Contexto

- Requiere M3-01 completado.
- M1 ya proporciona PostgreSQL + SQLAlchemy + Alembic.
- M0 ya define `Evidence` y ports base; no deben reemplazarse innecesariamente.
- El Source of Truth exige `scan_run`, `source_file`, `source_symbol` y `xml_record`.

## Objetivo

Añadir el mínimo modelo ejecutable y persistencia necesaria para scans de source, sin implementar todavía extractores reales ni búsquedas de filesystem.

## Contratos que NO puedes romper

- `contracts` no depende de FastAPI, Odoo ni storage.
- `application` no depende de SQLAlchemy concreto.
- migraciones forward-only.
- Assistant DB separada; cero SQL a la DB Odoo.
- `Evidence` actual sigue siendo la unidad común de salida.

## Debes reutilizar

- engine/session/repositorios de M1;
- patrón actual de Alembic;
- `Evidence`, `InstanceProfileSummary` y contracts existentes;
- tipos y serialización ya usados por el repo.

## Debes implementar

### 1. Contratos mínimos

Inspecciona primero los contracts existentes. Añade sólo lo que falte para representar:

- `ScanRun` / estado de scan;
- `SourceFile`;
- `SourceSymbol`;
- `XmlRecord`;
- `SourceRef` o pointer estable equivalente para lectura posterior;
- estados/fingerprints necesarios.

`SourceSymbol` debe poder representar al menos:
- module;
- kind;
- model opcional;
- name;
- path lógico;
- start/end line;
- fingerprint.

No crear clases por versión Odoo.

### 2. Persistencia

Añadir sólo las tablas ausentes entre:
- `scan_run`;
- `source_file`;
- `source_symbol`;
- `xml_record`.

Índices mínimos alineados con el Source of Truth:
- scan status/start time;
- source file por module/sha/path;
- symbol por model+name/module/path;
- XML por xml_id/model.

Mantener claves/FKs suficientes para sustituir de forma segura el resultado derivado de un fichero reescaneado.

### 3. Repositorios

Crear interfaces/implementaciones pequeñas para:
- abrir/cerrar scan;
- upsert de fichero por fingerprint;
- reemplazar símbolos/XML derivados de un fichero;
- marcar/eliminar entradas stale;
- consultar por identificadores estructurales.

No crear un repository framework genérico.

### 4. Migración y lifecycle

- migration nueva desde HEAD actual;
- fresh DB → head;
- upgrade desde revisión anterior → head;
- backup/rollback operativo de M1 sigue funcionando;
- no persistir contenido completo de logs;
- no persistir copias de registros vivos Odoo.

## Fuera de scope

- parsear manifests/Python/XML/CSV;
- leer source del host;
- LogProvider concreto;
- Diagnostics;
- trigram/FTS avanzado;
- Codex.

## Restricciones

- no guardar secretos/config completa;
- no meter paths del entorno DEV como defaults de schema;
- no usar SQLite;
- no crear tablas de embeddings/vector ni otras piezas especulativas.

## Tests obligatorios

- migración desde revisión actual;
- fresh DB → head;
- repositorio: create scan, upsert file, replace symbols, stale cleanup;
- unique/index constraints;
- rollback operativo existente no se rompe;
- `pytest`, `ruff`, `mypy`;
- perfiles PostgreSQL existentes.

## Acceptance criteria

- la Assistant DB puede representar un scan incremental sin duplicados;
- un fichero cambiado puede sustituir sus símbolos/XML previos;
- no hay dependencia de Odoo/FastAPI en contracts;
- no hay feature extraction todavía;
- tests y migraciones verdes.

## Antes de editar

1. Lista migraciones/tablas existentes para no duplicar.
2. Propón el schema mínimo exacto.
3. Señala si algún contrato del Source of Truth ya existe bajo otro nombre.

## Después

1. Informa migration revision y tablas/índices finales.
2. Demuestra un replace por fingerprint.
3. Ejecuta tests.
4. No avances a M3-03.
