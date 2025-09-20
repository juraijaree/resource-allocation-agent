from enum import Enum
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, END, MessagesState, StateGraph
from langgraph.graph.message import add_messages
from typing import Sequence
from typing_extensions import Annotated, TypedDict
from langchain_core.tools import tool
from apply_spec_change import apply_change
from controller_output import ControllerLLMOutput, Intent
from controller_prompt import controller_prompt_template
from resource_allocation_spec import ResourceAllocationSpec, SpecChangeEvent, init_spec
from typing import Optional, Any, Literal
import json
from pydantic import BaseModel
from parser_output import ParsingLLMOutput
from parser_prompt import parser_prompt_template
from datetime import datetime, timezone
from interpreter_prompt import interpreter_prompt_template
from change_summarizer_prompt import change_summarizer_prompt_template
from explain_solver_prompt import sat_explain_solver_prompt_template, unsat_explain_solver_prompt_template
from spec_compiler import SpecCompiler
from z3 import sat, unsat, Z3_INT_SORT

# import logging
# logging.basicConfig(level=logging.DEBUG)


# ==============================================================================
# ================================= STATE ======================================
# ==============================================================================


class CurrentUpdateRequest(TypedDict):
    intent: Intent
    text: str
    instructions: str
    turn_index: int

class SolverResult(TypedDict):
    spec_version: int
    result: Optional[Literal["SAT", "UNSAT"]]
    assignments: Optional[list[str]]
    unsat_constraints_ids: Optional[list[str]]
    explanation: str


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    spec_change_events: list[SpecChangeEvent]
    last_applied_change_index: int
    current_spec: ResourceAllocationSpec
    current_intent: Intent
    current_update_request: Optional[CurrentUpdateRequest]
    solver_result: SolverResult
    info: dict[str, Any]  # scratch pad


# ==============================================================================
# ============================= CONTROLLER LLM =================================
# ==============================================================================

controller_model = init_chat_model(
    "gpt-5-2025-08-07", model_provider="openai"
).with_structured_output(ControllerLLMOutput)


def controller_llm_node(state: AgentState) -> AgentState:
    controller_chain = controller_prompt_template | controller_model
    response: ControllerLLMOutput = controller_chain.invoke(
        {"messages": state.get("messages", [])}
    )

    if response.intent == Intent.UNSUPPORTED_REQUEST:
        reply = "Unsupported, sorry."
        return {
            "messages": [AIMessage(content=reply)],
            "current_intent": response.intent,
            "current_update_request": {},
        }

    if response.intent in [Intent.CLARIFY, Intent.GREET]:
        reply = response.reply if response.reply else "sorry, come again please."
        return {
            "messages": [AIMessage(content=reply)],
            "current_intent": response.intent,
            "current_update_request": {},
        }

    if response.intent == Intent.UPDATE_SPEC:
        return {
            "current_intent": response.intent,
            "current_update_request": {
                "intent": response.intent,
                "text": response.reply,
                "instructions": "",
                "turn_index": 0,  # TODO
            },
        }

    # cleanup
    state["current_intent"] = response.intent
    state["current_update_request"] = {}

    return state


# ==============================================================================
# ============================ INTERPRETER LLM =================================
# ==============================================================================


interpreter_model = init_chat_model(
    "gpt-5-2025-08-07", model_provider="openai", temperature=0
)


def interpreter_llm_node(state: AgentState) -> AgentState:
    """
    Stateless NL to structured instruction using a strict prompt.
    """
    user_message = state.get("current_update_request", {}).get("text", "")
    spec_json = state.get("current_spec", init_spec).model_dump_json(indent=2)
    prompt = interpreter_prompt_template.format_messages(
        user_message=user_message, spec=spec_json
    )
    response = interpreter_model.invoke(prompt)

    state["current_update_request"]["instructions"] = response.content

    return state


# ==============================================================================
# ============================= PARSER LLM =====================================
# ==============================================================================

# TODO: try -> model="gpt-5-reasoning", temperature=0, reasoning={"effort": "high"}

parser_model = init_chat_model(
    "gpt-5-2025-08-07", model_provider="openai", temperature=0
).with_structured_output(ParsingLLMOutput)


