# M7-03 — Runtime config validation y apply

## Contexto

- Requiere M7-01 y M7-02 verdes.
- Settings sólo es presentación/persistencia de intención administrativa; el Assistant Service debe validar de nuevo cualquier override que afecte su runtime.
- Los cambios host-owned siguen fuera de esta task.

## Objetivo

Implementar el boundary server-side que valida, persiste y aplica configuración `ADMIN_MUTABLE` de forma atómica y recuperable, conservando el último snapshot válido si el nuevo override falla.

## Debes implementar

### Admin config API/boundary

Crear rutas/handlers internos estrechos, machine-authenticated y admin-triggered, para como mínimo:

- obtener snapshot sanitizado de configuración efectiva;
- validar un conjunto bounded de overrides;
- aplicar/persistir overrides válidos;
- devolver revision/fingerprint de configuración y resultado sanitizado.

El cliente nunca envía una clave arbitraria. Sólo keys registradas por M7-01 pueden llegar al handler correspondiente.

### Persistencia y atomicidad

Usar una persistencia apropiada al Assistant para overrides operativos (DB/config store existente o equivalente) con:

- revision monotónica/fingerprint;
- update atómico;
- last-known-good/effective state;
- rechazo sin modificación si cualquier valor no pasa validación;
- audit event sanitizado de cambio administrativo.

No almacenar secrets completos aunque una referencia de secret forme parte del snapshot.

### Aplicación/reload

- aplicar en caliente sólo settings cuyo descriptor lo permita;
- marcar `restart_required`/`setup_required` cuando no pueda aplicarse en caliente;
- nunca reiniciar systemd ni procesos arbitrarios desde el modelo/LLM/browser;
- revalidar roots/providers contra envelope real antes de activar;
- invalidar/recrear providers/indexes sólo de forma explícita y segura cuando el setting lo requiera.

### Concurrencia

Dos admins cambiando la config no deben pisarse silenciosamente: usa revision/precondition o equivalente y devuelve conflicto actionable.

## Debes reutilizar

- config contracts M7-01;
- Assistant DB/storage/migrations patterns existentes;
- machine auth existente;
- status/readiness/capability calculation existente;
- source/log/knowledge provider factories actuales.

## Fuera de scope

- root/systemd control;
- secret rotation;
- DB provisioning;
- arbitrary env mutation;
- generic config dictionaries enviadas por Codex;
- M8.

## Restricciones

- sólo admin/Odoo server inicia cambios;
- ReasoningEngine no recibe admin config tools;
- browser no contacta Assistant directamente;
- paths y providers fail closed;
- no borrar índices/datos antes de que la nueva config sea validada;
- no degradar silenciosamente a un default diferente del seleccionado.

## Tests obligatorios

- GET snapshot sanitizado;
- valid → apply → effective revision cambia;
- invalid → rollback/no change;
- stale revision/concurrent update falla cerrado;
- host-only key y unknown key rechazadas;
- path/provider escape rechazado;
- secret/canary no aparece en response/audit;
- hot reload sólo para descriptors compatibles;
- restart/setup-required representado sin ejecutar privilegios;
- readiness refleja config rota/válida correctamente;
- PostgreSQL migration fresh/upgrade si aplica;
- suite, Ruff y mypy.

## Acceptance criteria

- Settings puede aplicar cambios operativos sin editar env/código manualmente;
- un override inválido no rompe el último runtime válido;
- config revision/provenance quedan trazables;
- ningún cambio host-privileged se ejecuta desde Odoo.

## Después

1. Documenta endpoints y state transition final.
2. Lista qué settings aplican hot y cuáles requieren setup/restart.
3. Ejecuta regresión combinada M7-01..03 antes de cerrar Goal A.
