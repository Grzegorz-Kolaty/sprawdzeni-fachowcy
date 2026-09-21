from pydantic import BaseModel


class EvidenceCandidateEvaluationRead(BaseModel):
    url: str

    classification: str | None

    independent_source: bool | None = None

    company_score: int | None = None
    entity_score: int | None = None
    relation_score: int | None = None
    contradiction_score: int | None = None

    signals: list[str] = []

    evidence_id: int | None = None

    error: str | None = None


class ClaimEvidenceVerificationRead(BaseModel):
    company_id: int
    claim_id: int

    status: str

    checked_count: int

    supporting_evidence_count: int
    contradicting_evidence_count: int

    evaluations: list[EvidenceCandidateEvaluationRead]