def parser_llm_node(state: AgentState) -> AgentState:
    """
    Stateless NL to IR using a strict prompt.
    """
    update_instructions = state.get("current_update_request", {}).get(
        "instructions", ""
    )
    # TODO: handle empty instructions

    prompt = parser_prompt_template.format_messages(
        user_instructions=update_instructions
    )
    response: ParsingLLMOutput = parser_model.invoke(prompt)

    # parser_model outputs [SpecChangeEvent]
    # append to current list
    # GOTO: UpdateSpecNode

    utc_now = datetime.now(timezone.utc)
    id = len(state.get("spec_change_events", [])) + 1

    for c in response.changes:
        new_event = SpecChangeEvent(
            event_id=id,
            timestamp=utc_now,
            change_type=c.change_type,
            change_payload=c.change_payload,
        )
        if state.get("spec_change_events", None):
            state["spec_change_events"].append(new_event)
        else:
            state["spec_change_events"] = [new_event]

        id += 1

    return state


# ==============================================================================
# ========================= APPLY SPEC CHANGE ==================================
# ==============================================================================
def apply_spec_change_node(state: AgentState) -> AgentState:
    # get last change(s)
    last_index = state.get("last_applied_change_index", -1)
    changes = state.get("spec_change_events", [])[last_index + 1 :]

    # get current spec
    new_spec = state.get("current_spec", init_spec)

    # apply change(s)
    for change in changes:
        new_spec = apply_change(new_spec, change)
        # last_index += 1

    return {
        "current_spec": new_spec,
        # "last_applied_change_index": last_index,
    }


# ==============================================================================
# ========================= CHANGE SUMMARIZER ==================================
# ==============================================================================

change_summarizer_model = init_chat_model(
    "gpt-5-mini-2025-08-07", model_provider="openai"
)


def change_summarizer_llm_node(state: AgentState) -> AgentState:
    """
    Stateless: changes -> NL
    """
    # assuming all changes were applied successfully in "apply_spec_change_node"
    last_index = state.get("last_applied_change_index", -1)
    changes = state.get("spec_change_events", [])[last_index + 1 :]

    prompt = change_summarizer_prompt_template.format_messages(changes=changes)
    response = change_summarizer_model.invoke(prompt)

    last_index = last_index + len(changes)

    return {
        "messages": [AIMessage(content=response.content)],
        "last_applied_change_index": last_index,
    }


# ==============================================================================
# =========================== EXPLAIN SPEC LLM =================================
# ==============================================================================
explain_spec_model = init_chat_model("gpt-5-mini-2025-08-07", model_provider="openai")


def explain_spec_llm_node(state: AgentState) -> AgentState:
    print("run explain_spec_model")
    return {}


# ==============================================================================
# =============================== SOLVER =======================================
# ==============================================================================
def solver_node(state: AgentState) -> AgentState:
    # get spec from state
    spec = state.get("current_spec", None)

    if not spec: # TODO: implement "and spec.is_empty():"
        return {
            "solver_result": {
                "spec_version": spec.version,
                "explanation": "no constraints or requirements to solve."
            }
        }

    # compile into solver instance
    compiler = SpecCompiler()
    solver = compiler.compile(spec)

    # run get model or unsat core
    result = solver.check()

    if result == sat:
        model = solver.model()
        assignments = []
        for d in model.decls():
            val = model[d]
            # filter out tracking literals (sort=bool)
            if val.sort().kind() == Z3_INT_SORT:
                assignments.append(f"{d.name()} = {val}")
        return {
            "solver_result": {
                "spec_version": spec.version,
                "result": "SAT",
                "assignments": assignments
            }
        }


    elif result == unsat:
        unsat_core = solver.unsat_core()

        return {
            "solver_result": {
                "spec_version": spec.version,
                "result": "UNSAT",
                "unsat_constraints_ids": [c.decl().name() for c in unsat_core]
            }
        }
    else:
        raise ValueError(f"unknown result: {result}")
    # GOTO: explain_solver_llm_node



# ==============================================================================
# ========================== EXPLAIN SOLVER LLM ================================
# ==============================================================================
explain_solver_model = init_chat_model("gpt-5-mini-2025-08-07", model_provider="openai")


