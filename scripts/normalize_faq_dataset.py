#!/usr/bin/env python3
"""Normalise ~/Downloads/data_faq/faq_enriched.json (129 FAQ, hors pipeline
d'origine du guide) vers data/processed/, meme convention que 01_Normalize
(rag data/ brut -> data/processed/ durable). A lancer une seule fois -- la
source Downloads est transitoire, seule la sortie ici est versionnee/reutilisee
par 02_Chunk / 05_Neo4j_Load / 06_Qdrant_Index.

Usage: .venv/bin/python3 scripts/normalize_faq_dataset.py
"""
import json
import sys
from pathlib import Path

UNIT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UNIT_DIR / "notebooks"))

from etl_lib.faq_dataset import normalize_faq_dataset  # noqa: E402
from etl_lib.io_utils import save_jsonl  # noqa: E402

SOURCE = Path.home() / "Downloads" / "data_faq" / "faq_enriched.json"
PROCESSED_DIR = UNIT_DIR / "data" / "processed"
REPORTS_DIR = UNIT_DIR / "data" / "reports"


def main():
    if not SOURCE.exists():
        print(f"✗ Source introuvable: {SOURCE}", file=sys.stderr)
        sys.exit(1)

    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    faqs = raw["faqs"]
    print(f"Source: {SOURCE} ({len(faqs)} FAQ)")

    service_faqs, institution_enrichments, general_faqs, report = normalize_faq_dataset(faqs)

    save_jsonl(PROCESSED_DIR / "faq_extra_service.jsonl", service_faqs)
    save_jsonl(PROCESSED_DIR / "institution_enrich.jsonl", institution_enrichments)
    save_jsonl(PROCESSED_DIR / "faq_extra_general.jsonl", general_faqs)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "report_faq_extra_normalize.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✓ Famille A (FAQ Service)          : {report['family_A_service']:3d} -> faq_extra_service.jsonl")
    print(f"✓ Famille B (fiches Institution)    : {report['family_B_institution_deduped']:3d} "
          f"(dédupliqué depuis {report['family_B_institution_raw']}) -> institution_enrich.jsonl")
    print(f"✓ Famille C (contenu générique)     : {report['family_C_general']:3d} -> faq_extra_general.jsonl")
    print(f"  Codes institution trouvés         : {', '.join(report['institution_codes_found'])}")
    print(f"  Doublons famille B écartés        : {report['family_B_dropped_duplicates']}")
    total = report['family_A_service'] + report['family_B_institution_deduped'] + report['family_C_general']
    assert report['family_A_service'] + report['family_B_institution_raw'] + report['family_C_general'] == report['total_input'], \
        "Toutes les entrées doivent être classées dans une famille -- aucune perte silencieuse"
    print(f"\n✅ {total} enregistrements normalisés (sur {report['total_input']} FAQ sources, "
          f"{report['family_B_institution_raw'] - report['family_B_institution_deduped']} doublons B fusionnés).")


if __name__ == "__main__":
    main()
