import asyncio
from datetime import UTC, datetime

from odoo_ai.contracts import (
    InstanceInventory,
    LogCorrelation,
    LogEvidence,
    LogSearchRequest,
    TimestampRange,
)
from odoo_ai.ports import LogProvider, OdooInstanceGateway


class FakeOdooInstanceGateway:
    async def get_instance_inventory(self) -> InstanceInventory:
        return InstanceInventory(
            database="customer_odoo",
            server_version="18.0",
            installed_modules=("base", "sale"),
            addons_roots=("/srv/customer/addons",),
            captured_at=datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
        )


class FakeLogProvider:
    async def search(self, request: LogSearchRequest) -> list[LogEvidence]:
        return [
            LogEvidence(
                provider="fake",
                timestamp_range=TimestampRange(
                    from_ts=request.from_ts,
                    to_ts=request.to_ts,
                ),
                excerpt="Traceback excerpt",
                traceback_fingerprint="trace-123",
                correlation=LogCorrelation.DIRECT,
            )
        ]

    async def read_traceback(
        self,
        fingerprint: str,
        *,
        max_bytes: int,
    ) -> LogEvidence | None:
        del max_bytes
        results = await self.search(
            LogSearchRequest(terms=[fingerprint], max_lines=20, max_bytes=4096)
        )
        return results[0]


async def _read_inventory(gateway: OdooInstanceGateway) -> InstanceInventory:
    return await gateway.get_instance_inventory()


async def _search_logs(provider: LogProvider) -> LogEvidence:
    results = await provider.search(
        LogSearchRequest(terms=["action_confirm"], max_lines=50, max_bytes=8192)
    )
    return results[0]


def test_odoo_instance_gateway_is_substitutable_without_business_execution() -> None:
    inventory = asyncio.run(_read_inventory(FakeOdooInstanceGateway()))

    assert inventory.database == "customer_odoo"
    assert inventory.installed_modules == ("base", "sale")
    assert not hasattr(OdooInstanceGateway, "execute_kw")
    assert not hasattr(OdooInstanceGateway, "execute_method")
    assert not hasattr(OdooInstanceGateway, "read_records")


def test_log_provider_is_substitutable_without_free_form_access() -> None:
    evidence = asyncio.run(_search_logs(FakeLogProvider()))

    assert evidence.traceback_fingerprint == "trace-123"
    assert not hasattr(LogProvider, "run_command")
