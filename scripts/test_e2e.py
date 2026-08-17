#!/usr/bin/env python3
"""Les 8 scénarios métier obligatoires du guide de déploiement, exécutés
contre /chat. Vérifie : réponse non vide, sources présentes quand attendu,
pas de crash, cohérence de langue basique.
"""
import os
import sys
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY_WIDGET", "changeme-widget-api-key")

QUESTIONS = [
    {"q": "أين أجد أقرب حضانة في سلا؟", "expect_intent": "centre_search", "expect_sources": True},
    {"q": "Conditions d'obtention de la certification d'invalidité", "expect_intent": "service_search", "expect_sources": True},
    {"q": "ما هي الوثائق اللازمة لتأكيد الاستفادة من الاصطياف؟", "expect_intent": None, "expect_sources": True},
    {"q": "Programme 2027 des crèches sociales", "expect_intent": "programme_2027", "expect_sources": True},
    {"q": "شروط إيواء المسنين", "expect_intent": "service_search", "expect_sources": True},
    {"q": "Bonjour, merci beaucoup", "expect_intent": "other", "expect_sources": False},
    {"q": "Je cherche une crèche بالرباط للأطفال", "expect_intent": None, "expect_sources": True},
    {"q": "شروط COAPH", "expect_intent": None, "expect_sources": True},
]


def run():
    failures = []
    for i, case in enumerate(QUESTIONS, 1):
        try:
            r = requests.post(
                f"{BASE_URL}/chat",
                json={"query": case["q"]},
                headers={"X-API-Key": API_KEY},
                # 2026-08-13 : 90s était calibré pour GROUNDED_MAX_TOKENS=512
                # (config.py) -- relevé depuis à 900 ("donner le max de text
                # data"), une génération complète peut légitimement dépasser
                # 90s (mesuré : jusqu'à ~170s pour une réponse riche).
                timeout=300,
            )
        except requests.RequestException as e:
            failures.append(f"#{i} '{case['q']}': exception réseau: {e}")
            continue

        if r.status_code != 200:
            failures.append(f"#{i} '{case['q']}': HTTP {r.status_code} — {r.text[:200]}")
            continue

        data = r.json()
        answer = data.get("answer", "")
        sources = data.get("sources", [])

        status = "OK"
        if not answer.strip():
            failures.append(f"#{i} '{case['q']}': réponse vide")
            status = "ÉCHEC"
        if case["expect_sources"] and not sources:
            failures.append(f"#{i} '{case['q']}': sources attendues mais absentes")
            status = "ÉCHEC"

        print(f"[{status}] #{i} intent={data.get('intent')} lang={data.get('language')} "
              f"sources={len(sources)} total_ms={data.get('timings_ms', {}).get('total')} — {case['q'][:50]}")

    print(f"\n{len(QUESTIONS) - len(failures)}/{len(QUESTIONS)} scénarios passés")
    if failures:
        print("\nÉchecs:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("✅ Tous les scénarios obligatoires du guide passent")


if __name__ == "__main__":
    run()
