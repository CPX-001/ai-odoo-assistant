# Codex / ChatGPT authentication lifecycle

Estado: runtime embebido Odoo-owned. Esta página es la referencia operativa para autenticación de Codex; sustituye el provisioning manual de `auth.json` como camino normal de instalación.

## Deployment normal

Perfil soportado: Odoo 18 Community self-hosted en Linux, con el addon ejecutándose bajo la identidad Unix normal de Odoo.

1. Instalar un runtime `codex` compatible y dejarlo accesible en el `PATH` del proceso Odoo o configurar el override en **Settings → AI Assistant**.
2. Instalar/actualizar `odoo_ai_assistant`.
3. Abrir **Settings → AI Assistant → Embedded runtime** como administrador del sistema.
4. Confirmar que `Codex runtime` aparece `ready`.
5. Pulsar **Connect with ChatGPT**.
6. Odoo mostrará `verificationUrl` y `userCode` obtenidos directamente de `account/login/start` con `type=chatgptDeviceCode`.
7. Abrir la página desde cualquier navegador/máquina, iniciar sesión y escribir el código.
8. Volver a Odoo y usar **Refresh account status**. El estado pasa a `Connected` cuando Codex emite `account/login/completed` y `account/read` confirma la cuenta.

No se configura una API key central ni se usa `/v1/responses`. Codex gestiona los tokens y su refresh.

## Persistencia y propiedad del secreto

El layout sigue siendo:

```text
<odoo data_dir>/odoo_ai_assistant/
    codex/      # CODEX_HOME persistente, privado
    runtime/    # estado no secreto del login/locks
    cache/
    source/
```

`codex/` usa permisos `0700`. Para mantener el aislamiento existente de los product turns, el runtime de autenticación fija la opción oficial `cli_auth_credentials_store="file"`; Codex sigue siendo propietario del formato y contenido de `auth.json`, que queda bajo ese `CODEX_HOME`. El addon no parsea, fabrica ni refresca access/refresh tokens. No se guardan tokens, contenido de `auth.json` ni credenciales ChatGPT en PostgreSQL, `ir.config_parameter`, logs, prompts, eventos de turn ni respuestas RPC.

El estado del device flow (`verificationUrl`, `userCode`, estado terminal y códigos de error saneados) vive temporalmente en `runtime/codex_auth/` con permisos privados. `loginId`, PID y metadatos internos nunca forman parte del payload público de Settings.

## Lifecycle del device login

`account/login/start` inicia en Codex una tarea interna que debe seguir viva hasta que OpenAI autorice, cancele o expire el código. Por eso una RPC Odoo no puede iniciar el App Server y cerrarlo inmediatamente.

La implementación usa un **worker efímero de autenticación**, no un sidecar permanente:

```text
Odoo worker A
  -> lock filesystem no bloqueante
  -> spawn account_worker.py (argv fijo, shell=False)
      -> CODEX_HOME persistente del addon
      -> codex app-server --stdio --strict-config
         --config mcp_servers={} --config cli_auth_credentials_store="file"
      -> initialize / initialized
      -> account/login/start(chatgptDeviceCode)
      -> escribe estado saneado + verificationUrl/userCode
      -> espera account/login/completed
      -> Codex persiste sus propias credenciales
      -> account/read confirma la cuenta
      -> cierra App Server y libera lock
```

El lock file descriptor se hereda al worker efímero. Esto hace que el estado activo sea válido entre workers Odoo y evita dos logins simultáneos sin globals, Redis ni afinidad de RPC.

### Multiproceso y restart

- `workers=0`: funciona igual; la petición HTTP no queda bloqueada esperando al usuario.
- multiproceso: cualquier worker puede leer el estado o pedir cancelación; ninguno necesita memoria del worker inicial.
- restart de Odoo: si el supervisor conserva el helper, éste puede completar; si el restart mata el cgroup, el lock del kernel se libera. El siguiente refresh detecta un `pending` sin owner, lo marca `codex_login_interrupted` y permite iniciar de nuevo.
- intento duplicado: si el lock está ocupado se devuelve el intento activo, no se crea otro App Server.
- timeout: el helper cancela best-effort mediante `account/login/cancel`, marca `timed_out` y termina.
- cancelación: Odoo crea un marker privado; el helper propietario ejecuta `account/login/cancel` en el mismo App Server que creó el `loginId` y termina.

