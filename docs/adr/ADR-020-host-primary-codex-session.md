# ADR-020 — Sesión Codex principal del host compartida por la instalación

## Estado

Accepted

## Contexto

ADR-016 hizo del App Server un subprocess efímero y mantuvo las credenciales bajo
propiedad de Codex. ADR-018 añadió después una activación no secreta por base y un
flujo de conexión/logout dentro de Odoo.

La instalación ya dispone de una sesión principal de Codex. Pedir que cada base la
active o que un administrador vuelva a autenticarse desde Odoo duplica un lifecycle
que pertenece al host/proveedor. Además, un logout iniciado desde una base muta la
misma identidad de proveedor que usan todas las demás.

## Decisión

La instalación consume automáticamente una única sesión Codex principal configurada
por el host. El proceso Odoo recibe su ubicación mediante la variable de entorno
absoluta `CODEX_HOME`. Si no se configura, se conserva como fallback compatible el
home administrado `<data_dir>/odoo_ai_assistant/codex`.

No existe activación por base de datos. El parámetro legado
`odoo_ai_assistant.codex_connection_enabled` se ignora y deja de escribirse. La UI y
los RPC del producto sólo consultan y refrescan estado sanitizado; no inician device
login, no desconectan la cuenta y no exponen códigos o tokens. La autenticación se
administra fuera de Odoo mediante el lifecycle normal de Codex en el host.

Todos los usuarios y bases atendidos por esa instalación comparten la identidad y
cuota del proveedor. Esto no comparte autoridad de negocio: cada turn captura el
usuario, compañías y contexto Odoo originarios, y las capacidades se resuelven y
ejecutan con ese Environment efectivo, `su=False`, ACLs, record rules, field access,
policy y aprobación vigentes.

`CODEX_HOME` es configuración del proceso/servicio, nunca un valor de PostgreSQL. Su
contenido continúa siendo provider-owned. Odoo no parsea ni copia tokens a campos,
parámetros, prompts, eventos públicos, logs o repositorio. Los homes temporales de un
turn pueden recibir sólo la copia credential-only ya definida por ADR-016; no se
convierten en almacén persistente ni en autoridad.

## Consecuencias

- una base nueva usa la sesión válida del host sin login o consentimiento duplicado;
- reiniciar Odoo conserva la sesión mientras el `CODEX_HOME` configurado siga válido;
- cambiar/autenticar/cerrar la sesión principal es una operación de host que afecta a
  toda la instalación;
- Settings y Diagnostics muestran estado y remediación, pero no administran tokens;
- el usuario del servicio Odoo necesita acceso de lectura/escritura al provider home;
- una sesión ausente, inválida o inaccesible bloquea turns de forma fail-closed;
- el executable override por base sigue siendo configuración no secreta independiente;
- ADR-018 queda superseded.

## Alternativas consideradas

### Activación por base sin credenciales separadas

Rechazada. Añade estado y UI duplicados sin aislar realmente identidad, cuota ni
logout del proveedor.

### Un `CODEX_HOME` y login por cada usuario Odoo

Rechazada para el producto actual. Confunde identidad de proveedor con autoridad de
negocio, multiplica credenciales y contradice la sesión principal compartida de la
instalación.

### Copiar `auth.json` al `data_dir`

Rechazada. Duplica material secreto y puede divergir durante refresh/rotación. Odoo
debe apuntar al store original administrado por Codex.

## Referencias

- `docs/adr/ADR-016-embedded-odoo-runtime.md`
- `docs/adr/ADR-018-database-scoped-codex-activation.md`
- `docs/codex/CODEX_AUTH.md`
- `addons/odoo_ai_assistant/runtime/paths.py`
- `addons/odoo_ai_assistant/services/runtime_account.py`
