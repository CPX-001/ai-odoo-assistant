# M3-07 — FileLogProvider bounded

## Contexto

- Requiere M3-06 verde.
- FULLY_READY exige un LogProvider funcional, pero M3 seguirá `DEGRADED` por `reasoning_engine` pendiente.
- Logs se consultan bajo demanda; no se ingieren completos en Assistant DB.
- El path del log debe provenir de deployment config/resolution, nunca del usuario/modelo.

## Objetivo

Implementar `FileLogProvider` con búsqueda temporal/términos, límites estrictos, redacción y evidencia normalizada.

## Contratos que NO puedes romper

- port `LogProvider` existente de M0;
- providers reciben config resuelta, no instrucciones libres;
- no persistencia masiva de logs;
- no path arbitrario por request.

## Debes reutilizar

- deployment/logfile detectado por M1;
- capability pattern;
- `Evidence`;
- límites/config comunes;
- redactor existente si ya existe.

## Debes implementar

### 1. Config/resolution

Resolver el fichero de log con:
1. override explícito;
2. config Odoo confirmada;
3. runtime/supervisor metadata;
4. hints sólo al final.

Validar:
- fichero regular;
- readable;
- realpath permitido;
- tamaño/estrategia compatibles con los caps.

### 2. Request bounded

Soportar una forma equivalente a `LogSearchRequest` con:
- `from_ts`;
- `to_ts`;
- `terms`;
- `max_lines <= 200`;
- `max_bytes <= configured_cap`.

Validar número y longitud de términos. No aceptar regex arbitraria en M3.

### 3. Búsqueda

- buscar primero por ventana y términos relevantes;
- evitar mandar megabytes al caller;
- devolver contexto acotado alrededor de matches;
- truncar de forma explícita;
- ordenar temporalmente cuando sea determinista;
- si timestamps no se pueden parsear, declarar limitación, no inventar.

### 4. Resultado

Producir resultado normalizado/Evidence con:
- provider=`file`;
- timestamp range;
- excerpt;
- traceback fingerprint opcional;
- correlation `direct` o `temporal_inference`;
- truncation metadata;
- pointer interno seguro.

### 5. Readiness

Actualizar logs/capability distinguiendo:
- operational;
- NOT_FOUND;
- NO_PERMISSION;
- ERROR.

## Fuera de scope

- journald;
- Docker/Odoo.sh;
- ingest completo;
- tail streaming;
- log analytics general.

## Restricciones

- no path desde prompt/UI como autoridad;
- no regex libre;
- caps por líneas/bytes/tiempo;
- secretos redactados antes de cualquier salida fuera del provider boundary.

## Tests obligatorios

- ventana temporal;
- términos;
- sin match;
- truncation line/byte cap;
- fichero grande;
- unreadable/missing;
- path override no convencional;
- secret fixture;
- timestamp no parseable;
- ningún log completo se persiste.

## Acceptance criteria

- un traceback fixture puede localizarse en file log por ventana/términos;
- respuesta acotada;
- secretos del fixture no aparecen;
- readiness diferencia ausencia/permisos/error;
- no hay ingest a DB.

## Antes de editar

1. Resume el `LogProvider` contract actual.
2. Define formato(s) de timestamp soportados en M3.
3. Define caps por defecto/configurables.

## Después

1. Demuestra búsqueda real sobre fixture.
2. Demuestra redacción y truncation.
3. Ejecuta tests.
4. No avances a M3-08.
