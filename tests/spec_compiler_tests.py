import pytest
from z3 import Solver, Int, sat
from src.resource_allocation_spec import (
    ResourceAllocationSpec,
    AllocationContext,
    Locations,
    Resource,
    VarSpec,
    Constraint,
    LinearExpr,
    Term,
)
from spec_compiler import SpecCompiler

"""
case 1:
- The area is modeled as a graph with three interconnected locations: A, B, and C. Each location can receive food and water.
- Location A needs 3 units of food and at least 4 units of water.
- Any location connected to A must receive more food than A.
- Location B must receive exactly 5 units of water.
- Location C must receive more water than the total received by A and B.

fA == 3, wA >= 4
fB > fA, wB == 5
fC > fA, wC > wA + wB


3 == 1*food[A] + 0
4 <= 1*water[A] + 0
1*food[B] + 0 > 1*food[A] + 0
5 == 1*water[B] + 0
1*food[C] + 0 > 1*food[A] + 0
1*water[C] + 0 > 1*water[A] + 1*water[B] + 0
"""


def test_compiler_1():
    # ===== arrange =====
    spec = ResourceAllocationSpec(
        version="0.0.0",
        context=AllocationContext(
            resources=[
                Resource(name="food", unit="unit"),
                Resource(name="water", unit="unit"),
            ],
            locations=Locations(
                nodes=["A", "B", "C"],
                edges={"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]},
            ),
        ),
        vars=[
            VarSpec(id="food[A]", sort="int"),
            VarSpec(id="food[B]", sort="int"),
            VarSpec(id="food[C]", sort="int"),
            VarSpec(id="water[A]", sort="int"),
            VarSpec(id="water[B]", sort="int"),
            VarSpec(id="water[C]", sort="int"),
        ],
        constraints=[
            Constraint(
                id="C001",
                lhs=LinearExpr(terms=[Term(var="food[A]", coef=1)], const=0),
                op="=",
                rhs=3,
            ),
            Constraint(
                id="C002",
                lhs=LinearExpr(terms=[Term(var="water[A]", coef=1)], const=0),
                op=">=",
                rhs=4,
            ),
            Constraint(
                id="C003",
                lhs=LinearExpr(terms=[Term(var="food[B]", coef=1)], const=0),
                op=">",
                rhs=LinearExpr(terms=[Term(var="food[A]", coef=1)], const=0),
            ),
            Constraint(
                id="C004",
                lhs=LinearExpr(terms=[Term(var="water[B]", coef=1)], const=0),
                op="=",
                rhs=5,
            ),
            Constraint(
                id="C005",
                lhs=LinearExpr(terms=[Term(var="food[C]", coef=1)], const=0),
                op=">",
                rhs=LinearExpr(terms=[Term(var="food[A]", coef=1)], const=0),
            ),
            Constraint(
                id="C006",
                lhs=LinearExpr(terms=[Term(var="water[C]", coef=1)], const=0),
                op=">",
                rhs=LinearExpr(
                    terms=[
                        Term(var="water[A]", coef=1),
                        Term(var="water[B]", coef=1),
                    ],
                    const=0,
                ),
            ),
        ],
    )

    # ===== act =====
    compiler = SpecCompiler()
    s = compiler.compile(spec)


    # ===== assert =====
    assert isinstance(s, Solver)

    assert len(compiler.vars) == len(spec.vars)
    assert len(compiler.constraint_trackings) == len(spec.constraints)
    assert len(compiler.constraint_expressions) == len(spec.constraints)

    for compiled_var, spec_var in zip(compiler.vars, spec.vars):
        assert compiled_var.__repr__() == spec_var.id

    for compiled_tkr, spec_constr in zip(
        compiler.constraint_trackings, spec.constraints
    ):
        assert compiled_tkr.__repr__() == spec_constr.id

    print("\n-----\n")

    for compiled_expr, spec_constr in zip(
        compiler.constraint_expressions, spec.constraints
    ):
        print(compiled_expr.__repr__())
