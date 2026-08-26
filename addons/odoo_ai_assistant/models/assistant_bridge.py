"""Compatibility configuration constants for the temporary sidecar settings surface.

The browser/query/action bridge that previously lived here was retired when the product
turn runtime moved to ``odoo.ai.turn`` + ``odoo.ai.embedded.runtime``. Keep only these
configuration keys while source/retrieval diagnostics still have a temporary service.
"""

from typing import Final

SERVICE_URL_PARAM: Final = "odoo_ai_assistant.service_url"
SECRET_FILE_PARAM: Final = "odoo_ai_assistant.shared_secret_file"
TURN_TIMEOUT_PARAM: Final = "odoo_ai_assistant.turn_timeout_seconds"
SERVICE_URL_ENV: Final = "ODOO_AI_SERVICE_URL"
SECRET_FILE_ENV: Final = "ODOO_AI_SHARED_SECRET_FILE"
TURN_TIMEOUT_ENV: Final = "ODOO_AI_TURN_TIMEOUT_SECONDS"
DEFAULT_TURN_TIMEOUT_SECONDS: Final = 150.0
