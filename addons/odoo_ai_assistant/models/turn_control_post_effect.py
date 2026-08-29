"""Post-effect Stop semantics: interrupt synthesis without discarding verified business effects."""

from odoo import models


class EmbeddedAssistantPostEffectStop(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    async def _continue_after_effect(
        self,
        turn,
        *,
        lease_token,
        completed,
        policy,
        registry,
        context,
        executor,
        working_items,
    ):
        try:
            return await super()._continue_after_effect(
                turn,
                lease_token=lease_token,
                completed=completed,
                policy=policy,
                registry=registry,
                context=context,
                executor=executor,
                working_items=working_items,
            )
        except Exception as error:  # noqa: BLE001 - inspect only the sanitized host error code
            if getattr(error, "code", None) != "agent_cancelled":
                raise
            # The plan has already executed and verified on this cursor. Stop should end further
            # provider synthesis, not pretend those verified effects never happened. Returning a
            # normal completed response lets the worker commit the effects and the UI expose the
            # host-declared compensation option where one exists.
            response = self._plan_response(turn, completed, policy, completed=True)
            response["answer"] = (
                "Procesamiento detenido. Los cambios que ya se habían realizado "
                "quedaron verificados en Odoo."
            )
            return response
