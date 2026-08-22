# M3-08 — JournalLogProvider, tracebacks y redactor común

## Contexto

- Requiere M3-07 verde.
- `JournalLogProvider` sólo aplica cuando Odoo usa una unit detectada/configurada y el service tiene permisos.
- La prohibición de shell libre es para el agente; un adapter puede invocar una herramienta fija del host si el command shape está cerrado y nunca recibe shell text del modelo.

## Objetivo

Implementar `JournalLogProvider` y cerrar operaciones equivalentes a `logs.search` / `logs.read_traceback` con fingerprinting, agrupación y redacción compartida.

## Contratos que NO puedes romper

- unit de journald resuelta server-side;
- no `shell=True`;
- no comando libre;
- no argumentos `journalctl` arbitrarios desde usuario/modelo;
- `LogProvider` sigue siendo portable a providers futuros.

## Debes reutilizar

- `LogProvider`;
- redacción de M3-07;
- capability/deployment config;
- subprocess runner seguro existente si el repo ya tiene uno; si no, crear uno mínimo local al adapter.

## Debes implementar

### 1. JournalLogProvider

Construir una invocación fija equivalente a:
- unit exacta resuelta;
- since/until bounded;
- formato determinista;
- output cap;
- timeout.

Pasar argumentos como lista, nunca string de shell.

Manejar:
- `journalctl` no disponible;
- unit no encontrada;
- permiso denegado;
- timeout;
- output truncado.

### 2. Traceback parser

Detectar bloques Python/Odoo:
- inicio `Traceback (most recent call last):`;
- frames;
- excepción final;
- contexto acotado.

Generar fingerprint estable basado en estructura útil y evitando timestamps/IDs volátiles cuando sea razonable.

Agrupar repeticiones por fingerprint.

### 3. `logs.search`

Normalizar File/Journal a la misma salida:
- excerpt;
- provider;
- rango;
- fingerprint;
- correlation;
- truncation metadata.

### 4. `logs.read_traceback`

Sólo aceptar una ref/fingerprint obtenida por provider/search:
- recuperar bloque acotado;
- no aceptar “lee cualquier fichero/unit”;
- volver a aplicar caps/redactor.

### 5. Redactor común

Cubrir al menos:
- bearer/API tokens;
- passwords/secrets por claves conocidas;
- URLs con credentials;
- shared secret de tests;
- patrones configurados del producto.

Evitar sobre-redactar IDs/nombres normales cuando sea posible.

## Fuera de scope

- Docker logs;
- Odoo.sh;
- OpenTelemetry;
- correlación perfecta record↔trace;
- prompt injection handling de M4 más allá de tratar source/log como datos no confiables.

## Restricciones

- no shell;
- no command template libre;
- no ingest completo;
- no output sin redacción;
- correlation temporal debe marcarse `temporal_inference`.

## Tests obligatorios

- command argv exacto sin shell;
- unit maliciosa/input no puede inyectar flags/comandos;
- timeout;
- no permission;
- journal fixture;
- traceback multiline;
- traceback repetido grouping;
- fingerprint estable;
- secret redaction;
- `read_traceback` con ref manipulada → reject;
- File provider regression.

## Acceptance criteria

- JournalLogProvider cumple el mismo contract;
- `logs.search` y `logs.read_traceback` son provider-agnostic;
- tracebacks quedan fingerprinted/grouped;
- no existe una superficie de shell indirecta.

## Antes de editar

1. Explica command construction.
2. Define fingerprint algorithm a alto nivel.
3. Lista patrones de redacción.

## Después

1. Demuestra argv sin shell.
2. Demuestra búsqueda + traceback + fingerprint.
3. Ejecuta tests.
4. No avances a M3-09.
