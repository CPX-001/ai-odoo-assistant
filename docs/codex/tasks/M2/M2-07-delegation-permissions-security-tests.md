# M2-07 — Hardening de delegación y permisos reales

## Contexto

- Requiere M2-06 verde.
- Esta task no añade features de usuario. Endurece y demuestra las propiedades de seguridad del flujo M2 con Odoo real.
- `tests/AGENTS.md` exige especial atención a record rules, restricted fields, multi-company y expiración/replay de delegación.

## Objetivo

Demostrar mediante tests de seguridad que manipular contexto/delegación no permite leer datos fuera de los permisos reales del usuario, y cerrar cualquier bypass encontrado sin ampliar el scope funcional de M2.

## Contratos que NO puedes romper

- current-user semantics;
- no `sudo()`;
- no SQL Odoo;
- delegation scope de M2;
- `OdooGateway` read/metadata-only;
- browser sin secretos/identidad confiada.

## Debes implementar / verificar

### 1. Token y scope

Cubrir al menos:

- firma alterada;
- expiración;
- versión inválida;
- wrong turn id;
- wrong DB/instance binding;
- tool no autorizada;
- modelo distinto;
- id distinto;
- fields/record count fuera de límites;
- claims duplicados/malformed cuando el codec pueda recibirlos.

### 2. Identidad del browser

Intentos de enviar/modificar:

- `uid`;
- `company_id`;
- `allowed_company_ids`;
- groups/roles;
- display name del registro.

No deben cambiar la identidad efectiva ni evitar la relectura ORM.

### 3. ACL y record rules

Crear usuarios/fixtures Odoo 18 realistas y demostrar:

- un usuario con acceso lee el registro scoped;
- un usuario sin ACL no lo lee;
- una record rule que excluye el registro produce deny sanitizado;
- no se puede distinguir “no existe” de “existe pero no tienes acceso” cuando hacerlo filtraría información.

### 4. Restricted fields

Encontrar un field estándar con restricción de grupo o crear un fixture de test apropiado sin contaminar producto. Demostrar que pedir un field no accesible no lo devuelve bajo la delegación de un usuario que carece del grupo.

No resolverlo filtrando manualmente con una lista hardcodeada si Odoo ya ofrece checks de field access.

### 5. Multi-company

Con dos compañías y un usuario de alcance limitado:

- company B no puede inyectarse desde JS;
- token de company A no amplía acceso a registros de B;
- allowed companies sólo contiene el conjunto efectivo autorizado;
- cambiar company claims rompe la firma o se rechaza por policy.

### 6. Replay

Aplicar la política del Source of Truth. Si M2 permite replay de lectura dentro del TTL, demostrar que:

- sólo reproduce exactamente la misma capacidad read-only scoped;
- no puede cambiar tool/model/id/company/turn;
- tras expirar se rechaza;
- este comportamiento queda documentado como aceptable únicamente para reads idempotentes.

Si el Source of Truth exige single-use, implementar el mecanismo mínimo correcto y testear consumo/replay. No anticipar approvals de M6.

### 7. Secret hygiene

Buscar en responses, traces y logs de tests que no aparezcan:

- shared secret;
- token completo;
- cookies/session ids;
- raw authorization headers;
- prompts/messages dentro de `trace_event`.

## Fuera de scope

- nuevas tools;
- UX nueva;
- source/logs;
- Codex;
- writes/approvals.

## Tests obligatorios

Además de la matriz anterior:

- suite de integration Odoo con usuarios no-admin;
- service adapter/API tests;
- boundary scans para `sudo(`, `execute_kw`, `execute_method` y SQL Odoo en paths M2;
- Ruff/mypy;
- addon install/upgrade smoke.

## Acceptance criteria

- ningún caso de tampering permite ampliar scope;
- ACL, record rules, field restrictions y multi-company son efectivos;
- identidad del browser nunca es autoritativa;
- replay cumple una política explícita y testeada;
- no se filtran credenciales;
- no se añaden features fuera de M2;
- tests verdes.

## Antes de editar

1. Diseña la matriz de usuarios/compañías/records y enumérala brevemente.
2. Señala qué field restringido real usarás y por qué prueba field access de verdad.
3. Confirma la política de replay del Source of Truth.

## Después

1. Entrega tabla PASS/FAIL por categoría.
2. Lista cualquier bug de seguridad corregido.
3. Si queda un riesgo aceptado, documenta alcance y razón concretos.
4. No avances a M2-08.
