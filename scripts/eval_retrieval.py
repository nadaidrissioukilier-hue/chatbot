#!/usr/bin/env python3
"""Diagnostic retrieval/ranking — sans LLM (rapide, quelques secondes/dizaines
de secondes par question au lieu de 2-3 minutes). Évalue : détection
d'intent/langue/entités, pertinence des résultats vectoriels+graphe,
comportement du ranking (pénalité EPS, score population/géo).
"""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from src.retrieval import pipeline

TEST_QUERIES = [
    ("centre_creche_ar", "أين أجد أقرب حضانة في سلا؟"),
    ("service_invalidite_fr", "Conditions pour la certification d'invalidité"),
    ("service_invalidite_docs_ar", "ما هي الوثائق المطلوبة للحصول على شهادة الإعاقة؟"),
    ("programme_creches_ar", "برنامج 2027 للحضانات الاجتماعية"),
    ("programme_creches_fr", "Programme 2027 crèches sociales"),
    ("service_mesnin_ar", "شروط إيواء المسنين"),
    ("greeting", "Bonjour, merci beaucoup"),
    ("centre_institution_geo", "أين أجد مركز CEF في الدار البيضاء؟"),
    ("service_handicap_broad", "خدمات لذوي الإعاقة"),
    ("faq_aos_conditions", "ما هي شروط الاستفادة من الاصطياف؟"),
    ("faq_aos_confirmation", "كيف يمكنني تأكيد حجزي في الاصطياف؟"),
    ("centre_geo_marrakech", "مركز اجتماعي في مراكش"),
    ("service_enfants_difficile", "خدمات الأطفال في وضعية صعبة"),
    ("programme_budget_fr", "budget du programme formation professionnelle"),
    ("institution_coaph", "COAPH شروط"),
    ("centre_eps_explicit", "Je cherche un centre EPS"),
    ("service_femmes", "نساء في وضعية صعبة مساعدة"),
    ("centre_geo_fes", "جمعية رعاية المسنين بفاس"),
    ("faq_aos_documents_fr", "quels documents pour l'AOS"),
    ("mixed_lang", "Je cherche خدمة for أطفال"),
]


def run():
    results = []
    for key, query in TEST_QUERIES:
        t0 = time.time()
        try:
            r = pipeline.retrieve(query, use_cache=False)
        except Exception as e:
            results.append({"key": key, "query": query, "error": str(e)})
            print(f"[ERREUR] {key}: {e}")
            continue
        elapsed = time.time() - t0

        top = r["context"]["json_context"]["results"][:5]
        entry = {
            "key": key,
            "query": query,
            "intent": r["intent"],
            "language": r["language"],
            "entities": r["entities"],
            "n_results": r["result_count"],
            "elapsed_s": round(elapsed, 1),
            "top_results": [
                {
                    "rank": t["rank"], "type": t["type"], "name": t["name"],
                    "region": t["location"].get("region"),
                    "score": t["scores"]["final_score"],
                    "reranker_score": t["scores"]["reranker_score"],
                    "is_eps": t["is_eps"],
                    "source_vector": t["sources"]["source_vector"],
                    "source_graph": t["sources"]["source_graph"],
                }
                for t in top
            ],
        }
        results.append(entry)
        top_str = "; ".join(f"{t['name'][:30]}({t['score']:.2f}{'  EPS' if t['is_eps'] else ''})" for t in entry["top_results"][:3])
        print(f"[{elapsed:5.1f}s] {key:30} intent={r['intent']:16} lang={r['language']:5} n={r['result_count']:3} | {top_str}")

    out_path = Path(__file__).parent.parent / "docs" / "eval_retrieval_results.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Résultats détaillés : {out_path}")

    zero_result = [r["key"] for r in results if r.get("n_results", 1) == 0]
    if zero_result:
        print(f"\n⚠ Requêtes sans AUCUN résultat : {zero_result}")


if __name__ == "__main__":
    run()
