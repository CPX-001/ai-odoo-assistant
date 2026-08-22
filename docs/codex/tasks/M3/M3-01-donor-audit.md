# M3-01 — Auditoría del donor de scanner

## Contexto

- Requiere **M2 GATE: PASS**.
- El Source of Truth recomienda auditar `erpipe-org/mcp-odoo` como donor MIT para scanner/query/write safety antes de copiar código.
- La revisión debe hacerse por fichero y revisión concreta, no sólo por README/licencia root.
- M3 no adopta la arquitectura de conexión externa/MCP del donor.

## Objetivo

Auditar la implementación actual relevante del scanner de ERPipe y dejar una decisión reproducible sobre qué código, algoritmos o ideas pueden reutilizarse en M3, sin implementar todavía el scanner del producto.

## Contratos que NO puedes romper

- `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`.
- ADR-013: repo propio + reutilización selectiva.
- Objetivo de distribución comercial/propietaria.
- Boundaries actuales del monorepo.
- No modificar `contracts`/`application` para acomodar la arquitectura del donor.

## Debes reutilizar

- `docs/ARCHITECTURE.md`.
- `docs/DEPLOYMENT_CONFIG.md`.
- convenciones actuales de notices/provenance del repo, si existen.

## Debes implementar

1. Inspeccionar el estado real del repo antes de editar.
2. Revisar `erpipe-org/mcp-odoo` en una revisión/commit concreto y documentar:
   - licencia root;
   - licencia/headers de los ficheros relevantes;
   - scanner de manifests;
   - parser Python/AST;
   - XML/security CSV;
   - hashing/incremental scan;
   - helpers de símbolos/source si existen.
3. Clasificar cada pieza como:
   - `reuse_code`;
   - `adapt_algorithm`;
   - `idea_only`;
   - `do_not_use`.
4. Para cada `reuse_code`, registrar:
   - repo y commit;
   - ruta original;
   - licencia;
   - ruta destino prevista;
   - cambios necesarios;
   - notice/atribución requerida.
5. Crear un informe versionado, preferiblemente `docs/third_party/M3_ERPIPE_SCANNER_AUDIT.md` o la convención equivalente ya existente en el repo.
6. Si durante la inspección aparece drift documental trivial de estado M2/M3, puede corregirse sólo si no cambia arquitectura.

## Fuera de scope

- copiar código donor;
- implementar scanner;
- MCP;
- Codex;
- write safety;
- query helpers de M5;
- refactors generales.

## Restricciones

- No asumir que “MIT en README” cubre todos los ficheros.
- No copiar código AGPL/LGPL en esta task.
- No añadir dependencias porque las use el donor.
- No cambiar invariantes ni crear ADR salvo conflicto real.

## Tests/verificaciones obligatorias

- comprobar que el informe referencia paths/commits concretos;
- `git diff` limitado a docs/notices salvo corrección documental trivial;
- lint Markdown si existe;
- si accidentalmente se toca código, ejecutar baseline correspondiente y justificarlo.

## Acceptance criteria

- existe inventario por fichero/función reutilizable;
- la revisión está ligada a un commit concreto del donor;
- queda claro qué puede copiarse, qué sólo inspira diseño y qué se rechaza;
- no se ha implementado ningún feature de M3;
- no se ha introducido una licencia incompatible.

## Antes de editar

1. Resume M2 GATE y HEAD actual.
2. Indica el commit exacto auditado de ERPipe.
3. Señala cualquier diferencia respecto a la evaluación del Source of Truth.

## Después

1. Lista piezas aprobadas/rechazadas.
2. Indica notices necesarios.
3. Ejecuta verificaciones disponibles.
4. No avances a M3-02.
