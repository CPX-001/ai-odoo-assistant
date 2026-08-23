"""Bounded log providers and deployment resolution."""

from odoo_ai.logs.common import LogProviderError, LogRedactor
from odoo_ai.logs.configured import (
    journal_unit_override_from_env,
    log_file_override_from_env,
)
from odoo_ai.logs.file import FileLogLimits, FileLogProvider
from odoo_ai.logs.journal import (
    JOURNAL_UNIT_ENV,
    JournalCommandResult,
    JournalLogLimits,
    JournalLogProvider,
    JournalUnitOrigin,
    JournalUnitSelection,
    ResolvedJournalUnit,
    SubprocessJournalRunner,
    resolve_journal_unit,
)
from odoo_ai.logs.resolution import (
    LOG_FILE_ENV,
    LogFileOrigin,
    LogFileResolution,
    LogFileSelection,
    ResolvedLogFile,
    resolve_log_file,
)

__all__ = [
    "LOG_FILE_ENV",
    "JOURNAL_UNIT_ENV",
    "FileLogLimits",
    "FileLogProvider",
    "LogFileOrigin",
    "LogFileResolution",
    "LogFileSelection",
    "LogProviderError",
    "LogRedactor",
    "JournalCommandResult",
    "JournalLogLimits",
    "JournalLogProvider",
    "JournalUnitOrigin",
    "JournalUnitSelection",
    "ResolvedJournalUnit",
    "SubprocessJournalRunner",
    "ResolvedLogFile",
    "log_file_override_from_env",
    "journal_unit_override_from_env",
    "resolve_log_file",
    "resolve_journal_unit",
]
