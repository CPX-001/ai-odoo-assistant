# ADR-018 — Activación explícita de Codex por base Odoo

## Estado

Accepted

## Contexto

ADR-016 mantiene un único `CODEX_HOME` privado bajo el `data_dir` de la instalación y
Codex sigue siendo propietario de las credenciales. Esa decisión permite que una sesión
de ChatGPT sobreviva a reinicios e incluso a cambios de base mientras se conserve el
mismo `data_dir`.

Sin embargo, reutilizar automáticamente esa sesión desde cualquier base nueva hace que
el Assistant parezca operativo antes de que un administrador haya conectado
explícitamente esa base. Además, la UI podía cargar historial y policy mientras todavía
estaba comprobando autenticación.

## Decisión

La credencial continúa siendo installation-scoped y provider-owned, pero cada base Odoo
debe activar explícitamente su uso mediante el parámetro no secreto
`odoo_ai_assistant.codex_connection_enabled`.

El lifecycle efectivo es:

```text
abrir Assistant
    -> comprobar runtime + activación de la base + account/read
    -> no autenticado: mostrar sólo el gate de conexión
    -> autenticado: cargar contexto, historial y policy
    -> permitir turns
```

Una base recién instalada se inicializa explícitamente con la activación deshabilitada
y se considera `not_authenticated` aunque el `CODEX_HOME` compartido ya contenga una
sesión válida. Un administrador debe pulsar `Connect with ChatGPT`. Si Codex ya reconoce
una sesión, la activación termina inmediatamente; si no, se usa el device-code flow
existente.

Para no romper bases actualizadas desde versiones anteriores a ADR-018, la ausencia del
parámetro se interpreta como activación legacy. `post_init_hook` escribe `false` sólo en
instalaciones nuevas; a partir de ese momento el valor queda explícito por base.

El servidor valida el mismo gate antes de persistir un turn. La UI no es autoridad.

La cuenta sigue gestionándose con las RPC oficiales de Codex (`account/read`,
`account/login/start`, `account/logout`, `account/rateLimits/read`). Odoo no copia,
parsea ni persiste tokens en PostgreSQL. El nuevo parámetro sólo expresa consentimiento
de esa base para usar la identidad Codex existente.

## Consecuencias

- una base nueva no carga historial ni composer del Assistant antes de conectarse;
- Settings y el panel muestran el mismo estado de activación;
- el executable override configurado por base se respeta también en el status del panel;
- upgrades de bases ya conectadas no fuerzan un logout/relogin sólo por introducir el gate;
- una instalación puede conservar una sesión Codex en disco sin activarla
  automáticamente en nuevas bases;
- `logout` sigue siendo una operación del account lifecycle de Codex y puede invalidar
  la sesión compartida; otras bases activadas fallarán cerradas hasta reconectar;
- no se modifica el layout de ADR-016 ni se crea un credential store por base.

## Alternativas consideradas

### `CODEX_HOME` separado por base

Rechazada por ahora. Garantizaría aislamiento completo, pero duplicaría sesiones,
complicaría upgrades y cambiaría una invariante de persistencia de ADR-016 sin necesidad
para resolver el onboarding.

### Confiar sólo en el estado del frontend

Rechazada. Un RPC directo podría persistir turns antes de autenticarse.

### Reutilizar automáticamente cualquier sesión encontrada en una base nueva

Rechazada. Evita un click pero contradice el requisito de conexión explícita para una
base nueva.

## Referencias

- `docs/adr/ADR-016-embedded-odoo-runtime.md`
- `docs/codex/CODEX_AUTH.md`
- `addons/odoo_ai_assistant/services/runtime_account.py`
