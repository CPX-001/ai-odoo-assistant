"""Generate the consolidated ADR-014 amendment to the product Source of Truth."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "Odoo_AI_Assistant_Source_of_Truth_v1.1.pdf"

NAVY = colors.HexColor("#14213D")
BLUE = colors.HexColor("#2563EB")
CYAN = colors.HexColor("#0E7490")
INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#667085")
LINE = colors.HexColor("#D0D5DD")
PALE_BLUE = colors.HexColor("#EFF6FF")
PALE_CYAN = colors.HexColor("#ECFEFF")
PALE_GRAY = colors.HexColor("#F8FAFC")
PALE_AMBER = colors.HexColor("#FFFBEB")
WHITE = colors.white


def _register_fonts() -> tuple[str, str, str]:
    regular = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    mono = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    if regular.exists() and bold.exists() and mono.exists():
        pdfmetrics.registerFont(TTFont("SourceSans", regular))
        pdfmetrics.registerFont(TTFont("SourceSans-Bold", bold))
        pdfmetrics.registerFont(TTFont("SourceMono", mono))
        return "SourceSans", "SourceSans-Bold", "SourceMono"
    return "Helvetica", "Helvetica-Bold", "Courier"


FONT, FONT_BOLD, FONT_MONO = _register_fonts()


class SourceDocument(BaseDocTemplate):
    def __init__(self, filename: str) -> None:
        super().__init__(
            filename,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=22 * mm,
            bottomMargin=20 * mm,
            title="Odoo AI Assistant - Source of Truth v1.1",
            author="Odoo AI Assistant project",
            subject="ADR-014, agente unificado, autoridad host-side y runtime Odoo dinámico",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="content",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="main", frames=[frame], onPage=_page))


def _page(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 11 * mm, width, 11 * mm, fill=1, stroke=0)
    canvas.setFont(FONT_BOLD, 8)
    canvas.setFillColor(WHITE)
    canvas.drawString(20 * mm, height - 7 * mm, "ODOO AI ASSISTANT - SOURCE OF TRUTH v1.1")
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 13 * mm, width - 20 * mm, 13 * mm)
    canvas.setFont(FONT, 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 8.5 * mm, "24 de agosto de 2026 - ADR-014")
    canvas.drawRightString(width - 20 * mm, 8.5 * mm, f"Pagina {document.page}")
    canvas.restoreState()


styles = getSampleStyleSheet()
TITLE = ParagraphStyle(
    "Title",
    parent=styles["Title"],
    fontName=FONT_BOLD,
    fontSize=27,
    leading=32,
    textColor=NAVY,
    alignment=TA_LEFT,
    spaceAfter=8 * mm,
)
SUBTITLE = ParagraphStyle(
    "Subtitle",
    parent=styles["Normal"],
    fontName=FONT,
    fontSize=13,
    leading=19,
    textColor=CYAN,
    spaceAfter=7 * mm,
)
H1 = ParagraphStyle(
    "H1",
    parent=styles["Heading1"],
    fontName=FONT_BOLD,
    fontSize=18,
    leading=23,
    textColor=NAVY,
    spaceBefore=3 * mm,
    spaceAfter=4 * mm,
    keepWithNext=True,
)
H2 = ParagraphStyle(
    "H2",
    parent=styles["Heading2"],
    fontName=FONT_BOLD,
    fontSize=12.5,
    leading=17,
    textColor=BLUE,
    spaceBefore=3 * mm,
    spaceAfter=2 * mm,
    keepWithNext=True,
)
BODY = ParagraphStyle(
    "Body",
    parent=styles["BodyText"],
    fontName=FONT,
    fontSize=9.4,
    leading=14,
    textColor=INK,
    alignment=TA_LEFT,
    spaceAfter=2.4 * mm,
)
BULLET = ParagraphStyle(
    "Bullet",
    parent=BODY,
    leftIndent=5 * mm,
    firstLineIndent=-3.5 * mm,
    spaceAfter=1.4 * mm,
)
SMALL = ParagraphStyle(
    "Small",
    parent=BODY,
    fontSize=8.2,
    leading=11.5,
    textColor=MUTED,
)
TABLE_HEAD = ParagraphStyle(
    "TableHead",
    parent=SMALL,
    fontName=FONT_BOLD,
    textColor=WHITE,
    alignment=TA_LEFT,
)
TABLE_BODY = ParagraphStyle(
    "TableBody",
    parent=SMALL,
    textColor=INK,
)
CODE = ParagraphStyle(
    "Code",
    parent=BODY,
    fontName=FONT_MONO,
    fontSize=7.7,
    leading=11,
    textColor=NAVY,
    backColor=PALE_GRAY,
    borderColor=LINE,
    borderWidth=0.6,
    borderPadding=8,
    spaceBefore=2 * mm,
    spaceAfter=4 * mm,
)
CALLOUT = ParagraphStyle(
    "Callout",
    parent=BODY,
    fontSize=10,
    leading=15,
    textColor=NAVY,
    backColor=PALE_BLUE,
    borderColor=BLUE,
    borderWidth=0.8,
    borderPadding=10,
    spaceBefore=2 * mm,
    spaceAfter=5 * mm,
)


def p(text: str, style=BODY) -> Paragraph:
    return Paragraph(text, style)


def bullet(text: str) -> Paragraph:
    return p(f"- {text}", BULLET)


def heading(number: str, title: str) -> Paragraph:
    return p(f"{number}. {title}", H1)


def subheading(title: str) -> Paragraph:
    return p(title, H2)


def table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[p(value, TABLE_HEAD) for value in headers]]
    data.extend([[p(value, TABLE_BODY) for value in row] for row in rows])
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE_GRAY]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return result


def story() -> list[object]:
    flow: list[object] = []
    flow.extend(
        [
            Spacer(1, 15 * mm),
            p("ODOO AI ASSISTANT", SMALL),
            p("Source of Truth v1.1", TITLE),
            p(
                "Agente unificado con autoridad host-side, autonomia por riesgo y descubrimiento dinamico de la instancia Odoo",
                SUBTITLE,
            ),
            p(
                "ESTADO: ENMIENDA ARQUITECTONICA APROBADA PARA IMPLEMENTACION",
                CALLOUT,
            ),
            Spacer(1, 4 * mm),
            table(
                ["Campo", "Valor"],
                [
                    ["Version", "1.1"],
                    ["Fecha de corte", "24-08-2026"],
                    ["Decision", "ADR-014 - agente unificado con autoridad host-side"],
                    ["Plataforma inicial", "Odoo 18 Community, Linux self-hosted, PostgreSQL"],
                    ["Alcance", "Sustituye las invariantes de routing, autonomia y approval de v1.0 que entren en conflicto"],
                    ["Continuidad", "Las secciones no modificadas de v1.0 permanecen vigentes"],
                ],
                [43 * mm, 125 * mm],
            ),
            Spacer(1, 8 * mm),
            p(
                "Objetivo rector: permitir que una peticion funcional compleja se resuelva con datos reales de la instalacion y con la minima friccion compatible con una autoridad determinista fuera del LLM.",
                CALLOUT,
            ),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("0", "Control de cambios"),
            p(
                "Este documento es la revision normativa v1.1 del Source of Truth. Integra ADR-014 y prevalece sobre v1.0 en routing, planificacion, politica de confirmacion, riesgo agregado, resolucion de datos, limites anti-loop y semantica del flujo comercial. Mantiene las invariantes de seguridad, deployment adaptable, persistencia separada, retrieval y compatibilidad que no se modifican.",
            ),
            table(
                ["Tema", "v1.0", "Decision v1.1"],
                [
                    ["Routing", "Workflows GENERAL/QUERY/HOW_TO/EXPLAIN/ACTION", "Un unico AgentTurnService; metadata interna no excluyente"],
                    ["Autoridad", "Approval explicita cuando corresponde", "LLM solo propone; host decide policy, autorizacion y commit"],
                    ["Confirmacion", "Centrada en cada approval", "Autoejecucion acotada o una confirmacion por plan"],
                    ["Riesgo", "Etiqueta low/medium/high por preview", "Agregado por maximo, blast radius, efecto y atomicidad"],
                    ["Modelos", "Runtime schemas", "Busqueda explicita del registry, incluidos OCA/terceros/custom"],
                    ["Datos ausentes", "Autocontexto general", "Orden obligatorio y sintesis solo autorizada"],
                    ["Delete", "Pospuesto/deshabilitado", "Un registro, siempre protected, con preview y ACL unlink"],
                ],
                [34 * mm, 55 * mm, 79 * mm],
            ),
            subheading("Invariantes no negociables"),
            bullet("La identidad efectiva, companias, ACL, record rules y schema Odoo son autoritativos."),
            bullet("El Assistant Service nunca usa SQL directo contra la DB productiva de Odoo."),
            bullet("No existe sudo(), shell libre, SQL/Python arbitrario ni execute_method generico para el agente."),
            bullet("Codex no puede aprobar, autorizar, hacer commit ni ampliar capabilities."),
            bullet("Los schemas concretos son datos runtime; no hay clases por major, modulo o proveedor."),
            bullet("Todo efecto conserva proposal, preview, autorizacion host-side, commit, verificacion y audit."),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("1", "Arquitectura y autoridad"),
            p(
                "El modelo es un componente de razonamiento no confiable para autoridad. Puede elegir tools registradas y proponer argumentos y dependencias. AgentTurnService normaliza la propuesta; el Policy Engine y el addon Odoo deciden si existe capacidad, permiso, riesgo aceptable y autoridad de ejecucion.",
            ),
            p(
                "Odoo addon -> Assistant Service -> Evidence / Tools / Reasoning",
                CODE,
            ),
            table(
                ["Boundary", "Responsabilidad autoritativa", "No puede delegar al LLM"],
                [
                    ["Browser/Owl", "UX, contexto de navegacion no autoritativo y decision del usuario", "Identidad, payload ejecutable, secrets"],
                    ["Addon Odoo", "Identidad, registry, ORM, ACL, record rules, defaults, business handlers", "sudo, metodos dinamicos, confianza en user_id de JS"],
                    ["Assistant Service", "Planes, policy, riesgo, persistencia, autorizacion, executor y audit", "SQL a Odoo o autoridad basada en texto"],
                    ["ReasoningEngine", "Comprension, lecturas necesarias y plan candidato", "Approval, commit, riesgo declarado, shell o tools no registradas"],
                ],
                [32 * mm, 69 * mm, 67 * mm],
            ),
            subheading("Flujo de un turn"),
            p(
                "1. Odoo deriva actor, base, companias, pantalla, conversacion y capas de policy.<br/>"
                "2. Codex usa solo tools registradas de lectura y preview.<br/>"
                "3. AgentTurnService valida tools, argumentos, dependencias y correspondencia exacta con previews.<br/>"
                "4. Odoo revalida schema, ACL, record rules, referencias y preconditions con su=False.<br/>"
                "5. El Policy Engine deriva metadata, riesgo agregado y policy efectiva.<br/>"
                "6. El host responde, pregunta, autoautoriza, solicita una confirmacion o rechaza.<br/>"
                "7. El executor realiza cada commit y verifica receipts bajo el usuario real.<br/>"
                "8. La respuesta solo puede afirmar resultados respaldados por receipts verificados.",
                CODE,
            ),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("2", "Agente unificado sin categorias"),
            p(
                "Se eliminan /v1/chat/route, ChatRoute, el enum de workflow del chat y los selectores visibles. Una peticion puede combinar busqueda, schema, consultas, previews y varios efectos sin quedar limitada a una sola clase. Las capacidades M2-M7 se reutilizan como componentes, no como workflows excluyentes.",
            ),
            subheading("Metadata derivada por el host"),
            table(
                ["Campo", "Significado"],
                [
                    ["needs_read", "El turn uso o requiere evidencia de registros/agregados"],
                    ["needs_schema", "El turn inspecciono schema/model catalog/defaults"],
                    ["needs_write", "Existe al menos una preview de efecto"],
                    ["needs_business_action", "Existe una accion tipada/versionada"],
                    ["has_external_effect", "El efecto se propaga fuera de Odoo"],
                    ["has_irreversible_effect", "No existe rollback real suficiente"],
                    ["is_atomic", "El plan completo tiene una frontera transaccional demostrada"],
                    ["estimated_blast_radius", "Registros/modelos/companias acotados por specs host-side"],
                ],
                [54 * mm, 114 * mm],
            ),
            p(
                "Esta metadata orienta policy, observabilidad y UX. No selecciona un workflow ni acepta valores suministrados por el LLM.",
                CALLOUT,
            ),
            subheading("Contrato candidato"),
            bullet("answer_markdown, confidence y assumptions para la respuesta."),
            bullet("clarification_question solo si no hay pasos ejecutables."),
            bullet("steps ordenados con step_id, tool_name, argumentos y dependencias previas."),
            bullet("Sin campos de riesgo, approval, authority, receipt ni estado de commit."),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("3", "Contexto Odoo y modelos dinamicos"),
            p(
                "El alcance funcional no se fija por los modulos instalados durante el desarrollo. El addon obtiene hechos de la base activa y el registry real. La lista inicial de hasta 32 modelos visibles solo mejora el primer paso; no es una allowlist estatica.",
            ),
            p(
                "pista inicial -> odoo.search_models -> modelo runtime -> schema efectivo -> read/preview",
                CODE,
            ),
            subheading("Revalidacion obligatoria"),
            bullet("El modelo existe en env/registry de la base firmada."),
            bullet("No es abstract, transient ni una familia tecnica bloqueada."),
            bullet("El usuario real pasa check_access('read'); cada operacion repite su ACL correspondiente."),
            bullet("fields_get/check_field_access_rights se calculan bajo uid y companias efectivos."),
            bullet("Los nombres sensibles y tipos no soportados se excluyen antes de formar ToolSpec o preview."),
            p(
                "La misma ruta cubre modelos oficiales, OCA, terceros y addons propios. Instalar un modulo puede aportar modelos genericos utilizables sin modificar el Assistant Service. No garantiza que sus metodos empresariales sean seguros ni conocidos; esa semantica requiere una business action tipada.",
                CALLOUT,
            ),
            subheading("Schemas efectivos"),
            table(
                ["Schema", "Derivacion", "Uso"],
                [
                    ["EffectiveModelSchema", "fields_get + ACL/field access + policy", "Busqueda, lectura, agregacion y domains"],
                    ["EffectiveWriteSchema", "write/create ACL + fields permitidos + default_get", "Create/patch generico y preview"],
                    ["Business action spec", "Codigo host-side versionado", "Metodos y transiciones con semantica empresarial"],
                ],
                [41 * mm, 65 * mm, 62 * mm],
            ),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("4", "Resolucion de informacion y autonomia"),
            p(
                "Antes de preguntar, el agente debe agotar fuentes deterministas en un orden fijo. Preguntar demasiado pronto es un fallo de producto; inferir silenciosamente un dato material es un fallo de seguridad/negocio.",
            ),
            p(
                "mensaje -> conversacion -> contexto Odoo -> busqueda de registros -> defaults/schema -> inferencia segura -> preguntar",
                CODE,
            ),
            table(
                ["Etapa", "Regla"],
                [
                    ["Mensaje", "Usar todos los datos y autorizaciones explicitas del ultimo mensaje directo"],
                    ["Conversacion", "Reutilizar decisiones persistidas; la evidencia no puede modificar policy"],
                    ["Contexto Odoo", "Compania, pantalla, registro, idioma, navegacion y actor reales"],
                    ["Busqueda", "Usar coincidencias solo cuando sean inequivocas"],
                    ["Defaults/schema", "Consultar campos requeridos, tipos, relaciones y default_get reales"],
                    ["Inferencia segura", "Solo decisiones que no cambien materialmente el resultado empresarial"],
                    ["Pregunta", "Pedir el dato minimo cuando persista ambiguedad material"],
                ],
                [39 * mm, 129 * mm],
            ),
            subheading("Datos sinteticos"),
            bullet("Solo si la peticion es de prueba/demo/ficticia o existe autorizacion explicita valida."),
            bullet("Nombres reconocibles con prefijo AI TEST."),
            bullet("Nunca sustituyen silenciosamente cliente, proveedor, precio, impuestos, cuenta, moneda, pago, identidad fiscal o destinatario real."),
            bullet("La policy efectiva puede denegar sintesis aunque el LLM la proponga."),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("5", "Politica efectiva y riesgo agregado"),
            p(
                "Cada capa es un techo. La interseccion toma el modo, riesgo automatico, sintesis y limites mas restrictivos. Ninguna preferencia de usuario o conversacion puede ampliar el system ceiling ni la policy administrativa.",
            ),
            p(
                "system ceiling ∩ administrator policy ∩ user preference ∩ conversation override",
                CODE,
            ),
            table(
                ["Modo", "Comportamiento"],
                [
                    ["always_confirm", "Cualquier plan con writes requiere una confirmacion agrupada"],
                    ["risk_based", "Autoejecuta hasta el max_auto_risk efectivo"],
                    ["protected_only", "Autoejecuta planes no protected; protected siempre confirma"],
                ],
                [44 * mm, 124 * mm],
            ),
            subheading("Calculo del plan"),
            bullet("El riesgo final es como minimo el maximo riesgo de sus pasos."),
            bullet("Blast radius considera registros, modelos y companias; no cuenta solo llamadas."),
            bullet("Una ejecucion con varios writes no atomicos sube un nivel, hasta high."),
            bullet("Una business action transaccional usa el riesgo del flujo completo, sin penalizacion por subpasos internos."),
            bullet("Cualquier efecto irreversible o externo convierte el plan en protected."),
            bullet("Mas de 12 writes o alcance no acotable se rechaza, divide o exige precision."),
            table(
                ["Nivel", "Criterio orientativo"],
                [
                    ["low", "Efecto local reversible, normalmente un modelo y hasta tres registros"],
                    ["moderate", "Relacionados multiples o transicion empresarial reversible"],
                    ["high", "Efecto relevante, varios modelos o ejecucion no atomica"],
                    ["protected", "Irreversible, contable publicado, pago o comunicacion externa"],
                ],
                [38 * mm, 130 * mm],
            ),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("6", "Tools y semantica Odoo"),
            table(
                ["Familia", "Limite", "Riesgo base"],
                [
                    ["record_create", "1 registro, hasta 16 campos scalar/many2one", "low"],
                    ["record_patch", "1 registro, hasta 16 campos scalar/many2one", "low"],
                    ["record_archive", "1 registro, reversible", "moderate"],
                    ["record_delete", "1 registro, ACL unlink, preview de impacto", "protected"],
                    ["business action", "Spec y handler tipados/versionados", "Riesgo propio del flujo"],
                ],
                [44 * mm, 83 * mm, 41 * mm],
            ),
            p(
                "El ORM generico no acepta x2many command lists, metodos, context arbitrario, domains libres, SQL ni Python. Modelos tecnicos, seguridad, credenciales, configuracion critica y campos sensibles permanecen bloqueados aunque el usuario tenga ACL.",
            ),
            subheading("sale.order.build_flow.v1"),
            table(
                ["Final", "Resultado", "Riesgo"],
                [
                    ["quotation", "Presupuesto borrador", "low"],
                    ["sale_order", "Presupuesto creado y confirmado", "moderate"],
                    ["invoice_draft", "Pedido confirmado y factura borrador", "high"],
                ],
                [42 * mm, 88 * mm, 38 * mm],
            ),
            bullet("'Crear un presupuesto' termina en quotation."),
            bullet("'Crear un presupuesto y validarlo/confirmarlo' termina normalmente en sale_order."),
            bullet("invoice_draft solo cuando se solicita factura o la intencion completa lo exige claramente."),
            bullet("Contabilizar, pagar, enviar o comunicar requiere una nueva accion protected."),
            p(
                "El handler usa metodos Odoo especificos en una transaccion atomica y bajo el usuario real. La dependencia account es explicita. En prueba autorizada puede resolver o crear partner/producto AI TEST; nunca genera una factura implicitamente al validar el presupuesto.",
                CALLOUT,
            ),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("7", "Planes, API y persistencia"),
            table(
                ["Endpoint", "Responsabilidad"],
                [
                    ["POST /v1/agent/turn", "Generar, reconciliar, evaluar y persistir un plan"],
                    ["POST /v1/agent/plans/{id}/decision", "Aprobar/rechazar el plan completo como el actor real"],
                    ["POST /v1/agent/plans/{id}/execute", "Ejecutar un plan ya autorizado desde Odoo"],
                    ["GET /v1/agent/plans/{id}", "Estado, pasos sanitizados y receipts"],
                ],
                [70 * mm, 98 * mm],
            ),
            p(
                "planning -> awaiting_confirmation | authorized -> executing -> completed | partial | failed",
                CODE,
            ),
            bullet("rejected y expired son estados terminales adicionales."),
            bullet("Cada step persiste tool/revision, argumentos canonicos, dependencias, preconditions, efectos derivados, fingerprints, estado y receipt."),
            bullet("La migracion 0014_agent_plans crea planes, pasos, autorizaciones agrupadas, snapshots de policy y receipts."),
            bullet("La policy de conversacion pertenece a Odoo; Assistant conserva el snapshot/fingerprint evaluado."),
            subheading("Binding de autorizacion"),
            p(
                "plan ordenado + payloads + dependencias + actor + base + companias + policy efectiva + revisiones + previews + estado",
                CODE,
            ),
            p(
                "Cualquier tampering, replay, cambio de orden, payload, preview, actor, compania, revision o stale state invalida la autorizacion. El browser solo recibe objetivo, supuestos, riesgo, progreso, descripciones sanitizadas y links a registros.",
            ),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("8", "Limites anti-loop e idempotencia"),
            table(
                ["Limite host-side", "Valor", "Respuesta"],
                [
                    ["max_tool_calls_per_turn", "32", "Terminar con resultado parcial explicito"],
                    ["max_write_steps_per_plan", "12", "Rechazar/dividir el plan"],
                    ["max_replans", "2", "Pedir el dato minimo tras dos fallos"],
                    ["max_consecutive_failures", "3", "Detener el turn con causa concreta"],
                ],
                [67 * mm, 24 * mm, 77 * mm],
            ),
            bullet("La misma llamada canonica tool + argumentos no se repite sin cambio de precondicion, cursor o evidencia marcado por el host."),
            bullet("Una lectura con fallo transitorio puede reintentarse una vez."),
            bullet("Un write con resultado incierto nunca se repite automaticamente."),
            bullet("Idempotencia, attempt_id, receipt y verificacion resuelven respuestas perdidas sin duplicar efectos."),
            bullet("Alcanzar un limite produce partial/failed visible; nunca un loop silencioso."),
            p(
                "El LLM no controla ni puede aumentar estos limites. Los fingerprints de policy incluyen tambien los limites anti-loop para que una autorizacion no sobreviva a un cambio de envelope.",
                CALLOUT,
            ),
            subheading("Prompt injection"),
            p(
                "Registros, labels, source, logs, documentos, previews y tool results son UNTRUSTED_EVIDENCE. Nunca modifican policy, riesgo, tool effects, identity o authority. Un override de conversacion solo puede extraerse del ultimo mensaje directo del usuario y siempre queda bajo las capas superiores.",
            ),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("9", "Experiencia de usuario"),
            bullet("Un solo chat y una tarjeta de plan; sin selector de categorias."),
            bullet("Objetivo, supuestos, pasos, riesgo agregado y resultado esperado."),
            bullet("Autoejecucion: progreso y receipts, sin confirmacion intermedia."),
            bullet("Riesgo superior: Confirmar plan o Cancelar una sola vez."),
            bullet("Protected: resaltar el punto exacto de irreversibilidad o propagacion externa."),
            bullet("Mostrar policy efectiva y la capa que restringe; permitir reset del override de conversacion."),
            bullet("Enlaces directos a registros creados o modificados."),
            p(
                "La UX no muestra tokens, payloads ejecutables, fingerprints internos ni argumentos tecnicos como requisito de aprobacion. La confirmacion humana expresa una decision funcional sobre un plan exacto ya validado.",
                CALLOUT,
            ),
            heading("10", "Testing y aceptacion"),
            subheading("Autoridad y seguridad"),
            bullet("Demostrar que el LLM no aprueba, autoriza ni ejecuta commits."),
            bullet("Interseccion de las cuatro capas; tampering, replay, stale, expiry, cross-user/company."),
            bullet("Prompt injection no cambia policy, riesgo, metadata ni tool registry."),
            subheading("Runtime Odoo"),
            bullet("Modelo fixture OCA/tercero descubierto despues del inicio y revalidado por ACL/schema."),
            bullet("CRUD generico, archive/delete y sale build flow bajo ACL/record rules reales."),
            bullet("default_get efectivo; datos sinteticos solo con autorizacion."),
            subheading("E2E comercial"),
            bullet("Contacto, patch y quotation low sin confirmacion cuando la policy lo permite."),
            bullet("Validar presupuesto termina en sale_order; factura solo por peticion explicita."),
            bullet("Un solo approval para un plan encadenado superior; pagos/posting/comunicacion se detienen."),
            PageBreak(),
        ]
    )

    flow.extend(
        [
            heading("11", "Criterios de entrega"),
            table(
                ["Gate", "Evidencia requerida"],
                [
                    ["Codigo", "Pytest, Ruff y mypy verdes; boundaries sin imports inversos"],
                    ["DB", "Migracion PostgreSQL real 0013 -> 0014 y downgrade estructural revisado"],
                    ["Odoo", "Install/upgrade 18.0.8.0.0, tests addon y ACL reales"],
                    ["UI", "Tests JS/Odoo, Chromium y revision visual del plan/policy"],
                    ["Reasoning", "Prueba real Codex con modelos runtime y receipts verificados"],
                    ["Documentacion", "ADR-014, arquitectura, operacion y PDF v1.1 renderizado"],
                ],
                [42 * mm, 126 * mm],
            ),
            subheading("Compatibilidad"),
            p(
                "El baseline garantizado sigue siendo Odoo 18 Community self-hosted. La generalidad de modelos se obtiene del registry/schema runtime, no de prometer compatibilidad automatica con cualquier hosting o major. Odoo 19/futuros deben pasar la misma contract suite; application no incorpora checks por major salvo ADR.",
            ),
            subheading("Alcance inicial"),
            p(
                "La primera entrega cubre consultas y operaciones genericas acotadas sobre modelos elegibles y el flujo comercial descrito. Procesos especializados adicionales se incorporan como business actions tipadas. Policies configuran autonomia, pero nunca crean capabilities, saltan ACL o convierten una operacion desconocida en segura.",
            ),
            p(
                "Decision final: evidencia determinista primero; LLM despues. Autonomia funcional no significa autoridad del modelo.",
                CALLOUT,
            ),
            heading("12", "Referencias normativas"),
            bullet("ADR-014 - Agente unificado con autoridad host-side."),
            bullet("Source of Truth v1.0 - secciones no modificadas por esta revision."),
            bullet("docs/ARCHITECTURE.md y docs/DEPLOYMENT_CONFIG.md."),
            bullet("docs/UNIFIED_AGENT_RUNTIME.md."),
            bullet("Contratos ejecutables en service/src/odoo_ai/contracts."),
            bullet("Odoo 18 ORM y Security, y Codex App Server adapter aislado."),
        ]
    )
    return flow


def main() -> None:
    document = SourceDocument(str(OUTPUT))
    document.build(story())
    print(OUTPUT)


if __name__ == "__main__":
    main()
