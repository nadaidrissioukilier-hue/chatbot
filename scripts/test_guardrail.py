#!/usr/bin/env python3
"""Verifie le guardrail v2 (citation reelle) sur un cas reel : contexte
recupere par le pipeline pour une vraie requete, teste contre (a) la vraie
reponse generee par le LLM (doit passer) et (b) une reponse fabriquee qui
cite une institution et un chiffre absents du contexte (doit etre rejetee)."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from src.retrieval.pipeline import retrieve
from src.generation.guardrail import ResponseGuardrail

query = "خدمات لذوي الإعاقة"
retrieval = retrieve(query)
context_obj = retrieval["context"]

guardrail = ResponseGuardrail()
guardrail.set_context(context_obj["json_context"])

real_answer_path = Path("/tmp/claude-1000/-home-ubunto/98efeea6-a54e-4244-87c0-a481cab6f877/scratchpad/post_fix_response.json")
real_answer = json.loads(real_answer_path.read_text())["answer"]

print("=== Test A : vraie reponse LLM (doit etre VALIDE) ===")
valid, cleaned, issues = guardrail.validate_response(real_answer)
print(f"valid={valid}")
print(json.dumps(issues, ensure_ascii=False, indent=2))

fake_answer = (
    "خدمات لذوي الإعاقة المتوفرة تشمل مركز CFA المتخصص، حيث يمكن الحصول على "
    "الخدمة خلال أجل 72 ساعة فقط، مع نسبة تكفل تصل إلى 90% من التكلفة الإجمالية "
    "بعد التسجيل في مؤسسة CJPA المعتمدة لهذا الغرض."
)
print("\n=== Test B : reponse fabriquee (institutions/chiffres hors-contexte, doit etre INVALIDE) ===")
valid2, cleaned2, issues2 = guardrail.validate_response(fake_answer)
print(f"valid={valid2}")
print(json.dumps(issues2, ensure_ascii=False, indent=2))
