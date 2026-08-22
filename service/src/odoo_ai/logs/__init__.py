"""Bounded log providers and deployment resolution."""

from odoo_ai.logs.common import LogRedactor
from odoo_ai.logs.file import FileLogLimits, FileLogProvider, LogProviderError
from odoo_ai.logs.resolution import (
    LOG_FILE_ENV,
    LogFileOrigin,
    LogFileResolution,
    LogFileSelection,
    ResolvedLogFile,
    log_file_override_from_env,
    resolve_log_file,
)

__all__ = [
    "LOG_FILE_ENV",
    "FileLogLimits",
    "FileLogProvider",
    "LogFileOrigin",
    "LogFileResolution",
    "LogFileSelection",
    "LogProviderError",
    "LogRedactor",
    "ResolvedLogFile",
    "log_file_override_from_env",
    "resolve_log_file",
]
