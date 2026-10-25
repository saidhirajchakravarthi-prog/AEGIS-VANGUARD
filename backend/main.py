from __future__ import annotations

import os
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, func, inspect, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from intelligence import (
    AnalysisOutput,
    AnalysisProvider,
    AssistantOutput,
    classify_provider_error,
    configured_provider,
    validate_analysis_references,
    validate_assistant_references,
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class DraftModel(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(60), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="Draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    findings: Mapped[list[FindingModel]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    decisions: Mapped[list[ReviewDecisionModel]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    analysis_runs: Mapped[list[AnalysisRunModel]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    evidence: Mapped[list[EvidenceReferenceModel]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    versions: Mapped[list[DraftVersionModel]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    proposed_edits: Mapped[list[ProposedEditModel]] = relationship(back_populates="draft", cascade="all, delete-orphan")


class FindingModel(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    policy_id: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    matched_text: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="potential_issue", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    draft: Mapped[DraftModel] = relationship(back_populates="findings")


class BrandRuleModel(Base):
    __tablename__ = "brand_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    term: Mapped[str | None] = mapped_column(String(200))
    replacement: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ReviewDecisionModel(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    draft: Mapped[DraftModel] = relationship(back_populates="decisions")


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_title: Mapped[str] = mapped_column(String(160), nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AnalysisRunModel(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(40))
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    draft: Mapped[DraftModel] = relationship(back_populates="analysis_runs")
    proposed_edits: Mapped[list[ProposedEditModel]] = relationship(back_populates="analysis_run", cascade="all, delete-orphan")


class EvidenceReferenceModel(Base):
    __tablename__ = "evidence_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    excerpt: Mapped[str | None] = mapped_column(Text)
    evidence_status: Mapped[str] = mapped_column(String(40), default="user_supplied_unverified", nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    draft: Mapped[DraftModel] = relationship(back_populates="evidence")


class DraftVersionModel(Base):
    __tablename__ = "draft_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    change_note: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    draft: Mapped[DraftModel] = relationship(back_populates="versions")


class ProposedEditModel(Base):
    __tablename__ = "proposed_edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    actor: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft: Mapped[DraftModel] = relationship(back_populates="proposed_edits")
    analysis_run: Mapped[AnalysisRunModel] = relationship(back_populates="proposed_edits")


class RuleRevisionModel(Base):
    __tablename__ = "brand_rule_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("brand_rules.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class GovernanceLearningRunModel(Base):
    __tablename__ = "governance_learning_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    window_starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    basis_json: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=2, max_length=160)
    author: str = Field(min_length=2, max_length=100)
    channel: str = Field(min_length=2, max_length=60)
    content: str = Field(min_length=5, max_length=12000)
    evidence_reference: str | None = Field(default=None, max_length=500)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["approve", "reject", "request_changes"]
    comment: str = Field(default="", max_length=2000)
    actor: str = Field(default="Local reviewer", min_length=2, max_length=100)


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=140)
    category: Literal["terminology", "required_term", "numerical_claim", "evidence_reference"]
    term: str | None = Field(default=None, max_length=200)
    replacement: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=3, max_length=1000)
    enabled: bool = True


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(min_length=2, max_length=160)
    source_url: str | None = Field(default=None, max_length=2000)
    excerpt: str | None = Field(default=None, max_length=5000)
    actor: str = Field(default="Local reviewer", min_length=2, max_length=100)


class DraftEditInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=5, max_length=12000)
    evidence_reference: str | None = Field(default=None, max_length=500)
    actor: str = Field(default="Local reviewer", min_length=2, max_length=100)
    change_note: str = Field(min_length=2, max_length=500)


class EditDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["accept", "reject"]
    actor: str = Field(default="Local reviewer", min_length=2, max_length=100)


class AssistantQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=3, max_length=500)


NUMERICAL_CLAIM = re.compile(
    r"(?:[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?\s?(?:million|billion|thousand|users|customers|percent|points|x)\b)",
    re.IGNORECASE,
)
EVIDENCE_MARKER = re.compile(r"\b(?:evidence|source|reference)\s*:", re.IGNORECASE)


def scan_content(
    content: str,
    evidence_reference: str | None,
    rules: list[BrandRuleModel],
    has_user_evidence: bool = False,
) -> list[dict[str, object]]:
    """Return deterministic potential-issue signals; never verify factual truth."""
    findings: list[dict[str, str | None]] = []
    lowered = content.casefold()
    for rule in rules:
        if not rule.enabled or not rule.term:
            continue
        term_match = re.search(re.escape(rule.term), content, re.IGNORECASE)
        if rule.category == "terminology" and term_match:
            suggestion = f" Consider “{rule.replacement}” instead." if rule.replacement else ""
            findings.append({
                "category": "terminology",
                "policy_id": rule.id,
                "severity": "medium",
                "title": f"Restricted terminology: {rule.term}",
                "description": f"This phrase is listed in your restricted terminology rules.{suggestion}",
                "matched_text": term_match.group(0),
            })
        elif rule.category == "required_term" and rule.term.casefold() not in lowered:
            findings.append({
                "category": "required_term",
                "policy_id": rule.id,
                "severity": "low",
                "title": f"Required language may be missing: {rule.term}",
                "description": "This configured phrase was not found. Confirm whether it applies to this content.",
                "matched_text": None,
            })

    numeric_match = NUMERICAL_CLAIM.search(content)
    if numeric_match and any(rule.enabled and rule.category == "numerical_claim" for rule in rules):
        numerical_rule = next(rule for rule in rules if rule.enabled and rule.category == "numerical_claim")
        findings.append({
            "category": "numerical_claim",
            "policy_id": numerical_rule.id,
            "severity": "medium",
            "title": "Numerical claim needs evidence review",
            "description": "A number-based claim was detected. A reviewer should confirm the source and context; this check does not verify the claim.",
            "matched_text": numeric_match.group(0),
        })
        has_reference = (
            bool((evidence_reference or "").strip())
            or bool(EVIDENCE_MARKER.search(content))
            or has_user_evidence
        )
        if not has_reference and any(rule.enabled and rule.category == "evidence_reference" for rule in rules):
            evidence_rule = next(rule for rule in rules if rule.enabled and rule.category == "evidence_reference")
            findings.append({
                "category": "evidence_reference",
                "policy_id": evidence_rule.id,
                "severity": "high",
                "title": "No evidence reference provided",
                "description": "A numerical claim was detected without an evidence reference. Add an existing source or confirm with a human reviewer.",
                "matched_text": numeric_match.group(0),
            })
    return findings


def _rule_dict(rule: BrandRuleModel) -> dict[str, object]:
    return {
        "id": rule.id, "name": rule.name, "category": rule.category, "term": rule.term,
        "replacement": rule.replacement, "description": rule.description, "enabled": rule.enabled,
    }


def _finding_dict(finding: FindingModel) -> dict[str, object]:
    return {
        "id": finding.id, "draft_id": finding.draft_id, "category": finding.category,
        "policy_id": finding.policy_id,
        "severity": finding.severity, "title": finding.title, "description": finding.description,
        "matched_text": finding.matched_text, "status": finding.status,
        "created_at": finding.created_at,
    }


def current_policy_version(db: Session) -> int:
    rules = list(db.scalars(select(BrandRuleModel).order_by(BrandRuleModel.id)))
    return sum(
        db.scalar(
            select(func.max(RuleRevisionModel.version)).where(RuleRevisionModel.rule_id == rule.id)
        ) or 1
        for rule in rules
    )


def _analysis_sort_key(run: AnalysisRunModel) -> tuple[datetime, int]:
    created_at = run.created_at
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at, run.id


def _latest_analysis_for_draft(draft: DraftModel) -> AnalysisRunModel | None:
    return max(draft.analysis_runs, key=_analysis_sort_key, default=None)


def _migration_status(engine) -> dict[str, object]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    inspector = inspect(engine)
    current = None
    if "alembic_version" in inspector.get_table_names():
        with engine.connect() as connection:
            current = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).scalar_one_or_none()
    return {"migrations_applied": current == head, "migration_current": current, "migration_head": head}


def latest_analysis_runs(db: Session, include_stale: bool = False) -> list[AnalysisRunModel]:
    latest_by_draft: dict[int, AnalysisRunModel] = {}
    for run in db.scalars(
        select(AnalysisRunModel).order_by(AnalysisRunModel.created_at.desc(), AnalysisRunModel.id.desc())
    ):
        latest_by_draft.setdefault(run.draft_id, run)
    latest_runs = list(latest_by_draft.values())
    if include_stale:
        return latest_runs
    policy_version = current_policy_version(db)
    current_runs: list[AnalysisRunModel] = []
    for run in latest_runs:
        draft = db.get(DraftModel, run.draft_id)
        if draft is None:
            continue
        content_version = max((version.version for version in draft.versions), default=1)
        if (
            run.content_version == content_version
            and run.evidence_version == len(draft.evidence)
            and run.policy_version == policy_version
        ):
            current_runs.append(run)
    return current_runs


def _draft_dict(draft: DraftModel, policy_version: int | None = None) -> dict[str, object]:
    latest = _latest_analysis_for_draft(draft)
    content_version = max((version.version for version in draft.versions), default=1)
    analysis = None
    if latest is not None:
        analysis = {
            "id": latest.id,
            "mode": latest.mode,
            "outcome": latest.outcome,
            "failure_code": latest.failure_code,
            "provider": latest.provider,
            "model": latest.model,
            "policy_version": latest.policy_version,
            "content_version": latest.content_version,
            "evidence_version": latest.evidence_version,
            "is_current": latest.content_version == content_version
            and latest.evidence_version == len(draft.evidence)
            and (policy_version is None or latest.policy_version == policy_version),
            "created_at": latest.created_at,
            "report": json.loads(latest.payload),
        }
    return {
        "id": draft.id, "title": draft.title, "author": draft.author, "channel": draft.channel,
        "content": draft.content, "evidence_reference": draft.evidence_reference,
        "status": draft.status, "created_at": draft.created_at, "updated_at": draft.updated_at,
        "analyzed_at": draft.analyzed_at, "finding_count": len(draft.findings),
        "findings": [_finding_dict(finding) for finding in draft.findings],
        "analysis": analysis,
        "evidence": [_evidence_dict(item) for item in sorted(draft.evidence, key=lambda item: item.id)],
        "versions": [_version_dict(item) for item in sorted(draft.versions, key=lambda item: item.version)],
        "proposed_edits": [_edit_dict(item) for item in sorted(draft.proposed_edits, key=lambda item: item.id, reverse=True)],
    }


def _evidence_dict(item: EvidenceReferenceModel) -> dict[str, object]:
    return {
        "id": item.id, "label": item.label, "source_url": item.source_url,
        "excerpt": item.excerpt, "evidence_status": item.evidence_status,
        "actor": item.actor, "created_at": item.created_at,
    }


def _version_dict(item: DraftVersionModel) -> dict[str, object]:
    return {
        "id": item.id, "version": item.version, "content": item.content,
        "actor": item.actor, "change_note": item.change_note, "created_at": item.created_at,
    }


def _edit_dict(item: ProposedEditModel) -> dict[str, object]:
    return {
        "id": item.id, "analysis_run_id": item.analysis_run_id,
        "original_text": item.original_text, "suggested_text": item.suggested_text,
        "rationale": item.rationale, "status": item.status, "actor": item.actor,
        "created_at": item.created_at, "decided_at": item.decided_at,
    }


def _audit_dict(event: AuditEventModel) -> dict[str, object]:
    return {
        "id": event.id, "action": event.action, "actor": event.actor, "target_type": event.target_type,
        "target_id": event.target_id, "target_title": event.target_title,
        "details": event.details, "created_at": event.created_at,
    }


def _get_draft(db: Session, draft_id: int) -> DraftModel:
    draft = db.get(DraftModel, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return draft


def create_submission(db: Session, data: DraftInput) -> DraftModel:
    draft = DraftModel(
        title=data.title, author=data.author, channel=data.channel, content=data.content,
        evidence_reference=data.evidence_reference or None,
    )
    db.add(draft)
    db.flush()
    if data.evidence_reference:
        db.add(EvidenceReferenceModel(
            draft_id=draft.id,
            label="Submission-provided evidence reference",
            excerpt=data.evidence_reference,
            evidence_status="user_supplied_unverified",
            actor=data.author,
        ))
    db.add(DraftVersionModel(
        draft_id=draft.id, version=1, content=draft.content, actor=data.author,
        change_note="Initial submission.",
    ))
    db.add(AuditEventModel(
        action="Draft submitted", actor=data.author, target_type="draft",
        target_id=draft.id, target_title=draft.title, details=f"Submitted to {draft.channel}.",
    ))
    db.commit()
    db.refresh(draft)
    return draft


def analyze_submission(
    db: Session,
    draft_id: int,
    provider: AnalysisProvider | None = None,
) -> DraftModel:
    draft = _get_draft(db, draft_id)
    if draft.status in ("Approved", "Rejected"):
        raise HTTPException(status_code=409, detail="A final decision has already been recorded for this submission.")
    draft.findings.clear()
    db.flush()
    rules = list(db.scalars(select(BrandRuleModel).order_by(BrandRuleModel.id)))
    evidence = list(db.scalars(
        select(EvidenceReferenceModel)
        .where(EvidenceReferenceModel.draft_id == draft.id)
        .order_by(EvidenceReferenceModel.id)
    ))
    deterministic = scan_content(
        draft.content, draft.evidence_reference, rules, has_user_evidence=bool(evidence)
    )
    for item in deterministic:
        draft.findings.append(FindingModel(draft_id=draft.id, **item))
    policies = [
        {
            "policy_id": str(rule.id),
            "name": rule.name,
            "category": rule.category,
            "term": rule.term or "",
            "description": rule.description,
        }
        for rule in rules if rule.enabled
    ]
    evidence_context: list[dict[str, object]] = [
        {
            "evidence_id": item.id,
            "label": item.label,
            "source_url": item.source_url,
            "excerpt": item.excerpt,
            "status": item.evidence_status,
        }
        for item in evidence
    ]
    active_provider = provider if provider is not None else configured_provider()
    model_name = getattr(active_provider, "model", "not-configured") if active_provider else "not-configured"
    mode = "rules_only"
    outcome = "not_configured"
    failure_code: str | None = None
    report = AnalysisOutput(
        summary="AI is not configured. Deterministic brand rules were applied; no model analysis was performed.",
        findings=[],
        missing_information=["AI analysis unavailable; a human must review claims and evidence."],
    )
    if active_provider is not None:
        try:
            report = active_provider.analyze(content=draft.content, policies=policies, evidence=evidence_context)
            report = validate_analysis_references(
                report,
                content=draft.content,
                policy_ids={item["policy_id"] for item in policies},
                evidence_ids={item.id for item in evidence},
            )
            mode = "ai_assisted"
            outcome = "succeeded"
        except Exception as error:
            outcome = "provider_error"
            failure_code = classify_provider_error(error)
            report = AnalysisOutput(
                summary="The configured AI request did not complete with a valid response. Deterministic checks were used instead.",
                findings=[],
                missing_information=["AI response unavailable; a human must review claims and evidence."],
            )
    policy_version = current_policy_version(db)
    version = db.scalar(
        select(func.max(DraftVersionModel.version)).where(DraftVersionModel.draft_id == draft.id)
    ) or 1
    run = AnalysisRunModel(
        draft_id=draft.id,
        provider=getattr(active_provider, "provider_name", "none") if active_provider else "none",
        model=model_name,
        mode=mode,
        outcome=outcome,
        failure_code=failure_code,
        policy_version=policy_version,
        content_version=version,
        evidence_version=len(evidence),
        payload=report.model_dump_json(),
    )
    db.add(run)
    db.flush()
    for finding in report.findings:
        if finding.suggested_rewrite:
            db.add(ProposedEditModel(
                draft_id=draft.id,
                analysis_run_id=run.id,
                original_text=finding.exact_quote,
                suggested_text=finding.suggested_rewrite,
                rationale=finding.recommended_action,
            ))
    draft.analyzed_at = utc_now()
    draft.updated_at = utc_now()
    draft.status = "In review"
    db.add(AuditEventModel(
        action="Draft analyzed", actor="Aegis analysis pipeline", target_type="draft",
        target_id=draft.id, target_title=draft.title,
        details=f"Mode: {mode}; outcome: {outcome}; {len(deterministic)} deterministic signal(s), "
        f"{len(report.findings)} structured claim finding(s).",
    ))
    db.commit()
    db.refresh(draft)
    return draft


def add_evidence(db: Session, draft_id: int, data: EvidenceInput) -> EvidenceReferenceModel:
    draft = _get_draft(db, draft_id)
    if draft.status in ("Approved", "Rejected"):
        raise HTTPException(status_code=409, detail="Evidence cannot be changed after a final decision.")
    if not data.source_url and not data.excerpt:
        raise HTTPException(status_code=422, detail="Provide a source URL, an excerpt, or both.")
    if data.source_url:
        from urllib.parse import urlparse

        parsed = urlparse(data.source_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=422, detail="Evidence URLs must use http or https and include a host.")
    item = EvidenceReferenceModel(
        draft_id=draft.id, label=data.label, source_url=data.source_url or None,
        excerpt=data.excerpt or None, actor=data.actor,
    )
    db.add(item)
    draft.findings.clear()
    draft.analyzed_at = None
    if draft.status == "In review":
        draft.status = "Draft"
    draft.updated_at = utc_now()
    db.add(AuditEventModel(
        action="Evidence reference added", actor=data.actor, target_type="draft",
        target_id=draft.id, target_title=draft.title,
        details=f"{data.label}; user-supplied and not independently verified.",
    ))
    db.commit()
    db.refresh(item)
    return item


def edit_requested_draft(db: Session, draft_id: int, data: DraftEditInput) -> DraftModel:
    draft = _get_draft(db, draft_id)
    if draft.status != "Changes requested":
        raise HTTPException(status_code=409, detail="Only drafts with requested changes can be edited and resubmitted.")
    latest_version = db.scalar(
        select(func.max(DraftVersionModel.version)).where(DraftVersionModel.draft_id == draft.id)
    ) or 1
    previous_reference = draft.evidence_reference
    draft.content = data.content
    draft.evidence_reference = data.evidence_reference or None
    draft.findings.clear()
    if draft.evidence_reference and draft.evidence_reference != previous_reference:
        db.add(EvidenceReferenceModel(
            draft_id=draft.id,
            label="Revised submission evidence reference",
            excerpt=draft.evidence_reference,
            evidence_status="user_supplied_unverified",
            actor=data.actor,
        ))
    draft.status = "Draft"
    draft.updated_at = utc_now()
    db.add(DraftVersionModel(
        draft_id=draft.id, version=latest_version + 1, content=draft.content,
        actor=data.actor, change_note=data.change_note,
    ))
    db.add(AuditEventModel(
        action="Draft revised", actor=data.actor, target_type="draft",
        target_id=draft.id, target_title=draft.title, details=data.change_note,
    ))
    db.commit()
    db.refresh(draft)
    return draft


def decide_proposed_edit(db: Session, edit_id: int, data: EditDecisionInput) -> DraftModel:
    edit = db.get(ProposedEditModel, edit_id)
    if edit is None:
        raise HTTPException(status_code=404, detail="Proposed edit not found.")
    draft = _get_draft(db, edit.draft_id)
    if draft.status in ("Approved", "Rejected"):
        raise HTTPException(status_code=409, detail="Edits cannot be applied after a final review decision.")
    if edit.status != "proposed":
        raise HTTPException(status_code=409, detail="This proposed edit already has a decision.")
    latest_analysis = _latest_analysis_for_draft(draft)
    current_version = max((version.version for version in draft.versions), default=1)
    if (
        latest_analysis is None
        or latest_analysis.id != edit.analysis_run_id
        or latest_analysis.content_version != current_version
        or latest_analysis.evidence_version != len(draft.evidence)
        or latest_analysis.policy_version != current_policy_version(db)
    ):
        raise HTTPException(status_code=409, detail="This suggestion belongs to a stale analysis. Re-analyze before deciding.")
    edit.status = "accepted" if data.action == "accept" else "rejected"
    edit.actor = data.actor
    edit.decided_at = utc_now()
    if data.action == "accept":
        if edit.original_text not in draft.content:
            raise HTTPException(status_code=409, detail="The quoted draft text has changed; analyze the current draft before applying this suggestion.")
        draft.content = draft.content.replace(edit.original_text, edit.suggested_text, 1)
        draft.findings.clear()
        latest_version = db.scalar(
            select(func.max(DraftVersionModel.version)).where(DraftVersionModel.draft_id == draft.id)
        ) or 1
        db.add(DraftVersionModel(
            draft_id=draft.id, version=latest_version + 1, content=draft.content,
            actor=data.actor, change_note=f"Accepted proposed edit: {edit.rationale[:400]}",
        ))
        draft.status = "Draft"
        draft.analyzed_at = None
    draft.updated_at = utc_now()
    db.add(AuditEventModel(
        action=f"Proposed edit {edit.status}", actor=data.actor, target_type="draft",
        target_id=draft.id, target_title=draft.title,
        details=f"Original: {edit.original_text[:200]} | Revision: {edit.suggested_text[:200]}",
    ))
    db.commit()
    db.refresh(draft)
    return draft


def record_rule_revision(db: Session, rule: BrandRuleModel, actor: str) -> None:
    latest = db.scalar(
        select(func.max(RuleRevisionModel.version)).where(RuleRevisionModel.rule_id == rule.id)
    ) or 0
    snapshot = _rule_dict(rule)
    db.add(RuleRevisionModel(
        rule_id=rule.id, version=latest + 1,
        snapshot=json.dumps(snapshot, ensure_ascii=False), actor=actor,
    ))


def invalidate_open_findings(db: Session) -> None:
    for draft in db.scalars(select(DraftModel).where(DraftModel.status == "In review")):
        draft.findings.clear()


def record_review(db: Session, draft_id: int, review: ReviewInput) -> DraftModel:
    draft = _get_draft(db, draft_id)
    if draft.status != "In review":
        raise HTTPException(status_code=409, detail="Only submissions in the review queue can receive a decision.")
    latest_analysis = _latest_analysis_for_draft(draft)
    current_version = max((version.version for version in draft.versions), default=1)
    if (
        latest_analysis is None
        or latest_analysis.content_version != current_version
        or latest_analysis.evidence_version != len(draft.evidence)
        or latest_analysis.policy_version != current_policy_version(db)
    ):
        raise HTTPException(status_code=409, detail="The draft or brand policies changed after analysis. Re-analyze before recording a decision.")
    status_map = {"approve": "Approved", "reject": "Rejected", "request_changes": "Changes requested"}
    action_label = {"approve": "Submission approved", "reject": "Submission rejected", "request_changes": "Changes requested"}
    draft.status = status_map[review.action]
    draft.updated_at = utc_now()
    db.add(ReviewDecisionModel(
        draft_id=draft.id, action=review.action, actor=review.actor, comment=review.comment,
    ))
    db.add(AuditEventModel(
        action=action_label[review.action], actor=review.actor, target_type="draft",
        target_id=draft.id, target_title=draft.title, details=review.comment,
    ))
    db.commit()
    db.refresh(draft)
    return draft


DEFAULT_RULES = [
    {
        "name": "Avoid guaranteed outcome language", "category": "terminology",
        "term": "guaranteed returns", "replacement": "potential returns",
        "description": "Avoid absolute promises about investment or product outcomes.",
    },
    {
        "name": "Include applicable terms notice", "category": "required_term",
        "term": "terms apply", "replacement": None,
        "description": "Check that the applicable terms notice appears in the content.",
    },
    {
        "name": "Review numerical statements", "category": "numerical_claim",
        "term": None, "replacement": None,
        "description": "Flag numbers and percentages for source and context review.",
    },
    {
        "name": "Require a source reference", "category": "evidence_reference",
        "term": None, "replacement": None,
        "description": "Ask for an existing evidence reference when numbers are present.",
    },
]


def create_app(
    database_url: str | None = None,
    provider: AnalysisProvider | None = None,
    *,
    initialize_schema: bool = False,
) -> FastAPI:
    configured_database_url = database_url or os.environ.get("AEGIS_DATABASE_URL")
    if configured_database_url is None and os.getenv("VERCEL"):
        raise RuntimeError(
            "AEGIS_DATABASE_URL is required on Vercel. Configure a managed persistent database; "
            "SQLite under /tmp is ephemeral and cannot store governance history reliably."
        )
    url = configured_database_url or f"sqlite:///{(Path(__file__).resolve().parent / 'aegis.db').as_posix()}"
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if os.getenv("VERCEL") and engine.dialect.name == "sqlite":
        # Temporary Vercel demo databases are per-instance. Use the versioned
        # migration path so a cold instance can serve the demo; this does not
        # make its records durable or suitable for governance history.
        from alembic import command
        from alembic.config import Config

        migration_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        command.upgrade(migration_config, "head")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    if initialize_schema:
        # Explicit test-only convenience; deployed/local app startup requires
        # `alembic upgrade head` and never mutates schema implicitly.
        Base.metadata.create_all(engine)
        with factory() as db:
            if db.scalar(select(func.count()).select_from(BrandRuleModel)) == 0:
                db.add_all(BrandRuleModel(**rule) for rule in DEFAULT_RULES)
                db.commit()
            rules_without_history = list(db.scalars(
                select(BrandRuleModel).where(
                    ~BrandRuleModel.id.in_(select(RuleRevisionModel.rule_id))
                )
            ))
            for rule in rules_without_history:
                record_rule_revision(db, rule, "Aegis system")
            if rules_without_history:
                db.commit()

    app = FastAPI(title="Aegis Vanguard API", version="1.0.0")
    app.state.engine = engine
    app.state.database_status = {
        "kind": engine.dialect.name,
        "persistent_database_configured": engine.dialect.name != "sqlite",
        "durability": "managed_database_required" if engine.dialect.name == "sqlite" else "external_database",
        **_migration_status(engine),
    }
    app.state.analysis_provider = provider if provider is not None else configured_provider()
    configured_origins = [
        origin.strip().rstrip("/")
        for origin in os.getenv("AEGIS_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(dict.fromkeys([
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:4173", "http://127.0.0.1:4173",
            *configured_origins,
        ])),
        allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
    )

    def get_db() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "database": app.state.database_status}

    @app.get("/api/intelligence/status")
    def intelligence_status(db: Session = Depends(get_db)) -> dict[str, object]:
        active_provider = app.state.analysis_provider
        latest = db.scalar(
            select(AnalysisRunModel).order_by(AnalysisRunModel.created_at.desc(), AnalysisRunModel.id.desc())
        )
        last_success = db.scalar(
            select(AnalysisRunModel.created_at)
            .where(AnalysisRunModel.outcome == "succeeded")
            .order_by(AnalysisRunModel.created_at.desc(), AnalysisRunModel.id.desc())
            .limit(1)
        )
        return {
            "provider": getattr(active_provider, "provider_name", "openai") if active_provider else "none",
            "model": getattr(active_provider, "model", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")) if active_provider else None,
            "configured": active_provider is not None,
            "last_request_succeeded": None if latest is None else latest.outcome == "succeeded",
            "last_request_status": latest.outcome if latest else "not_run",
            "last_failure_code": latest.failure_code if latest else None,
            "last_successful_request_at": last_success,
            "live_ai_claim": latest is not None and latest.outcome == "succeeded",
            "database": app.state.database_status,
        }

    @app.get("/api/dashboard")
    def dashboard(db: Session = Depends(get_db)) -> dict[str, object]:
        total = db.scalar(select(func.count()).select_from(DraftModel)) or 0
        in_review = db.scalar(select(func.count()).select_from(DraftModel).where(DraftModel.status == "In review")) or 0
        approved = db.scalar(select(func.count()).select_from(DraftModel).where(DraftModel.status == "Approved")) or 0
        deterministic_findings = list(db.scalars(select(FindingModel).where(FindingModel.status == "potential_issue")))
        latest_runs = latest_analysis_runs(db)
        model_findings = [
            finding
            for run in latest_runs
            for finding in json.loads(run.payload).get("findings", [])
        ]
        issue_count = len(deterministic_findings) + len(model_findings)
        reviewed = db.scalar(select(func.count()).select_from(ReviewDecisionModel)) or 0
        active_rules = db.scalar(select(func.count()).select_from(BrandRuleModel).where(BrandRuleModel.enabled.is_(True))) or 0
        approval_rate = round(approved / reviewed * 100) if reviewed else 0
        severity_counts = {
            severity: count
            for severity, count in db.execute(
                select(FindingModel.severity, func.count()).group_by(FindingModel.severity)
            )
        }
        for finding in model_findings:
            severity_counts[finding["severity"]] = severity_counts.get(finding["severity"], 0) + 1
        category_counts = {
            category: count
            for category, count in db.execute(
                select(FindingModel.category, func.count()).group_by(FindingModel.category)
            )
        }
        for finding in model_findings:
            category_counts[finding["category"]] = category_counts.get(finding["category"], 0) + 1
        decision_counts = {
            action: count
            for action, count in db.execute(
                select(ReviewDecisionModel.action, func.count()).group_by(ReviewDecisionModel.action)
            )
        }
        unresolved_evidence = sum(finding.category == "evidence_reference" for finding in deterministic_findings)
        unresolved_evidence += sum(
            finding["evidence_status"] in ("evidence_missing", "insufficient_evidence")
            for finding in model_findings
        )
        latest_analysis = db.scalar(
            select(AnalysisRunModel).order_by(AnalysisRunModel.created_at.desc(), AnalysisRunModel.id.desc())
        )
        return {
            "total_submissions": total, "in_review": in_review, "approved": approved,
            "potential_issues": issue_count, "approval_rate": approval_rate, "enabled_rules": active_rules,
            "findings_by_severity": severity_counts,
            "findings_by_category": category_counts,
            "review_decisions": decision_counts,
            "unresolved_evidence_requirements": unresolved_evidence,
            "latest_analysis_mode": latest_analysis.mode if latest_analysis else "not_run",
        }

    @app.post("/api/submissions", status_code=201)
    def submit(data: DraftInput, db: Session = Depends(get_db)) -> dict[str, object]:
        return _draft_dict(create_submission(db, data), current_policy_version(db))

    @app.get("/api/drafts")
    def drafts(
        status: str | None = Query(default=None, max_length=32),
        db: Session = Depends(get_db),
    ) -> list[dict[str, object]]:
        query = select(DraftModel).order_by(DraftModel.updated_at.desc(), DraftModel.id.desc())
        if status:
            query = query.where(DraftModel.status == status)
        return [_draft_dict(draft, current_policy_version(db)) for draft in db.scalars(query)]

    @app.get("/api/drafts/{draft_id}")
    def draft_detail(draft_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
        return _draft_dict(_get_draft(db, draft_id), current_policy_version(db))

    @app.put("/api/drafts/{draft_id}/content")
    def revise_draft(
        draft_id: int,
        data: DraftEditInput,
        db: Session = Depends(get_db),
    ) -> dict[str, object]:
        return _draft_dict(edit_requested_draft(db, draft_id, data), current_policy_version(db))

    @app.post("/api/drafts/{draft_id}/evidence", status_code=201)
    def attach_evidence(
        draft_id: int,
        data: EvidenceInput,
        db: Session = Depends(get_db),
    ) -> dict[str, object]:
        return _evidence_dict(add_evidence(db, draft_id, data))

    @app.post("/api/drafts/{draft_id}/analyze")
    def analyze(draft_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
        return _draft_dict(analyze_submission(db, draft_id, app.state.analysis_provider), current_policy_version(db))

    @app.post("/api/drafts/{draft_id}/assistant")
    def ask_assistant(
        draft_id: int,
        data: AssistantQuestion,
        db: Session = Depends(get_db),
    ) -> dict[str, object]:
        draft = _get_draft(db, draft_id)
        rules = list(db.scalars(select(BrandRuleModel).where(BrandRuleModel.enabled.is_(True))))
        policies = [
            {"policy_id": str(rule.id), "name": rule.name, "category": rule.category, "description": rule.description}
            for rule in rules
        ]
        evidence = [
            {
                "evidence_id": item.id,
                "label": item.label,
                "source_url": item.source_url,
                "excerpt": item.excerpt,
                "status": item.evidence_status,
            }
            for item in draft.evidence
        ]
        latest = _latest_analysis_for_draft(draft)
        current_version = max((version.version for version in draft.versions), default=1)
        if latest is not None and (
            latest.content_version != current_version
            or latest.evidence_version != len(draft.evidence)
            or latest.policy_version != current_policy_version(db)
        ):
            latest = None
        findings_context: list[dict[str, object]] = []
        if latest is not None:
            findings_context = json.loads(latest.payload).get("findings", [])
        active_provider = app.state.analysis_provider
        mode = "rules_only"
        outcome = "not_configured"
        failure_code: str | None = None
        question_text = data.question.casefold()
        if any(term in question_text for term in ("evidence", "source", "citation")):
            missing = [
                finding for finding in draft.findings
                if finding.category == "evidence_reference"
            ]
            if missing:
                rules_only_answer = "A deterministic check flagged a missing evidence reference: " + "; ".join(
                    finding.description for finding in missing
                )
            elif evidence:
                rules_only_answer = (
                    f"{len(evidence)} user-supplied reference(s) are attached, but none are independently "
                    "verified. Inspect the source and excerpt before relying on them."
                )
            else:
                rules_only_answer = "No evidence references are attached to this draft. Add a source URL or excerpt, then ask a reviewer to inspect it."
        elif any(term in question_text for term in ("policy", "rule", "term")):
            rules_only_answer = (
                "Active policies: " + (
                    "; ".join(f"{item['name']}: {item['description']}" for item in policies)
                    if policies else "none are configured."
                )
            )
        elif any(term in question_text for term in ("fix", "change", "approve", "review")):
            rules_only_answer = (
                f"The draft has {len(draft.findings)} deterministic potential finding(s). "
                "Review each rule signal and any source material, resolve outstanding questions, "
                "then run analysis again before recording a decision."
            )
        else:
            rules_only_answer = (
                f"This workspace is in rules-only mode. The current draft has {len(draft.findings)} "
                f"deterministic potential finding(s), {len(evidence)} user-supplied unverified evidence "
                f"reference(s), and {len(policies)} active brand rule(s). No model analysis or factual "
                "verification has occurred."
            )
        answer = AssistantOutput(
            answer=rules_only_answer,
            supporting_evidence_ids=[],
            human_review_required=True,
        )
        if active_provider is not None:
            try:
                answer = active_provider.answer(
                    question=data.question,
                    content=draft.content,
                    policies=policies,
                    findings=findings_context,
                    evidence=evidence,
                )
                answer = validate_assistant_references(
                    answer,
                    {int(item["evidence_id"]) for item in evidence},
                )
                mode = "ai_assisted"
                outcome = "succeeded"
                failure_code = None
            except Exception as error:
                outcome = "provider_error"
                failure_code = classify_provider_error(error)
                answer = AssistantOutput(
                    answer="The configured AI request did not complete with a valid response. No action was taken. Review the draft and evidence directly.",
                    supporting_evidence_ids=[],
                    human_review_required=True,
                )
        db.add(AuditEventModel(
            action="Governance assistant queried",
            actor="Local reviewer",
            target_type="draft",
            target_id=draft.id,
            target_title=draft.title,
            details=f"Mode: {mode}; outcome: {outcome}.",
        ))
        db.commit()
        return {
            "mode": mode,
            "outcome": outcome,
            "failure_code": failure_code,
            "answer": answer.model_dump(),
        }

    @app.post("/api/drafts/{draft_id}/proposed-edits/{edit_id}/decision")
    def decide_edit(
        draft_id: int,
        edit_id: int,
        data: EditDecisionInput,
        db: Session = Depends(get_db),
    ) -> dict[str, object]:
        edit = db.get(ProposedEditModel, edit_id)
        if edit is None or edit.draft_id != draft_id:
            raise HTTPException(status_code=404, detail="Proposed edit not found for this submission.")
        return _draft_dict(decide_proposed_edit(db, edit_id, data), current_policy_version(db))

    @app.get("/api/drafts/{draft_id}/versions")
    def draft_versions(draft_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
        draft = _get_draft(db, draft_id)
        return [_version_dict(item) for item in db.scalars(
            select(DraftVersionModel)
            .where(DraftVersionModel.draft_id == draft.id)
            .order_by(DraftVersionModel.version)
        )]

    @app.get("/api/drafts/{draft_id}/analyses")
    def draft_analyses(draft_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
        draft = _get_draft(db, draft_id)
        runs = db.scalars(
            select(AnalysisRunModel)
            .where(AnalysisRunModel.draft_id == draft.id)
            .order_by(AnalysisRunModel.created_at.desc(), AnalysisRunModel.id.desc())
        )
        return [
            {
                "id": run.id, "mode": run.mode, "outcome": run.outcome, "provider": run.provider,
                "failure_code": run.failure_code,
                "model": run.model, "policy_version": run.policy_version,
                "content_version": run.content_version, "created_at": run.created_at,
                "evidence_version": run.evidence_version,
                "report": json.loads(run.payload),
            }
            for run in runs
        ]

    @app.post("/api/drafts/{draft_id}/review")
    def review(draft_id: int, data: ReviewInput, db: Session = Depends(get_db)) -> dict[str, object]:
        return _draft_dict(record_review(db, draft_id, data), current_policy_version(db))

    @app.get("/api/findings")
    def findings(
        status: str = Query(default="potential_issue", max_length=32),
        db: Session = Depends(get_db),
    ) -> list[dict[str, object]]:
        query = select(FindingModel).where(FindingModel.status == status).order_by(FindingModel.created_at.desc(), FindingModel.id.desc())
        results = [_finding_dict(finding) for finding in db.scalars(query)]
        if status == "potential_issue":
            for run in latest_analysis_runs(db):
                report = json.loads(run.payload)
                for index, finding in enumerate(report.get("findings", [])):
                    results.append({
                        "id": -(run.id * 100 + index + 1),
                        "draft_id": run.draft_id,
                        "category": finding["category"],
                        "policy_id": finding.get("policy_id"),
                        "severity": finding["severity"],
                        "title": f"{finding['category'].replace('_', ' ').capitalize()} claim needs review",
                        "description": finding["explanation"],
                        "matched_text": finding["exact_quote"],
                        "status": "potential_issue",
                        "created_at": run.created_at,
                    })
        results.sort(key=lambda item: item["created_at"], reverse=True)
        return results

    @app.get("/api/brand-rules")
    def brand_rules(db: Session = Depends(get_db)) -> list[dict[str, object]]:
        return [_rule_dict(rule) for rule in db.scalars(select(BrandRuleModel).order_by(BrandRuleModel.id))]

    @app.post("/api/brand-rules", status_code=201)
    def add_brand_rule(data: RuleInput, db: Session = Depends(get_db)) -> dict[str, object]:
        if data.category in ("terminology", "required_term") and not data.term:
            raise HTTPException(status_code=422, detail="A term is required for terminology and required-language rules.")
        rule = BrandRuleModel(**data.model_dump())
        db.add(rule)
        db.flush()
        record_rule_revision(db, rule, "Local reviewer")
        db.add(AuditEventModel(
            action="Brand rule created", actor="Local reviewer", target_type="brand_rule",
            target_id=rule.id, target_title=rule.name, details=f"Created version 1 ({rule.category}).",
        ))
        invalidate_open_findings(db)
        db.commit()
        return _rule_dict(rule)

    @app.put("/api/brand-rules/{rule_id}")
    def update_brand_rule(
        rule_id: int,
        data: RuleInput,
        db: Session = Depends(get_db),
    ) -> dict[str, object]:
        rule = db.get(BrandRuleModel, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Brand rule not found.")
        if data.category in ("terminology", "required_term") and not data.term:
            raise HTTPException(status_code=422, detail="A term is required for terminology and required-language rules.")
        for key, value in data.model_dump().items():
            setattr(rule, key, value)
        db.flush()
        record_rule_revision(db, rule, "Local reviewer")
        db.add(AuditEventModel(
            action="Brand rule updated", actor="Local reviewer", target_type="brand_rule",
            target_id=rule.id, target_title=rule.name,
            details="A new version was created; existing analyses remain unchanged.",
        ))
        invalidate_open_findings(db)
        db.commit()
        db.refresh(rule)
        return _rule_dict(rule)

    @app.get("/api/brand-rules/{rule_id}/versions")
    def brand_rule_versions(rule_id: int, db: Session = Depends(get_db)) -> list[dict[str, object]]:
        if db.get(BrandRuleModel, rule_id) is None:
            raise HTTPException(status_code=404, detail="Brand rule not found.")
        revisions = db.scalars(
            select(RuleRevisionModel)
            .where(RuleRevisionModel.rule_id == rule_id)
            .order_by(RuleRevisionModel.version.desc())
        )
        return [
            {
                "version": item.version, "rule": json.loads(item.snapshot),
                "actor": item.actor, "created_at": item.created_at,
            }
            for item in revisions
        ]

    @app.get("/api/audit")
    def audit(
        limit: int = Query(default=100, ge=1, le=500),
        db: Session = Depends(get_db),
    ) -> list[dict[str, object]]:
        events = db.scalars(select(AuditEventModel).order_by(AuditEventModel.created_at.desc(), AuditEventModel.id.desc()).limit(limit))
        return [_audit_dict(event) for event in events]

    def build_learning_payload(db: Session, days: int) -> dict[str, object]:
        window_end = utc_now()
        window_start = window_end - timedelta(days=days)
        decisions = list(db.scalars(
            select(ReviewDecisionModel)
            .where(ReviewDecisionModel.created_at >= window_start)
            .order_by(ReviewDecisionModel.created_at.desc(), ReviewDecisionModel.id.desc())
        ))
        latest_by_draft: dict[int, ReviewDecisionModel] = {}
        for decision in decisions:
            latest_by_draft.setdefault(decision.draft_id, decision)
        completed = [
            decision for decision in latest_by_draft.values()
            if decision.action in {"approve", "reject"}
        ]
        completed.sort(key=lambda decision: decision.id)

        patterns: dict[tuple[int | None, str, str], dict[str, object]] = {}
        for decision in completed:
            findings = db.scalars(
                select(FindingModel).where(FindingModel.draft_id == decision.draft_id)
            )
            seen_on_draft: set[tuple[int | None, str, str]] = set()
            for finding in findings:
                key = (finding.policy_id, finding.category, finding.title)
                if key in seen_on_draft:
                    continue
                seen_on_draft.add(key)
                pattern = patterns.setdefault(key, {
                    "policy_id": finding.policy_id,
                    "category": finding.category,
                    "finding_title": finding.title,
                    "draft_ids": [],
                    "finding_ids": [],
                    "decision_ids": [],
                })
                pattern["draft_ids"].append(decision.draft_id)
                pattern["finding_ids"].append(finding.id)
                pattern["decision_ids"].append(decision.id)

        recommendations = []
        for key, pattern in sorted(patterns.items(), key=lambda item: str(item[0])):
            if len(pattern["draft_ids"]) < 2:
                continue
            rule = db.get(BrandRuleModel, key[0]) if key[0] is not None else None
            recommendations.append({
                "key": f"{key[0] or 'unlinked'}:{key[1]}:{re.sub(r'[^a-z0-9]+', '-', key[2].lower()).strip('-')}",
                "recommendation": (
                    f"Review whether the policy '{rule.name}' should be clarified for this recurring finding."
                    if rule else "Review whether a policy should address this recurring finding."
                ),
                "basis": pattern,
                "requires_human_policy_review": True,
                "automatically_applied": False,
            })

        return {
            "window": {"starts_at": window_start, "ends_at": window_end, "days": days},
            "basis": {
                "method": "latest completed approve/reject decision per draft within the selected window; recurring patterns count once per draft",
                "completed_decisions": len(completed),
                "decision_ids": [decision.id for decision in completed],
                "unverified_actor_labels": True,
            },
            "recommendations": recommendations,
            "notice": "Descriptive patterns from local review records. They do not establish causation and never change active policy.",
        }

    def learning_run_dict(run: GovernanceLearningRunModel) -> dict[str, object]:
        return {
            "run_id": run.id,
            "recorded_at": run.created_at,
            "window": {
                "starts_at": run.window_starts_at,
                "ends_at": run.window_ends_at,
                "days": run.window_days,
            },
            "basis": json.loads(run.basis_json),
            "recommendations": json.loads(run.recommendations_json),
            "notice": "Descriptive patterns from local review records. They do not establish causation and never change active policy.",
        }

    @app.get("/api/governance/learning")
    def governance_learning(
        days: int = Query(default=90, ge=1, le=365),
        db: Session = Depends(get_db),
    ) -> dict[str, object]:
        """Return a traceable preview; it records only when explicitly generated."""
        return {"run_id": None, "recorded_at": None, **build_learning_payload(db, days)}

    @app.post("/api/governance/learning")
    def record_governance_learning(
        days: int = Query(default=90, ge=1, le=365),
        db: Session = Depends(get_db),
    ) -> dict[str, object]:
        payload = build_learning_payload(db, days)
        run = GovernanceLearningRunModel(
            window_days=days,
            window_starts_at=payload["window"]["starts_at"],
            window_ends_at=payload["window"]["ends_at"],
            basis_json=json.dumps(payload["basis"]),
            recommendations_json=json.dumps(payload["recommendations"]),
        )
        db.add(run)
        db.flush()
        db.add(AuditEventModel(
            action="Governance learning snapshot recorded",
            actor="Aegis rules engine",
            target_type="governance_learning_run",
            target_id=run.id,
            target_title=f"Review patterns · {days} days",
            details=(
                f"{payload['basis']['completed_decisions']} completed decisions; "
                f"{len(payload['recommendations'])} human review suggestions."
            ),
        ))
        db.commit()
        db.refresh(run)
        return learning_run_dict(run)

    @app.get("/api/governance/learning/runs")
    def governance_learning_runs(
        limit: int = Query(default=20, ge=1, le=100),
        db: Session = Depends(get_db),
    ) -> list[dict[str, object]]:
        runs = db.scalars(
            select(GovernanceLearningRunModel)
            .order_by(GovernanceLearningRunModel.created_at.desc(), GovernanceLearningRunModel.id.desc())
            .limit(limit)
        )
        return [learning_run_dict(run) for run in runs]

    return app


app = create_app()
