#!/usr/bin/env python3
"""Test de fidélité factuelle (groundedness) : pour chaque question, sauvegarde
CÔTE À CÔTE le contexte exact envoyé au LLM et la réponse générée, pour
permettre une comparaison manuelle rigoureuse (plus fiable qu'un matching de
mots-clés automatique pour de l'arabe/français mélangé).
"""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from src.retrieval import pipeline
from src.generation.guardrail import ResponseGuardrail
from src.inference.llamacpp_client import LlamaCppClient

SYSTEM_PROMPT = (
    "Tu es un assistant officiel de l'Entraide Nationale (Maroc).\n"
    "Tu réponds uniquement à partir du contexte fourni.\n"
    "- Langue = langue de la question (arabe ou français)\n"
    "- Ne jamais inventer conditions, documents, centres ou programmes\n"
    "- Si information absente -> le dire clairement et orienter vers le centre le plus proche\n"
    "- Va droit au but : commence directement par la réponse utile, sans salutation ni préambule\n"
    "- Cite les centres, conditions et documents quand disponibles, sous forme de liste courte avec des tirets\n"
    "- Texte brut uniquement : jamais de markdown (pas de **gras**, pas de #titres, pas de ```code```)\n"
    "- Réponses concises et factuelles, 5 à 8 lignes maximum sauf si la question demande une liste plus longue"
)

QUERIES = [
    ("service_invalidite_docs_ar", "ما هي الوثائق المطلوبة للحصول على شهادة الإعاقة؟"),
    ("centre_creche_ar", "أين أجد أقرب حضانة في سلا؟"),
    ("programme_creches_fr", "Programme 2027 crèches sociales, quel est le budget ?"),
    ("faq_aos_conditions", "ما هي شروط الاستفادة من الاصطياف؟"),
]

llm_client = LlamaCppClient()


def run():
    output = []
    for key, query in QUERIES:
        print(f"\n=== {key}: {query} ===")
        t0 = time.time()
        retrieval = pipeline.retrieve(query, use_cache=False)
        context_obj = retrieval["context"]
        t_retrieval = time.time()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Contexte:\n{context_obj['text_prompt']}\n\nQuestion: {query}"},
        ]
        answer = llm_client.chat_completion(messages, max_tokens=512, temperature=0.3)
        t_llm = time.time()

        guardrail = ResponseGuardrail()
        guardrail.set_context(context_obj["json_context"])
        is_valid, cleaned, issues = guardrail.validate_response(answer)

        entry = {
            "key": key, "query": query,
            "intent": retrieval["intent"], "language": retrieval["language"],
            "context_sent_to_llm": context_obj["text_prompt"],
            "answer": answer,
            "guardrail_valid": is_valid, "guardrail_issues": issues,
            "timing_s": {"retrieval": round(t_retrieval - t0, 1), "llm": round(t_llm - t_retrieval, 1)},
        }
        output.append(entry)
        print(f"[retrieval {entry['timing_s']['retrieval']}s | llm {entry['timing_s']['llm']}s] "
              f"guardrail_valid={is_valid}")
        print(f"REPONSE: {answer[:200]}...")

    out_path = Path(__file__).parent.parent / "docs" / "eval_faithfulness_results.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Résultats complets (contexte + réponse côte à côte) : {out_path}")


if __name__ == "__main__":
    run()
