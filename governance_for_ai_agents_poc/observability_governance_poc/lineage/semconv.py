"""Attribute and span names used on OpenTelemetry spans and metrics, in one place.

GenAI names follow the OpenTelemetry GenAI semantic conventions, which are in Development status (not stable) at the time
of the run; HTTP names follow the stable HTTP conventions.  Verified against the sources in research/sources.md.  Names in
the `lineage.` namespace are this POC's own and are never presented as official.
"""

# GenAI (Development status)
OP = "gen_ai.operation.name"
PROVIDER = "gen_ai.provider.name"
REQ_MODEL = "gen_ai.request.model"
RESP_MODEL = "gen_ai.response.model"
TEMPERATURE = "gen_ai.request.temperature"
SEED = "gen_ai.request.seed"
IN_TOKENS = "gen_ai.usage.input_tokens"
OUT_TOKENS = "gen_ai.usage.output_tokens"
FINISH = "gen_ai.response.finish_reasons"
AGENT_ID = "gen_ai.agent.id"
AGENT_NAME = "gen_ai.agent.name"
AGENT_VERSION = "gen_ai.agent.version"
TOOL_NAME = "gen_ai.tool.name"
TOOL_CALL_ID = "gen_ai.tool.call.id"
TOOL_TYPE = "gen_ai.tool.type"
CONVERSATION_ID = "gen_ai.conversation.id"
TOKEN_TYPE = "gen_ai.token.type"
M_TOKEN_USAGE = "gen_ai.client.token.usage"
M_OP_DURATION = "gen_ai.client.operation.duration"

# HTTP (stable)
HTTP_METHOD = "http.request.method"
HTTP_STATUS = "http.response.status_code"
HTTP_ROUTE = "http.route"
URL_FULL = "url.full"
SERVER_ADDRESS = "server.address"
SERVER_PORT = "server.port"
ERROR_TYPE = "error.type"
