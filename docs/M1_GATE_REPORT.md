# M1 Gate Report

Fecha: 2026-08-21  
Entorno: Ubuntu 24.04 WSL2 con systemd real, PostgreSQL 16, Odoo 18 Community y
units/DBs/directorios disposable.

El host permite una verificación equivalente al perfil Linux self-hosted del Source
of Truth: el service se ejecutó realmente bajo systemd como usuario no-root, el
bootstrap completo instaló su propio runtime y levantó un cluster PostgreSQL
disposable, y el addon se instaló/actualizó/desinstaló en Odoo 18 real.

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| tests | PASS | DB real: `installer/smoke/m1_gate.sh quality` → 84 passed, 5 perfiles host-gated ejecutados aparte |
| lint | PASS | `ruff check service/src installer tests addons` |
| type-check | PASS | `mypy service/src` |
| health | PASS | perfiles `systemd`, `odoo` y `alternate`; `/health` HTTP 200 `status=ok` |
| admin status | PASS | autenticación por secret, payload sanitizado y estado DB/Alembic; tests API y smokes host |
| systemd/non-root/loopback | PASS | `installer/smoke/m1_gate.sh systemd`; PID con UID no-root y socket loopback |
| Assistant DB migrations | PASS | `installer/smoke/m1_gate.sh postgres`; Alembic en `head`, upgrade con backup previo |
| Assistant role → Odoo DB denied | PASS | cluster disposable, reglas HBA acotadas y conexión real rechazada |
| bootstrap first run | PASS | `installer/smoke/m1_gate.sh alternate`; crea runtime/config/secret/DB/migrations/unit |
| bootstrap second run | PASS | mismo perfil; sin release/config/DB/unit/restart nuevos |
| conventional deployment | PASS | perfiles reales `postgres`, `systemd` y `odoo` sobre Ubuntu/Odoo DEV |
| non-conventional deployment | PASS | perfil `alternate`: sin config/unit Odoo detectables, usuario explícito, unit `acme-*`, paths con espacios, puertos/nombres DB y directorios custom |
| Odoo health visibility | PASS | `installer/smoke/m1_gate.sh odoo`; healthy, error controlado al parar service y browser sin acceso directo |
| upgrade/rollback | PASS | runtime build versionado, restart por cambio de release/config, rollback atómico probado, Alembic forward-only y runbook en `docs/OPERATIONS_M1.md` |

## Perfiles ejecutados

- calidad con Assistant DB real: 84 passed, 5 skipped host-gated, ruff PASS, mypy PASS;
- PostgreSQL disposable: 1 passed;
- instalación/upgrade/rollback real del runtime: 1 passed;
- systemd real: 1 passed;
- addon Odoo real: 1 passed;
- bootstrap completo no convencional: 1 passed.

Los perfiles host-gated limpian sus units, DBs, roles y directorios temporales. La
prueba Odoo confirmó además que desinstalar el addon no elimina una Assistant DB
separada.

## Boundaries y portabilidad

- `contracts`, `core` y `application` siguen libres de FastAPI, Odoo, Codex y
  storage concreto; las comprobaciones están en la contract suite.
- No existen tools genéricas `execute_kw`/`execute_method`, `sudo()` Odoo, shell
  libre ni SQL del Assistant Service contra la DB productiva de Odoo.
- Las rutas convencionales del bootstrap son hints sustituibles. El perfil alterno
  pasó sólo con configuración/overrides; no se editó código ni templates durante el
  smoke.
- M2 no se implementó: no hay chat, delegación, ORM tools, source/log providers ni
  reasoning loop activos.

## Riesgos no bloqueantes

- El bootstrap instala dependencias Python desde el source disponible; wheelhouse,
  package OS y upgrades offline pertenecen al hardening operativo posterior.
- `managed-local` y `external-existing` son los perfiles M1; otros supervisores y
  providers de deployment se incorporarán mediante adapters, sin cambiar
  application contracts.
- `installer/odoo18_install.sh` es exclusivamente un fixture DEV para preparar Odoo
  18/WSL y no es el instalador de producto.

## Veredicto

Se cumplen los ocho acceptance criteria de M1-10 con ejecución real, no por
inferencia.

**M1 GATE: PASS**
