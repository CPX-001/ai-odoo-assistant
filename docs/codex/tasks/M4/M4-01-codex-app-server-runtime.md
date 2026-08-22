# M4-01 — Runtime seguro de Codex App Server

## Contexto

- Requiere **M3 GATE: PASS**.
- M0 ya fijó `ReasoningEngine`; M4 debe implementar un adapter, no rediseñar el port por detalles del proveedor.
- La especificación del producto exige Codex App Server como primer engine y aislamiento de tools/autoridad.
- El protocolo de Codex evoluciona. Antes de programar, inspecciona la versión real disponible y la documentación/schema oficial actual.

## Objetivo

Crear la foundation de runtime/protocolo para lanzar y controlar Codex App Server desde el Assistant Service con lifecycle, límites y configuración seguros, demostrando un handshake real y uno fake reproducible; todavía sin ejecutar un product turn.

## Contratos que NO puedes romper

- `service/src/odoo_ai/ports/reasoning.py`;
- boundaries de `service/AGENTS.md`;
- configuración/deployment como datos, no paths hardcodeados;
- Codex no recibe autoridad Odoo ni acceso directo al source del host.

## Antes de decidir implementación

Contrasta dos opciones contra el runtime actual:

1. SDK Python oficial de Codex, si la release disponible expone el lifecycle/protocolo necesario y conserva App Server como boundary;
2. cliente mínimo propio del protocolo stdio, si el SDK no expone todavía las capabilities necesarias.

Prefiere la opción oficial estable cuando satisfaga el scope. No copies un cliente JSON-RPC grande ni vendorizaciones innecesarias. Documenta versión/protocolo probado y por qué se eligió la opción.

## Debes implementar

### Configuración runtime

Una configuración tipada equivalente a:

- executable/runtime seleccionado;
- `CODEX_HOME` o equivalente, sólo si debe ser override explícito;
- model opcional, sin fijar un modelo concreto como contrato;
- startup/handshake timeout;
- turn timeout futuro;
- cwd aislado del Assistant;
- límites de frame/stdout/stderr;
- flags/capabilities de protocolo necesarias.

No copies auth tokens a campos propios. La autenticación la gestiona Codex bajo el usuario del Assistant; el producto sólo detecta disponibilidad/estado sanitizado.

### Lifecycle

- lanzar sin `shell=True` ni command string libre;
- argv construido por el adapter;
- stdio/transport oficial soportado;
- `initialize` + `initialized` o secuencia exacta de la versión probada;
- request IDs correlacionados;
- lectura/escritura bounded;
- stderr capturado con ring buffer sanitizado y cap;
- timeout, EOF inesperado y proceso muerto producen errores tipados;
- cierre graceful y kill bounded como fallback;
- no dejar subprocess huérfanos.

### Aislamiento inicial

Para los futuros threads de M4 prepara una política que permita fijar:

- thread efímero;
- approval policy sin escalaciones interactivas;
- sandbox de sólo lectura o más restrictivo según la API real;
- cwd disposable/aislado que no sea el checkout del producto ni addons roots;
- sin workspace roots de Odoo/source.

No habilites dynamic tools todavía; sólo deja la capability negociable para M4-04.

### Probe

Añade un probe estrecho que pueda distinguir, como mínimo:

- runtime no configurado/no encontrado;
- proceso arranca pero handshake falla;
- App Server compatible/usable;
- auth/model no se debe inferir como usable hasta que exista evidencia real suficiente.

El probe no debe ejecutar una consulta LLM cara cada vez que `/admin/status` se abra.

## Fuera de scope

- implementar `ReasoningEngine.run_turn`;
- dynamic tools;
- ToolExecutor;
- UI;
- login OAuth desde Odoo;
- copiar `auth.json` o credenciales;
- source/log/Odoo tools.

## Tests obligatorios

- fake App Server: handshake correcto;
- response ID incorrecto/mensaje malformado → fail closed;
- frame/stdout oversized → rechazo;
- startup timeout y EOF;
- stderr nunca se devuelve crudo a APIs;
- shutdown termina el proceso;
- argv no usa shell;
- cwd es configurable/aislado;
- probe sanitiza paths/auth;
- smoke real `codex app-server`/SDK equivalente en el host DEV si está disponible;
- suite, Ruff y mypy.

## Acceptance criteria

- existe una boundary de runtime Codex pequeña y sustituible;
- el protocolo concreto queda confinado a `adapters`/infra;
- el proceso se controla con límites y cleanup;
- no hay auth/token/path sensible en logs o contratos públicos;
- hay evidencia de handshake real cuando el host lo permite;
- no se ha ejecutado todavía un product turn.

## Después

1. Informa versión/protocolo/SDK realmente probados.
2. Muestra lifecycle y comando/argv efectivo sin secretos.
3. Indica dónde espera Codex su auth y qué usuario ejecuta el proceso.
4. No avances a M4-02.
