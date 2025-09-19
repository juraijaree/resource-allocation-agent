from enum import Enum
from typing import Literal, Union, Annotated, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class Resource(BaseModel):
    name: str = Field(description="Resource name, e.g. 'food', 'water', 'medicine'.")
    unit: str = Field(
        description="Measurement unit e.g. 'units' or 'liters'; default to 'units' if unspecified."
    )


class Edge(BaseModel):
    src: str = Field(description="Source node name")
    dst: str = Field(description="Destination node name")

class Locations(BaseModel):
    nodes: list[str] = Field(description="List of location names, e.g. ['a','location_b'].")
    edges: list[Edge] = Field(description="Graph edges as a list of {src,dst} pairs")

VarId = Annotated[
    str,
    Field(
        pattern=r"^[a-z_][a-z0-9_]*\[[a-z0-9_]+\]$",
        description="Variable id formatted as '<resource>[<location>]' (snake_case), e.g. 'food[a]'.",
    ),
]


class VarSpec(BaseModel):
    id: VarId
    sort: Literal["int"] = Field(
        description="Variable type; always 'int' for resource allocations."
    )


class Term(BaseModel):
    var: VarId = Field(
        description="Reference to a defined variable id. (must match a defined var)"
    )
    coef: int = Field(
        default=1, description="Integer coefficient multiplying the variable."
    )


class LinearExpr(BaseModel):
    terms: list[Term] = Field(
        default_factory=list,
        description="Sum of variable terms; combine duplicates, drop zero coefficients.",
    )
    const: int = Field(
        default=0, description="Integer constant added to the expression."
    )


class Constraint(BaseModel):
    id: str = Field(
        description="Unique zero-padded constraint ID like 'C0001', 'C0002', etc."
    )
    lhs: LinearExpr = Field(description="Left-hand side linear expression.")
    op: Literal[">=", ">", "=", "<=", "<"] = Field(
        description="Allowed operators only: >=, >, =, <=, <"
    )
    rhs: Union[int, LinearExpr] = Field(
        description="Right-hand side: integer or linear expression."
    )
    # text: str = Field(description="Human-readable statement of the constraint")


class AllocationContext(BaseModel):
    resources: list[Resource] = Field(description="Resources mentioned in the text.")
    locations: Locations = Field(
        description="Graph structure: nodes and adjacency list."
    )

# ================================== Full Spec ========================================

class ResourceAllocationSpec(BaseModel):
    version: int = Field(description="Schema version, e.g. '1'.")
    context: AllocationContext = Field(
        description="Problem context extracted from natural language: resources and location graph"
    )
    vars: list[VarSpec] = Field(
        description="Variables generated for every <resource, location> pair."
    )
    constraints: list[Constraint] = Field(
        default_factory=list, description="Linear constraints derived from user text."
    )
    assumptions: list[str] = Field(
        default_factory=list, description="Global assumptions, e.g., non-negativity."
    )
    notes: str = Field(
        default="",
        description="Optional brief free-text notes for ambiguities or skipped constraints.",
    )


init_spec = ResourceAllocationSpec(
    version=1,
    context=AllocationContext(resources=[], locations={"nodes":[], "edges":[]}),
    vars=[],
    constraints=[],
    assumptions=[],
    notes=""
)




# ================================== Change Payloads ========================================

class AddConstraintChange(BaseModel):
    constraint: Constraint = Field(..., description="Fully specified constraint to add.")

class RemoveConstraintChange(BaseModel):
    constraint_id: str = Field(..., description="ID of the constraint to remove, e.g., 'C0007'.")

class UpdateConstraintChange(BaseModel):
    # Patch semantics: only provided fields are updated.
    constraint_id: str = Field(..., description="ID of the constraint to update.")
    lhs: Optional[LinearExpr] = Field(None, description="New LHS; omit to keep existing.")
    op: Optional[Literal[">=", ">", "=", "<=", "<"]] = Field(None, description="New operator; omit to keep existing.")
    rhs: Optional[Union[int, LinearExpr]] = Field(None, description="New RHS; omit to keep existing.")

class AddResourceChange(BaseModel):
    resource: Resource = Field(..., description="Resource to add (name, unit).")

class RemoveResourceChange(BaseModel):
    name: str = Field(..., description="Exact resource name to remove, e.g., 'food'.")

class AddLocationChange(BaseModel):
    # Support adding either a node OR an edge (one-of).
    node: Optional[str] = Field(None, description="Location node to add, e.g., 'D'.")
    edge: Optional[Edge] = Field(None, description="Graph edge to add, e.g., {src:'A', dst:'D'}.")

class RemoveLocationChange(BaseModel):
    # Support removing either a node OR an edge (one-of).
    node: Optional[str] = Field(None, description="Location node to remove, e.g., 'C'.")
    edge: Optional[Edge] = Field(None, description="Graph edge to remove, e.g., {src:'A', dst:'B'}.")

ChangePayload = Union[
    AddConstraintChange,
    RemoveConstraintChange,
    UpdateConstraintChange,
    AddResourceChange,
    RemoveResourceChange,
    AddLocationChange,
    RemoveLocationChange,
]

# ================================== Change Types ========================================

class ChangeType(str, Enum):
    ADD_CONSTRAINT = "add_constraint"
    REMOVE_CONSTRAINT = "remove_constraint"
    UPDATE_CONSTRAINT = "update_constraint"
    ADD_RESOURCE = "add_resource"
    REMOVE_RESOURCE = "remove_resource"
    ADD_LOCATION = "add_location"
    REMOVE_LOCATION = "remove_location"

# ================================== Change Event ========================================

class SpecChangeEvent(BaseModel):
    event_id: int
    timestamp: datetime
    change_type: ChangeType
    change_payload: ChangePayload




# =========================================================================

# TODO: canonicalize
# def canonicalize(self) -> "ResourceAllocationSpec":
#     """
#     Example: rewrite (x > k) as (x >= k+1). No arithmetic on symbolic rhs terms
#     beyond shifting constants.
#     """
#     new_constraints: List[Constraint] = []
#     for c in self.constraints:
#         if c.op == ">":
#             # lhs > rhs  =>  lhs >= rhs + 1
#             if isinstance(c.rhs, int):
#                 new_constraints.append(
#                     Constraint(id=c.id, lhs=c.lhs, op=">=", rhs=c.rhs + 1)
#                 )
#             elif isinstance(c.rhs, LinearExpr):
#                 rhs = c.rhs.model_copy(deep=True)
#                 rhs.const += 1
#                 new_constraints.append(
#                     Constraint(id=c.id, lhs=c.lhs, op=">=", rhs=rhs)
#                 )
#             else:
#                 new_constraints.append(c)
#         else:
#             new_constraints.append(c)
#     return self.model_copy(update={"constraints": new_constraints})
