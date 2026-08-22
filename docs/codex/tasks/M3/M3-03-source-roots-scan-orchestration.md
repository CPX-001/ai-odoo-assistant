# M3-03 — Roots de source y orquestación incremental

## Contexto

- Requiere M3-02 verde.
- El scanner sólo puede leer roots configurados/detectados de addons.
- Los defaults de deployment son hints, no contratos.
- M1 ya conoce parte del deployment; M2 mantiene boundaries HTTP/machine-auth estrechos.
- La lista de módulos instalados debe obtenerse determinísticamente, no inferirse del nombre de directorios.

## Objetivo

Resolver de forma segura el inventario de addons/módulos instalados y construir el lifecycle del scan incremental sobre roots explícitos, todavía usando extractores fake/stub.

## Contratos que NO puedes romper

- browser no participa en source discovery;
- no escaneo global del host;
- no SQL a Odoo;
- no `sudo()`;
- no ampliar `OdooGateway` a `execute_method`/`execute_kw` genérico;
- `application` no depende de paths concretos del cliente.

## Debes reutilizar

- discovery/config de M1;
- `docs/DEPLOYMENT_CONFIG.md`;
- machine-auth existente;
- storage M3-02;
- instance profile/capability pattern actual.

## Debes implementar

### 1. Inventario runtime mínimo

Inspecciona qué fuente server-side existe ya para versión, DB, módulos instalados y addons roots. Si falta la lista de módulos instalados, añade el boundary más estrecho posible entre Assistant Service y addon para obtener metadata de instancia.

Debe estar autenticado server-to-server, no depender de identidad del browser y no devolver datos de negocio ni métodos arbitrarios.

### 2. Resolución de roots

Aplicar esta prioridad:
1. override explícito;
2. runtime confirmado;
3. metadata de proceso/supervisor;
4. config Odoo;
5. hints convencionales.

Normalizar:
- realpath;
- existencia;
- tipo directorio;
- duplicados;
- permisos de lectura;
- roots permitidos.

Representar `NOT_FOUND`, `NO_PERMISSION` y `ERROR`; no inventar paths.

### 3. Inventario de módulos

Sobre los roots resueltos:
- localizar directorios de módulos sin ejecutar código;
- cruzar con módulos instalados;
- priorizar instalados;
- módulos disponibles-no-instalados quedan fuera del scan inicial salvo necesidad explícita posterior.

No clasificar un módulo como `custom` por estar en una carpeta llamada `custom`.

### 4. Scan orchestrator

Crear un orchestrator explícito que:
- inicia `scan_run`;
- recorre sólo módulos/roots autorizados;
- calcula fingerprint/mtime/size;
- omite ficheros sin cambios;
- invoca extractores explícitos/fakes por tipo;
- registra error parcial de forma estructurada;
- finaliza scan con métricas bounded.

No crear registry/plugin framework.

### 5. Capabilities

Actualizar snapshot/readiness para source con estados equivalentes a:
- DETECTED/operational;
- NOT_FOUND;
- NO_PERMISSION;
- ERROR.

M3 no puede marcar `FULLY_READY` mientras `reasoning_engine` siga pendiente.

## Fuera de scope

- AST/XML/CSV reales;
- source queries finales;
- logs;
- Codex;
- Settings completas de M7.

## Restricciones

- no `os.walk("/")` ni scans equivalentes;
- no seguir symlinks fuera de roots permitidos salvo root explícitamente autorizado;
- no importar addons;
- no usar nombres/path DEV como requisito;
- límites de módulos/ficheros/bytes/tiempo por scan.

## Tests obligatorios

- layout convencional;
- layout no convencional con overrides;
- root inexistente;
- root sin permisos;
- duplicate/symlink escape;
- sólo módulos instalados priorizados;
- segundo scan sin cambios no reprocesa;
- cambio de hash marca reextracción;
- suite M1/M2 sigue verde.

## Acceptance criteria

- el scanner sabe exactamente qué roots puede leer y por qué;
- un deployment no convencional funciona por configuración;
- no hay scan global ni ejecución de código Odoo;
- el scan incremental funciona con extractores fake;
- capabilities distinguen ausencia/permisos/error.

## Antes de editar

1. Resume qué datos de deployment ya existen realmente.
2. Explica cómo obtendrás módulos instalados sin SQL.
3. Lista los límites de scan propuestos.

## Después

1. Demuestra layout convencional + override no convencional.
2. Demuestra segundo scan sin reproceso.
3. Ejecuta tests.
4. No avances a M3-04.
