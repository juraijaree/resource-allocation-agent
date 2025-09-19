from copy import deepcopy
from typing import Optional, Set
import re
from resource_allocation_spec import (
    AddConstraintChange,
    AddLocationChange,
    AddResourceChange,
    ChangePayload,
    ChangeType,
    Constraint,
    Edge,
    LinearExpr,
    RemoveConstraintChange,
    RemoveLocationChange,
    RemoveResourceChange,
    ResourceAllocationSpec,
    SpecChangeEvent,
    UpdateConstraintChange,
    VarSpec,
)


# ============================== HELPERS =====================================


def _next_constraint_id(existing: list[Constraint]) -> str:
    nums = []
    for c in existing:
        m = re.match(r"^[A-Za-z]*0*([0-9]+)$", c.id)
        if m:
            nums.append(int(m.group(1)))
    nxt = (max(nums) + 1) if nums else 1
    return f"C{nxt:04d}"


def _vars_in_expr(expr: LinearExpr | int) -> Set[str]:
    if isinstance(expr, int):
        return set()
    return {t.var for t in expr.terms}


def _vars_in_constraint(c: Constraint) -> Set[str]:
    vs = set(_vars_in_expr(c.lhs))
    vs |= _vars_in_expr(c.rhs)
    return vs

def increment_version(old: ResourceAllocationSpec, new: ResourceAllocationSpec) -> None:
    if old != new:
        new.version += 1

# ============================== MAIN =====================================


def apply_change(
    spec: ResourceAllocationSpec, change: SpecChangeEvent
) -> ResourceAllocationSpec:
    """
    Apply a single SpecChangeEvent to a ResourceAllocationSpec and return a new spec.
    Notes:
      - No canonicalization here (assumed done elsewhere).
      - Missing targets (e.g., unknown IDs) are treated as no-ops.
      - For update_constraint: patch semantics; provided sides replace entirely.
    """
    s = deepcopy(spec)
    ct: ChangeType = change.change_type
    payload: ChangePayload = change.change_payload

    # ADD_CONSTRAINT
    if ct == ChangeType.ADD_CONSTRAINT and isinstance(payload, AddConstraintChange):
        new_c = payload.constraint
        cid = new_c.id
        if cid == "__AUTO__" or any(c.id == cid for c in s.constraints):
            new_c.id = _next_constraint_id(s.constraints)
        s.constraints.append(new_c)
        increment_version(spec, s)
        return s

    # REMOVE_CONSTRAINT
    if ct == ChangeType.REMOVE_CONSTRAINT and isinstance(
        payload, RemoveConstraintChange
    ):
        s.constraints = [c for c in s.constraints if c.id != payload.constraint_id]
        increment_version(spec, s)
        return s

    # UPDATE_CONSTRAINT (patch)
    if ct == ChangeType.UPDATE_CONSTRAINT and isinstance(
        payload, UpdateConstraintChange
    ):
        cid = payload.constraint_id
        idx = next((i for i, c in enumerate(s.constraints) if c.id == cid), None)
        if idx is None:
            return s  # no-op

        current_constraint = s.constraints[idx]
        lhs = getattr(payload, "lhs", None)
        op = getattr(payload, "op", None)
        rhs = getattr(payload, "rhs", None)
        updated = current_constraint.model_copy(
            update={
                **({"lhs": lhs} if lhs is not None else {}),
                **({"op": op} if op is not None else {}),
                **({"rhs": rhs} if rhs is not None else {}),
            }
        )
        s.constraints[idx] = updated
        increment_version(spec, s)
        return s

    # ADD_RESOURCE
    if ct == ChangeType.ADD_RESOURCE and isinstance(payload, AddResourceChange):
        res = payload.resource
        if not any(r.name == res.name for r in s.context.resources):
            s.context.resources.append(res)
            # generate vars for new resource across all existing nodes
            new_vars = [
                VarSpec(id=f"{res.name}[{node}]", sort="int") for node in s.context.locations.nodes
            ]
            # avoid duplicates
            existing = {v.id for v in s.vars}
            s.vars.extend([v for v in new_vars if v.id not in existing])

        increment_version(spec, s)
        return s

    # REMOVE_RESOURCE
    if ct == ChangeType.REMOVE_RESOURCE and isinstance(payload, RemoveResourceChange):
        name = payload.name
        before = len(s.context.resources)
        s.context.resources = [r for r in s.context.resources if r.name != name]

        # remove successful
        if len(s.context.resources) != before:
            var_ids = {f"{name}[{node}]" for node in s.context.locations.nodes}
            s.vars = [v for v in s.vars if v.id not in var_ids]
            s.constraints = [
                c for c in s.constraints if _vars_in_constraint(c).isdisjoint(var_ids)
            ]

        increment_version(spec, s)
        return s

    # ADD_LOCATION (node or edge)
    if ct == ChangeType.ADD_LOCATION and isinstance(payload, AddLocationChange):
        node: Optional[str] = getattr(payload, "node", None)
        edge: Optional[Edge] = getattr(payload, "edge", None)

        if node:
            if node not in s.context.locations.nodes:
                s.context.locations.nodes.append(node)
                # generate vars for all resources at this node
                existing = {v.id for v in s.vars}
                for r in s.context.resources:
                    vid = f"{r.name}[{node}]"
                    if vid not in existing:
                        s.vars.append(VarSpec(id=vid, sort="int"))

        elif edge:
            # add edge if both nodes exist and edge not present
            src, dst = edge.src, edge.dst
            nodes = set(s.context.locations.nodes)
            if src in nodes and dst in nodes:
                exists = any(
                    e.src == src and e.dst == dst for e in s.context.locations.edges
                )
                if not exists:
                    s.context.locations.edges.append(edge)

        increment_version(spec, s)
        return s

    # REMOVE_LOCATION (node or edge)
    if ct == ChangeType.REMOVE_LOCATION and isinstance(payload, RemoveLocationChange):
        node: Optional[str] = getattr(payload, "node", None)
        edge: Optional[Edge] = getattr(payload, "edge", None)

        if node:
            if node in s.context.locations.nodes:
                # remove node
                s.context.locations.nodes = [
                    n for n in s.context.locations.nodes if n != node
                ]
                # remove incident edges
                s.context.locations.edges = [
                    e
                    for e in s.context.locations.edges
                    if e.src != node and e.dst != node
                ]
                # remove vars and constraints referencing this node
                var_ids = {f"{r.name}[{node}]" for r in s.context.resources}
                s.vars = [v for v in s.vars if v.id not in var_ids]
                s.constraints = [
                    c
                    for c in s.constraints
                    if _vars_in_constraint(c).isdisjoint(var_ids)
                ]
        elif edge:
            s.context.locations.edges = [
                e
                for e in s.context.locations.edges
                if not (e.src == edge.src and e.dst == edge.dst)
            ]

        increment_version(spec, s)
        return s

    # Unknown type = no-op
    return s
