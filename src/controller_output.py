from enum import Enum
from pydantic import BaseModel, Field


# shared
class Intent(str, Enum):
    UPDATE_SPEC = "update_spec"
    QUERY_SPEC = "query_spec"
    SOLVE = "solve"
    EXPLAIN_SOLVER = "explain_solver"
    CLARIFY = "clarify"
    GREET = "greet"
    UNSUPPORTED_REQUEST = "unsupported_request"


"""
 new intent?

Explain-solver path (result already available)
1. START -> Controller
2. intent=EXPLAIN_SOLVER and solver_result present/fresh
3. -> ExplainSolver LLM -> END
 """


class ControllerLLMOutput(BaseModel):
    intent: Intent = Field(
        ...,
        description="The classified user intent based on their request. Always one of the supported intents.",
    )
    reply: str | None = Field(
        default=None,
        description="A concise, user-facing message. Only required when intent is 'greet' or 'clarify'; otherwise, leave as None.",
    )
