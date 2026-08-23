# M7-01 — Config contracts, ownership y provenance

## Contexto

- Requiere M6 GATE: PASS.
- `docs/DEPLOYMENT_CONFIG.md` ya fija la UX `Autodetectar → mostrar → override → validar → guardar` y la prioridad de fuentes.
- Hoy existe configuración dispersa entre bootstrap/env/`ir.config_parameter`; M7 necesita una representación estable antes de crear UI.

## Objetivo

Definir un contrato único y tipado para describir configuración efectiva del Assistant, su provenance y quién puede modificar cada valor, sin mover secretos ni autoridad de host a Odoo.

## Debes implementar

### Taxonomía de configuración

Introducir descriptors/contratos que distingan al menos:

- `HOST_ONLY`: provisioning, secret contents/secret creation, PostgreSQL admin, systemd/root-level setup, bind de seguridad y otros valores que Odoo no puede aplicar;
- `ADMIN_MUTABLE`: overrides operativos que un system admin puede cambiar sin ampliar privilegios del proceso;
- `DISCOVERED`: facts detectados/runtime que pueden mostrarse pero no falsificarse como autoridad superior.

Cada setting debe poder expresar de forma bounded:

- key estable/versionada;
- tipo y constraints;
- valor efectivo sanitizado;
- provenance (`explicit_override`, `runtime`, `supervisor`, `config`, `hint`, `unknown` o equivalente);
- ownership/mutability;
- sensibilidad/redaction policy;
- restart/reload requirement si aplica;
- estado de validación/capability;
- mensaje admin-safe de por qué no es editable cuando corresponda.

### Envelope de paths/providers

Los valores que representen roots, log providers, units o paths no pueden convertir Settings en una ampliación arbitraria del filesystem. Diseña el contrato para que setup/bootstrap pueda declarar candidates/envelopes permitidos y que la capa admin sólo seleccione/ajuste dentro de ellos.

No convertir paths detectados en secretos, pero tampoco exponer paths físicos al usuario no administrador o al ReasoningEngine por esta feature.

### Snapshot efectivo

Crear una representación determinista del snapshot de configuración efectiva que pueda consumir Diagnostics/Settings posteriormente. Debe distinguir `unknown` de valor vacío y conservar provenance.

## Debes reutilizar

- `InstanceProfile`/deployment discovery existentes;
- config/bootstrap y env existentes;
- `ir.config_parameter` sólo donde ya sea apropiado para Odoo-side non-secret references;
- patterns de status/capabilities existentes.

## Fuera de scope

- UI Settings;
- endpoint de escritura de config;
- reiniciar servicios;
- rotar/generar secretos;
- policies ACTION administrables;
- soporte Odoo 19.

## Restricciones

- no `sudo()`;
- no direct Odoo SQL;
- no guardar secret contents en Odoo;
- no permitir que una configuración M7 amplíe source/log/knowledge roots fuera del envelope autorizado por setup;
- no hardcodear layout DEV;
- no version checks en `application`.

## Tests obligatorios

- clasificación host-only/admin-mutable/discovered;
- precedence/provenance determinista;
- `unknown` no se confunde con empty/default;
- secret/ref se redacta correctamente;
- path fuera del envelope se rechaza;
- symlink/escape no amplía containment;
- snapshot estable ante orden distinto de inputs;
- layout no-default;
- suite, Ruff y mypy.

## Acceptance criteria

- existe un único contrato usable por Settings/Diagnostics para configuración efectiva;
- cada valor conoce su authority/provenance y mutability;
- ningún secret content ni privilegio host se mueve a Odoo;
- los futuros overrides no pueden ampliar filesystem authority arbitrariamente.

## Después

1. Documenta la tabla final de settings/ownership/provenance que M7 pretende administrar.
2. Señala qué valores siguen requiriendo bootstrap/setup.
3. No avances a M7-02 si el boundary host/admin sigue ambiguo.