def explain_solver_llm_node(state: AgentState) -> AgentState:
    # get result from state
    solver_result = state.get("solver_result", {})

    # call llm to translate (stateless)
    # - input: result, spec
    # - output -> AIMessage()
    explanation = "n/a"
    r = solver_result.get("result", None)

    if r == "SAT" and solver_result.get("assignments"):
        resources = state.get("current_spec", {}).context.resources
        assignments = solver_result.get("assignments")

        prompt = sat_explain_solver_prompt_template.format_messages(resources=resources, assignments=assignments)
        response = explain_solver_model.invoke(prompt)
        explanation = response.content

    elif r == "UNSAT" and solver_result.get("unsat_constraints_ids"):
        conflict_ids = solver_result.get("unsat_constraints_ids")
        constraints = state.get("current_spec", {}).constraints
        conflicted_constraints = [c for c in constraints if c.id in conflict_ids]

        prompt = unsat_explain_solver_prompt_template.format_messages(resources=resources, assignments=assignments)
        response = explain_solver_model.invoke(prompt)
        explanation = response.content

    # GOTO: END
    return {
        "messages": [AIMessage(content=explanation)],
        "solver_result": {"explanation": explanation}
    }


# ******************************************************************************
# ============================= GRAPH WIRING ===================================
# ******************************************************************************

workflow = StateGraph(state_schema=AgentState)


class NodeName(str, Enum):
    CONTROLLER_LLM = "controller_llm"
    INTERPRETER_LLM = "interpreter_llm"
    PARSER_LLM = "parser_llm"
    APPLY_SPEC_CHANGE = "apply_spec_change"
    CHANGE_SUMMARIZER = "change_summarizer"
    EXPLAIN_SPEC_LLM = "explain_spec_llm"
    SOLVER = "solver"
    EXPLAIN_SOLVER_LLM = "explain_solver_llm"


workflow.add_node(NodeName.CONTROLLER_LLM, controller_llm_node)
workflow.add_node(NodeName.INTERPRETER_LLM, interpreter_llm_node)
workflow.add_node(NodeName.PARSER_LLM, parser_llm_node)
workflow.add_node(NodeName.APPLY_SPEC_CHANGE, apply_spec_change_node)
workflow.add_node(NodeName.CHANGE_SUMMARIZER, change_summarizer_llm_node)
workflow.add_node(NodeName.EXPLAIN_SPEC_LLM, explain_spec_llm_node)
workflow.add_node(NodeName.SOLVER, solver_node)
workflow.add_node(NodeName.EXPLAIN_SOLVER_LLM, explain_solver_llm_node)


def intent_router(state: AgentState):
    match state.get("current_intent"):
        case Intent.UPDATE_SPEC:
            return NodeName.INTERPRETER_LLM
        case Intent.QUERY_SPEC:
            return NodeName.EXPLAIN_SPEC_LLM
        case Intent.SOLVE:
            return NodeName.SOLVER
        case Intent.EXPLAIN_SOLVER:
            return NodeName.EXPLAIN_SOLVER_LLM
        case Intent.CLARIFY | Intent.GREET | Intent.UNSUPPORTED_REQUEST:
            return END
        case _:
            return END


workflow.add_edge(START, NodeName.CONTROLLER_LLM)
workflow.add_conditional_edges(NodeName.CONTROLLER_LLM, intent_router)
workflow.add_edge(NodeName.INTERPRETER_LLM, NodeName.PARSER_LLM)
workflow.add_edge(NodeName.PARSER_LLM, NodeName.APPLY_SPEC_CHANGE)
workflow.add_edge(NodeName.APPLY_SPEC_CHANGE, NodeName.CHANGE_SUMMARIZER)
workflow.add_edge(NodeName.CHANGE_SUMMARIZER, END)
workflow.add_edge(NodeName.SOLVER, NodeName.EXPLAIN_SOLVER_LLM)
workflow.add_edge(NodeName.EXPLAIN_SOLVER_LLM, END)
workflow.add_edge(NodeName.EXPLAIN_SPEC_LLM, END)

# ============================= APP & MEMORY ===================================
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
config = {"configurable": {"thread_id": "abc123"}}


while True:
    query = input("User: ")

    if query == "QUIT" or query == "q":
        print("...bye...")
        break
    if query == "DEBUG":
        print(output["messages"])
        continue

    output = app.invoke({"messages": [HumanMessage(query)]}, config)
    # output["messages"][-1].pretty_print()
    print(f"AI: {output["messages"][-1].content}")


