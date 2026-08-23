# M6-02 — Schema efectivo de escritura

## Contexto

- Requiere M6-01 verde.
- M5 ya descubre `EffectiveModelSchema` para lectura/query bajo usuario, compañías y policy actuales.
- Tener acceso de lectura a un field no implica que sea apto para ACTION.

## Objetivo

Construir una vista efectiva y bounded de qué cambios simples puede intentar el usuario sobre el target actual, combinando permisos Odoo reales, metadata runtime y la ActionPolicy de M6-01.

## Contratos que NO puedes romper

- `EffectiveModelSchema` de M5 sigue gobernando QUERY.
- No ampliar QUERY con información/capabilities de write si no la necesita.
- Odoo sigue siendo autoridad final de ACL, record rules y reglas de negocio.

## Debes reutilizar

- adapters/endpoints de metadata M5 cuando sea seguro extenderlos sin mezclar authorities;
- identidad/companies derivadas server-side;
- patrones de schema/policy revision;
- Evidence METADATA checked.

## Debes implementar

### Effective write schema

Crea un contrato sibling o extensión claramente separada que represente al menos:

- model objetivo;
- si el usuario tiene acceso de escritura al modelo en ese contexto;
- fields candidatos que además pasan ActionPolicy;
- tipo de field y restricciones mínimas necesarias para validar valores;
- readonly/required/selection/relation metadata estrictamente necesaria;
- policy revision/fingerprint;
- captured_at.

No expongas todos los fields técnicos sólo porque `fields_get` los devuelva.

### Tipos inicialmente soportados

Mantén el primer slice pequeño. Como base, permitir sólo tipos escalares sencillos cuyo valor pueda representarse y validar sin command language. Cualquier soporte para `many2one` debe ser explícito y validar el id objetivo de forma segura. Deja fuera al menos:

- one2many/many2many commands;
- binary;
- HTML salvo policy de sanitización explícita;
- reference/polymorphic libres;
- fields técnicos/sensibles denegados por policy;
- campos que requieran una mini-lengua o código.

Si el repo real ya tiene un validador de field types mejor, reutilízalo en vez de duplicar lógica.

### Autoridad real

La obtención del schema debe ocurrir bajo el usuario real y compañías efectivas, `su=False`. Debe distinguir:

- field visible/readable pero no write-eligible;
- model sin write access;
- field fuera de ActionPolicy;
- metadata desconocida/degradada.

El schema no concede por sí mismo autorización de commit; es evidencia/capability para validar proposal/preview.

### Evidence

Produce Evidence METADATA checked citable con una representación sanitizada del schema efectivo de escritura. No incluir secrets, tokens ni metadata innecesaria del servidor.

## Fuera de scope

- preview del registro;
- approval;
- write;
- UI;
- create/delete;
- business methods.

## Tests obligatorios

- usuario con read pero sin write obtiene schema no-writeable;
- field readonly/no permitido desaparece o queda marcado no elegible;
- field sensible denegado por ActionPolicy no puede entrar en proposal;
- field type no soportado se rechaza;
- multi-company conserva contexto efectivo;
- usuario distinto puede obtener schema distinto;
- metadata adversarial no altera policy ni tools;
- Evidence sólo contiene fields permitidos/sanitizados;
- M5 QUERY schema no regresa;
- suite, Ruff y mypy.

## Acceptance criteria

- un proposal sólo puede referirse a fields presentes y write-eligible en el schema efectivo actual;
- policy + metadata + permisos están separados y verificables;
- el resultado sigue sin permitir ningún write.

## Después

1. Lista los tipos soportados finalmente y por qué.
2. Documenta cualquier field type deliberadamente pospuesto.
3. No avances a M6-03 si el schema permite un valor que el preview no pueda validar determinísticamente.
