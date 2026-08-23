"""Revision-aware diagnostics wiring for M7 hot log-provider changes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from odoo_ai.adapters.diagnostics_runtime import (
    RuntimeDiagnosticsService as BaseRuntimeDiagnosticsService,
)
from odoo_ai.adapters.diagnostics_runtime import _log_provider_from_env
from odoo_ai.adapters.odoo_http import OdooGatewayFactory, OdooGatewaySettings
from odoo_ai.application import DiagnosticsError
from odoo_ai.contracts import (
    LogCapabilityState,
    LogEvidence,
    LogSearchRequest,
    LogTestDiagnostics,
    TracebackRequest,
)
from odoo_ai.ports import LogProvider, OdooInstanceGateway
from odoo_ai.runtime.configuration import (
    RuntimeConfigurationError,
    current_runtime_config_revision,
)
from odoo_ai.storage import DatabaseSettings


class ConfiguredRuntimeDiagnosticsService(BaseRuntimeDiagnosticsService):
    """Refresh only the bounded log provider when M7 config revision advances."""

    def __init__(
        self,
        *,
        inventory_gateway_loader: Callable[[], OdooInstanceGateway],
        database_settings: DatabaseSettings,
        log_provider: LogProvider | None,
        log_provider_name: str | None,
        unresolved_log_state: LogCapabilityState = LogCapabilityState.NOT_FOUND,
    ) -> None:
        super().__init__(
            inventory_gateway_loader=inventory_gateway_loader,
            database_settings=database_settings,
            log_provider=log_provider,
            log_provider_name=log_provider_name,
            unresolved_log_state=unresolved_log_state,
        )
        self._configuration_revision = 0
        self._configuration_lock = asyncio.Lock()

    @classmethod
    def from_env(cls) -> ConfiguredRuntimeDiagnosticsService:
        settings = DatabaseSettings.from_env()

        def inventory_gateway() -> OdooInstanceGateway:
            return OdooGatewayFactory(OdooGatewaySettings.from_env()).for_instance()

        provider, provider_name, state = _log_provider_from_env()
        result = cls(
            inventory_gateway_loader=inventory_gateway,
            database_settings=settings,
            log_provider=provider,
            log_provider_name=provider_name,
            unresolved_log_state=state,
        )
        result._configuration_revision = current_runtime_config_revision()
        return result

    async def test_logs(self, request: LogSearchRequest) -> LogTestDiagnostics:
        await self._refresh_log_provider()
        return await super().test_logs(request)

    async def read_traceback(self, request: TracebackRequest) -> LogEvidence:
        await self._refresh_log_provider()
        return await super().read_traceback(request)

    async def _refresh_log_provider(self) -> None:
        try:
            revision = await asyncio.to_thread(current_runtime_config_revision)
        except RuntimeConfigurationError as error:
            raise DiagnosticsError(error.code, error.status_code) from None
        if revision == self._configuration_revision:
            return
        async with self._configuration_lock:
            try:
                revision = await asyncio.to_thread(current_runtime_config_revision)
                if revision == self._configuration_revision:
                    return
                provider, provider_name, state = await asyncio.to_thread(
                    _log_provider_from_env
                )
            except RuntimeConfigurationError as error:
                raise DiagnosticsError(error.code, error.status_code) from None
            self._log_provider = provider
            self._log_provider_name = provider_name
            self._unresolved_log_state = state
            self._configuration_revision = revision
