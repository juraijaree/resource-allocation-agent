from z3 import Solver, Int, Bool, Sum, IntVal, BoolRef, ArithRef
from resource_allocation_spec import ResourceAllocationSpec, Constraint, LinearExpr


class SpecCompiler:
    def __init__(self):
        self.solver = None
        self.vars: list[ArithRef] = []
        self.constraint_trackings: list[BoolRef] = []
        self.constraint_expressions: list[BoolRef] = []

    def compile(self, spec: ResourceAllocationSpec) -> Solver:
        # build variables dict
        var_dict: dict[str, ArithRef] = {}
        for var in spec.vars:
            if var.sort == "int":
                var_dict[var.id] = Int(var.id)
            else:
                raise ValueError(
                    f"Unsupported sort for variable '{var.id}': {var.sort}"
                )

        # build tracking literals for constraints
        # build constraint expression dict
        constraint_tracking_dict: dict[str, BoolRef] = {}
        constraint_expr_dict: dict[str, BoolRef] = {}
        for c in spec.constraints:
            constraint_tracking_dict[c.id] = Bool(c.id)
            constraint_expr_dict[c.id] = self._create_constraint_expression(c, var_dict)

        # instantiate solver instance
        s = Solver()

        # add allocation requirements with tracking
        for c in spec.constraints:
            s.assert_and_track(
                constraint_expr_dict[c.id], constraint_tracking_dict[c.id]
            )

        # populate fields
        self.solver = s
        for _v in var_dict.values():
            self.vars.append(_v)
        for _tkr in constraint_tracking_dict.values():
            self.constraint_trackings.append(_tkr)
        for _expr in constraint_expr_dict.values():
            self.constraint_expressions.append(_expr)

        return s

    def _convert_linear_expr_to_expr_operant(
        self, expr: LinearExpr, var_dict: dict[str, ArithRef]
    ) -> ArithRef:
        """
        Convert IR LinearExpr into a Z3 arithmetic expression:
        sum(coef_i * var_i) + const
        """
        terms = []
        for t in expr.terms:
            if t.var not in var_dict:
                raise ValueError(f"Undeclared variable in expression: '{t.var}'")
            terms.append(t.coef * var_dict[t.var])

        if terms:
            return Sum(terms) + IntVal(expr.const)
        else:
            return IntVal(0) + IntVal(expr.const)  # IntVal(0) for consistent shape

    def _create_constraint_expression(
        self, c: Constraint, var_dict: dict[str, ArithRef]
    ) -> BoolRef:
        # LHS is always a LinearExpr (var or expr)
        if isinstance(c.lhs, LinearExpr):
            lhs = self._convert_linear_expr_to_expr_operant(c.lhs, var_dict)
        else:
            raise ValueError(f"Unsupported LHS for constraint {c.id}: {c.rhs!r}")

        # RHS can be an int or a LinearExpr
        if isinstance(c.rhs, int):
            rhs = IntVal(c.rhs)
        elif isinstance(c.rhs, LinearExpr):
            rhs = self._convert_linear_expr_to_expr_operant(c.rhs, var_dict)
        else:
            raise ValueError(f"Unsupported RHS for constraint {c.id}: {c.rhs!r}")

        match c.op:
            case ">=":
                return lhs >= rhs
            case ">":
                return lhs > rhs
            case "=":
                return lhs == rhs
            case "<=":
                return lhs <= rhs
            case "<":
                return lhs < rhs
            case _:
                raise ValueError(f"Unsupported operator in constraint {c.id}: {c.op!r}")
