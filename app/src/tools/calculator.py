"""Calcul arithmétique direct — logique métier sans passer par le LLM.

Demande du 2026-08-12 : "les questions habituelles comme calculatrice...
doivent être traitées avec une logique métier sans consommer beaucoup de
tokens". Un calcul simple ("15+27", "كم يساوي 100 على 4") n'a besoin ni de
retrieval (Qdrant/Neo4j) ni de génération LLM (~60-160s sur ce CPU) : on le
détecte et on le résout directement, en quelques millisecondes.

Évaluation sûre via `ast` (whitelist stricte des nœuds autorisés) -- jamais
`eval()` brut, qui exécuterait n'importe quelle expression Python.
"""
import ast
import operator
import re
from typing import Optional, Dict, Any

_ALLOWED_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}

# Mots-opérateurs -> symbole, appliqués avant extraction de l'expression
# (permet "15 زائد 27" ou "20 fois 3" en plus de la forme symbolique).
_WORD_OPERATORS = [
    (r"زائد", "+"), (r"ناقص", "-"), (r"ضرب", "*"), (r"\bفي\b", "*"),
    (r"تقسيم", "/"), (r"على", "/"),
    (r"\bplus\b", "+"), (r"\bmoins\b", "-"), (r"\bfois\b", "*"),
    (r"divis[ée]e?\s*(par|sur)?", "/"),
]

# Déclencheur explicite ("calcule...", "كم يساوي...") -- sans lui, on exige
# que la requête entière (après normalisation) soit déjà une expression pure,
# pour ne jamais confondre un numéro de programme ("برنامج 2027") avec un calcul.
_TRIGGER_RE = re.compile(
    r"احسب|كم\s+(يساوي|يساو|تساوي)|"
    r"calcul(?:e|er)?|combien\s+(?:fait|font|vaut|égal)|résultat\s+de",
    re.IGNORECASE,
)

_PURE_EXPRESSION_RE = re.compile(r"^[\d\s+\-*/().]+$")
_CANDIDATE_RE = re.compile(r"[\d\s+\-*/().]{3,}")


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Nœud non autorisé: {type(node).__name__}")


def try_calculate(query: str) -> Optional[Dict[str, Any]]:
    """Détecte et calcule une expression arithmétique simple dans `query`.
    Retourne None si ce n'est pas un calcul (laisse le pipeline normal
    gérer la requête) -- {"expression": str, "result": int|float} sinon."""
    q = query.strip()
    if not q:
        return None

    normalized = q.lower()
    for pattern, op in _WORD_OPERATORS:
        normalized = re.sub(pattern, f" {op} ", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".")

    has_operator = bool(re.search(r"[+\-*/]", normalized))
    if not has_operator:
        return None

    has_trigger = bool(_TRIGGER_RE.search(q))
    is_pure_expression = bool(_PURE_EXPRESSION_RE.match(normalized.strip()))
    if not (has_trigger or is_pure_expression):
        return None

    match = _CANDIDATE_RE.search(normalized)
    if not match:
        return None
    candidate = re.sub(r"\s+", " ", match.group(0).strip().rstrip("+-*/ "))
    if not candidate or not re.search(r"\d", candidate) or not re.search(r"[+\-*/]", candidate):
        return None

    try:
        tree = ast.parse(candidate, mode="eval")
        result = _eval_node(tree)
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError):
        return None

    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return {"expression": candidate, "result": result}
