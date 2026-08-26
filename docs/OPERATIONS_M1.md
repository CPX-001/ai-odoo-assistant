# Operación M1: instalación, upgrade y rollback

Este runbook cubre el perfil Linux self-hosted probado en M1. Las rutas y nombres de
los ejemplos son overrides, no contratos. Deben sustituirse por los facts del
deployment confirmados con `--preflight-only` y `docs/DEPLOYMENT_CONFIG.md`.

## Fresh install y segunda ejecución

Crear primero el virtualenv desde el que se ejecuta el bootstrap. Después:

```bash
sudo .venv/bin/python -m installer.bootstrap \
  --runtime-source "$PWD" \
  --odoo-user acme-odoo \
  --odoo-db-name acme_odoo \
  --install-dir /srv/acme/assistant \
  --config-dir /srv/acme/assistant-config \
  --state-dir /srv/acme/assistant-state \
  --runtime-dir /run/acme-assistant \
  --assistant-db-name acme_assistant \
  --assistant-db-role acme_assistant_role \
  --assistant-backup-dir /srv/acme/assistant-backups \
  --assistant-unit-name acme-assistant.service
```

El resultado JSON identifica `runtime_version` y `runtime_build_id`. El payload se
instala primero en `INSTALL_DIR/releases/<version>-<build>` y sólo después se activa
mediante el enlace `current`. La segunda ejecución del mismo comando debe informar
que runtime, config, DB, unit y service no cambiaron.

El modo `managed-local` requiere nombres de DB Odoo explícitos o detectados para
probar el aislamiento. En PostgreSQL remoto/administrado se usa
`--postgres-mode external-existing` y un archivo `0600` pasado mediante
`--assistant-database-url-file`; el operador provisiona previamente role y DB.

## Autenticación Codex después de instalar el addon

La operación normal ya **no** requiere entrar por terminal como usuario Odoo para
ejecutar `codex login` ni copiar `auth.json` manualmente.

1. Instalar un `codex` compatible y hacerlo visible en el `PATH` de Odoo o guardar
   el override de executable en **Settings → AI Assistant**.
2. Actualizar/instalar `odoo_ai_assistant`.
3. En **Embedded runtime**, confirmar `Codex state: ready`.
4. Pulsar **Connect with ChatGPT**.
5. Abrir la URL indicada desde cualquier navegador y escribir el device code.
6. Pulsar **Refresh account status** hasta ver `Connected`.
7. Abrir **AI Assistant Diagnostics** y comprobar `Authenticated / ready`.

El proceso de login es efímero y queda limitado por timeout. Cancelar desde Settings
hace que el proceso propietario ejecute `account/login/cancel`; no matar procesos a
mano salvo investigación de un fallo del runtime. Si Odoo se reinicia durante el
login, refrescar Settings: un intento cuyo lock ya no existe se marca interrumpido y
puede iniciarse de nuevo.

`Disconnect` usa `account/logout`; no borra la configuración del addon ni el resto de
`data_dir`.

Una sesión previa válida en el `CODEX_HOME` del addon se reconoce automáticamente.
El login manual queda sólo como recovery/debug y debe apuntar al mismo `CODEX_HOME`;
nunca pegar tokens en Odoo, logs o parámetros de configuración. Ver
`docs/codex/CODEX_AUTH.md`.

## Upgrade coordinado

1. Conservar el release/config actuales y comprobar espacio en el destino de backup.
2. Ejecutar el bootstrap desde el nuevo checkout con los mismos overrides. Usar
   `--restart-service` cuando el código tenga el mismo fingerprint/path efectivo o
   se quiera forzar el restart coordinado.
3. El bootstrap instala el release completo antes de cambiar `current`, inspecciona
   Alembic y, si una DB existente no está en `head`, crea un `pg_dump` custom `0600`
   en `--assistant-backup-dir` antes de ejecutar `upgrade head`.
4. Verificar `/health`, `/v1/admin/status`, estado systemd y diagnóstico en Odoo.
5. Actualizar el addon Odoo sólo cuando el release correspondiente ya esté healthy.

Una instalación nueva sin tabla Alembic no necesita backup. Una DB ya en `head`
tampoco. Si hay migraciones pendientes y no se configuró backup, el upgrade falla
antes de migrar.

## Rollback de runtime y config

Alembic es **forward-only en operación normal**. Nunca se ejecuta un downgrade
automático.

Si el schema actual es compatible con el release previo, restaurar primero los
overrides/config anteriores y ejecutar:

```bash
sudo .venv/bin/python -m installer.bootstrap \
  --install-dir /srv/acme/assistant \
  --runtime-source "$PWD" \
  --assistant-unit-name acme-assistant.service \
  --rollback-runtime \
  --acknowledge-schema-compatibility
```

El comando intercambia atómicamente `current`/`previous`, reinicia el service y no
toca la DB. El acknowledgement es una decisión operativa explícita, no una prueba
automática de compatibilidad.

Si el código anterior no entiende el schema nuevo, no activarlo. La recuperación es
desplegar un runtime compatible o restaurar el `pg_dump` en una DB de recuperación
separada, validar esa DB y cambiar la configuración mediante un procedimiento
operativo aprobado. No sobrescribir ni borrar automáticamente la DB original.

Un fallo mientras se construye un release elimina sólo el staging incompleto y
conserva `current`. Un fallo de migración conserva el backup y debe investigarse
antes de reiniciar. Un fallo de start deja el unit y journal disponibles para
diagnóstico; corregir config/capacidad y repetir el bootstrap.

## Uninstall y purge

Desinstalar `odoo_ai_assistant`, retirar el unit o borrar un release **no elimina** la
Assistant DB. No existe uninstall hook de purge. La eliminación de role, DB, backups
y secretos es una acción administrativa separada, destructiva y explícita, fuera
del flujo normal de uninstall/upgrade.

El `CODEX_HOME` bajo `data_dir/odoo_ai_assistant/codex` contiene estado de cuenta
administrado por Codex y también debe tratarse como secreto. No borrarlo como efecto
lateral de un upgrade. Un purge deliberado debe ejecutarse fuera de Odoo y bajo la
misma política operativa que el resto de secretos persistentes.

## Smokes reproducibles

`installer/smoke/m1_gate.sh` ofrece perfiles independientes:

```bash
installer/smoke/m1_gate.sh quality
ODOO_AI_RUN_POSTGRES_BOOTSTRAP_TEST=1 installer/smoke/m1_gate.sh postgres
ODOO_AI_RUN_RUNTIME_INSTALL_TEST=1 installer/smoke/m1_gate.sh runtime
sudo ODOO_AI_RUN_SYSTEMD_BOOTSTRAP_TEST=1 installer/smoke/m1_gate.sh systemd
sudo ODOO_AI_RUN_ODOO_PLACEHOLDER_TEST=1 installer/smoke/m1_gate.sh odoo
sudo ODOO_AI_RUN_NONDEFAULT_BOOTSTRAP_TEST=1 installer/smoke/m1_gate.sh alternate
```

`postgres` debe ejecutarse como un usuario no-root capaz de levantar un cluster
disposable. Los tres perfiles con systemd/Odoo requieren root y limpian sus units,
DBs y directorios temporales. `alternate` usa config Odoo ausente, unit sin `odoo` en
el nombre, usuario Odoo explícito, paths con espacios, nombres/puertos DB no-default
y directorios Assistant personalizados.
