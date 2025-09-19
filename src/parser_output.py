from pydantic import BaseModel, Field
from resource_allocation_spec import ChangePayload, ChangeType


class ChangeOutput(BaseModel):
    change_type: ChangeType = Field(
        ...,
        description=(
            "The kind of atomic update to apply. Choose EXACTLY one from: "
            "'add_constraint', 'remove_constraint', 'update_constraint', "
            "'add_resource', 'remove_resource', 'add_location', 'remove_location'."
        ),
    )
    change_payload: ChangePayload = Field(
        ...,
        description=(
            "The payload object depends on the selected change_type. Its structure is as follows:"
            "Examples:"
            "- add_constraint -> The key is constraint. The value is a full Constraint object."
            "- remove_constraint -> The key is constraint_id. The value is the unique identifier of the constraint (for example: C0007)."
            "- update_constraint -> The key is constraint_id (value is the identifier of the constraint). Additionally, there may be keys for the parts of the constraint you want to update: lhs, op, or rhs. The values for these keys are the new values you want to assign."
            "- add_resource -> The key is resource. The value is an object containing two keys: name and unit."
            "- remove_resource -> The key is name. The value is the name of the resource to remove."
            "- add_location -> You must provide:"
            "  - A key node with its value being the identifier of the node, AND/OR"
            "  - A key edge with its value being an object containing two keys: src (the source node) and dst (the destination node)."
            "- remove_location -> Same structure as add_location. Provide either a key node with its value being the node identifier, and/or a key edge with its value containing src and dst."
            "Only include the keys and values that are relevant to the chosen change_type."
        ),
    )


class ParsingLLMOutput(BaseModel):
    changes: list[ChangeOutput] = Field(
        default_factory=list,
        description=(
            "Ordered list of ALL explicit, mandatory updates parsed from the input. "
            "Return an empty list [] if no safe updates are found. "
            "Deterministic order (if multiple): "
            "1) add_resource, 2) add_location (node, then edge), "
            "3) add_constraint, 4) update_constraint, 5) remove_constraint, "
            "6) remove_resource, 7) remove_location. "
        ),
    )


# '- add_constraint → {"constraint": Constraint} '
# '- remove_constraint → {"constraint_id": "C0007"} '
# '- update_constraint → {"constraint_id": ..., [lhs|op|rhs]} '
# '- add_resource → {"resource": {"name": ..., "unit": ...}} '
# '- remove_resource → {"name": ...} '
# '- add_location → {"node": ...} OR {"edge": {"src": ..., "dst": ...}} '
# '- remove_location → {"node": ...} OR {"edge": {"src": ..., "dst": ...}} '
# "Do NOT include fields irrelevant to the chosen change_type."