No hay threads daemon, estado global de Python, petición HTTP larga, shell, systemd adicional, Redis/Celery ni proceso de auth permanente.

## Account status y logout

Settings y diagnostics consultan el `CODEX_HOME` persistente mediante App Server efímero:

- `account/read` → `runtime unavailable`, `not authenticated`, `authenticated` o `authentication error`;
- `account/login/start` / `account/login/completed` → `login pending` y resultado terminal;
- `account/logout` → Codex elimina su propia sesión;
- `account/rateLimits/read` → diagnóstico opcional de ventanas reales.

Sólo se muestran datos acotados que Codex entregue de forma explícita: modo de auth, email de la cuenta y `planType`. No se muestran account/workspace IDs.

Rate limits no usa etiquetas hardcodeadas “5h” o “weekly”. Se renderizan los buckets disponibles a partir de `limitId`, `limitName`, `usedPercent`, `windowDurationMins` y `resetsAt`. Si la API no existe o falla, la autenticación sigue siendo válida y la sección de uso se omite.

## Aislamiento de product turns

El lifecycle de auth no cambia la autoridad del reasoning ni la seguridad de los turns.

```text
CODEX_HOME persistente del addon
  -> copia credential-only existente
  -> HOME temporal aislado
  -> Codex App Server efímero
  -> thread efímero / sandbox read-only / MCP vacío
  -> HOME eliminado
```

El runtime actual de product turns sigue copiando únicamente `auth.json` como bytes, con límite de tamaño y modo `0600`; no copia `config.toml`, MCPs, plugins ni skills. La autenticación gestionada desde Odoo escribe en el mismo `CODEX_HOME`, por lo que instalaciones que ya posean una sesión válida continúan funcionando sin relogin.

Diagnostics comprueba adicionalmente que una cuenta que Codex declara autenticada siga siendo visible desde el HOME aislado de product turns. Así puede distinguir `Authenticated / ready` de `Authenticated / unusable`. Esto hace visible una futura incompatibilidad si Codex cambia de credential store antes de adaptar el materializado credential-only.

## Seguridad y RPC

Las operaciones Connect / Refresh / Open login page / Cancel / Disconnect requieren `base.group_system`.

Los paths de executable/runtime se resuelven server-side; el browser no envía `loginId`, PID ni paths. Los subprocess usan argv fijo, `shell=False`, entorno allowlisted, límites de frame/stdout/stderr, timeouts y TERM/KILL acotados. El estado de auth usa directorios `0700`, ficheros `0600`, reemplazo atómico y rechazo de symlinks.

`verificationUrl` sólo se acepta por HTTPS en dominios OpenAI/ChatGPT antes de exponer el action URL. Los errores de App Server se reducen a códigos internos; stdout/stderr y mensajes provider no se devuelven al browser ni se registran como detalle de credenciales.

## Diagnostics y operación

En **AI Assistant Diagnostics → Embedded Codex account** se muestran:

- runtime missing/unusable;
- not connected;
- login pending;
- authentication error;
- authenticated / ready;
- authenticated / unusable;
- email/plan si Codex los proporciona;
- rate-limit windows opcionales.

Ante un login stale después de restart, refrescar Settings o Diagnostics normaliza el intento interrumpido. Ante credenciales expiradas, volver a **Connect with ChatGPT**. Ante una versión de Codex que no implemente las RPC requeridas, actualizar Codex; el addon falla cerrado con `codex_account_api_unsupported`.

## Recovery/manual auth

El login manual de Codex bajo la misma identidad Unix y apuntando al `CODEX_HOME` privado del addon queda soportado únicamente como recovery/debug. No copiar ni pegar tokens en Odoo y no introducir un segundo formato de credenciales.

Si un `codex_home` existente ya contiene una sesión que `account/read` reconoce, Settings la muestra como conectada y los product turns mantienen la compatibilidad actual. No es necesario reloguear al actualizar el addon.

## Protocolo oficial contrastado

La implementación se basa en las RPC v2 públicas actuales de Codex App Server: `account/read`, `account/login/start` (`chatgptDeviceCode`), `account/login/completed`, `account/login/cancel`, `account/logout` y, de forma opcional, `account/rateLimits/read`. No implementa OAuth contra endpoints privados de OpenAI.
