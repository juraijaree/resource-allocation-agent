from langchain_core.prompts import ChatPromptTemplate



SAT_EXPLAIN_SOLVER_SYSTEM_MESSAGE = """
Your task is to translate formal Z3 solver outcomes into plain language for disaster managers.
The outcome is a list of assignments.

Rules:
- Use lowercase for resource names, exact names for locations.
- Translate assignments directly, for example "food[a] = 3" -> "send 3 units of food to location a".
- Always include the correct unit for each resource, using the `resources` list.
  - Example: if assignments say "water[a] = 5" and resources has name = water and unit = liters,
    then output "send 5 liters of water to location a".
- Mention only what appears in the assignments.
- Keep sentences short, clear, and natural.

`resources` list = {resources}
"""



sat_explain_solver_prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", SAT_EXPLAIN_SOLVER_SYSTEM_MESSAGE),
        ("user", "{assignments}"),
    ]
)




UNSAT_EXPLAIN_SOLVER_SYSTEM_MESSAGE = """
Your task is to translate formal Z3 solver outcomes into plain language, explaining why constraints are infeasible for disaster managers.
The outcome is a list of conflicted constraint. Explain why constraints are infeasible.

Input you receive:
- A list of conflicted constraints in structured form.
- Each constraint has:
  - an identifier (id). Do not mention this in your output.
  - a left-hand side (lhs): a linear expression made of terms and an optional constant.
  - an operator: one of >=, >, =, <=, <.
  - a right-hand side (rhs): either a number or another linear expression.

How to read the structure:
- A linear expression is the sum of its terms plus the constant.
- Each term has a variable and a coefficient.
- Variables look like resource[Location], for example "water[A]" means "water at A".
- Coefficients indicate multiplication, e.g., coef 2 with water[A] means "twice the water at A".
- Operators should be verbalized:
  >= is "at least"
  >  is "more than"
  =  is "exactly"
  <= is "at most"
  <  is "less than"
- If the rhs is a linear expression, describe it as the sum of its parts. For example:
  “2 x water at A >= food at B + water at C” is “Twice the water at A must be at least the sum of food at B and water at C.”
- If a resource has a unit (from the resources list), include it, e.g., "5 liters of water at A". If no unit, just use the number.

Output rules:
1. Start with a verdict: "Infeasible: constraints conflict."
2. Restate each conflicted constraint in clear, natural language. Do not mention IDs or technical field names.
3. Explain briefly how the rules contradict each other.
4. Suggest up to three minimal relaxations or fixes, phrased in natural language only (e.g., "reduce the water requirement at A from 6 to 5", "remove the rule that B must have more food than A").

Style:
- Keep sentences short.
- Use plain, clear language.
- Do not include math symbols in the explanation; use words instead.
- Only use the information provided in the input.
"""



unsat_explain_solver_prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", UNSAT_EXPLAIN_SOLVER_SYSTEM_MESSAGE),
        ("user", "{conflicts}"),
    ]
)
