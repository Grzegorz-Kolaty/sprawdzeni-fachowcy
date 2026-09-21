from app.providers.evidence_candidate_evaluator import EvidenceCandidateEvaluator

_COMPANY_NAMES = [
    "BOS USŁUGI BUDOWLANE MICHAŁ OMYŁA",
]


def _company_score(text: str) -> tuple[int, list[str]]:
    evaluator = EvidenceCandidateEvaluator()
    corpus = evaluator._normalize_phrase(text)

    return evaluator._company_score(
        corpus,
        company_names=_COMPANY_NAMES,
    )


def test_generic_company_tokens_do_not_identify_company() -> None:
    score, signals = _company_score(
        "Profesjonalne usługi budowlane i remontowe"
    )

    assert score == 0
    assert signals == []


def test_safe_abbreviated_company_prefix_matches() -> None:
    score, signals = _company_score(
        "BOS Usługi budowlane ul. Krokusowa 18 Pietrzykowice"
    )

    assert score == 90
    assert signals == [
        "company_abbreviated_prefix:bos uslugi budowlane"
    ]


def test_full_legal_company_name_is_exact_match() -> None:
    score, signals = _company_score(
        "BOS USŁUGI BUDOWLANE MICHAŁ OMYŁA"
    )

    assert score == 100
    assert signals == ["company_exact_phrase"]
