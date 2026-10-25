import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError
from fastapi.testclient import TestClient

from main import (
    AuditEventModel,
    AnalysisRunModel,
    Base,
    BrandRuleModel,
    DraftEditInput,
    DraftInput,
    DraftModel,
    EvidenceInput,
    EvidenceReferenceModel,
    FindingModel,
    ReviewDecisionModel,
    ReviewInput,
    add_evidence,
    analyze_submission,
    create_submission,
    edit_requested_draft,
    record_review,
    scan_content,
    DEFAULT_RULES,
    create_app,
    app as default_app,
)
from intelligence import (
    AnalysisOutput,
    ClaimFinding,
    OpenAIProvider,
    classify_provider_error,
    configured_provider,
    validate_analysis_references,
)


class MockAnalysisProvider:
    provider_name = "mock"
    model = "mock-governance-v1"

    def analyze(self, *, content, policies, evidence):
        quote = "25% growth" if "25% growth" in content else None
        return AnalysisOutput(
            summary="A factual and numerical statement needs human review." if quote else "No configured model findings.",
            findings=[
                ClaimFinding(
                    exact_quote=quote,
                    category="numerical_claim",
                    severity="medium",
                    explanation="The numerical claim needs source and context review.",
                    rationale="The source excerpt gives a number but does not establish its measurement period.",
                    policy_id=next((policy["policy_id"] for policy in policies if policy["category"] == "numerical_claim"), None),
                    evidence_status="insufficient_evidence" if evidence else "evidence_missing",
                    evidence_ids=[int(evidence[0]["evidence_id"])] if evidence else [],
                    recommended_action="Attach an existing source and confirm the measurement period.",
                    suggested_rewrite="Growth was observed during the reported period.",
                    human_review_required=True,
                )
            ] if quote else [],
            missing_information=["Measurement period and source."] if quote else [],
        )

    def answer(self, *, question, content, policies, findings, evidence):
        from intelligence import AssistantOutput

        return AssistantOutput(
            answer="The 25% figure has no supplied source excerpt. Add a source before review.",
            supporting_evidence_ids=[],
            human_review_required=True,
        )


class GovernanceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.addClassCleanup(default_app.state.engine.dispose)

    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.factory() as db:
            db.add_all(BrandRuleModel(**rule) for rule in DEFAULT_RULES)
            db.commit()

    def test_scan_flags_potential_issues_without_claiming_falsehood(self) -> None:
        with self.factory() as db:
            rules = list(db.scalars(select(BrandRuleModel)))
            results = scan_content(
                "Guaranteed returns of 25% for every customer.",
                None,
                rules,
            )

        categories = {finding["category"] for finding in results}
        self.assertEqual(categories, {"terminology", "required_term", "numerical_claim", "evidence_reference"})
        self.assertTrue(all("false" not in str(item).lower() for item in results))
        self.assertTrue(all(item["category"] for item in results))
        self.assertEqual(results[0]["matched_text"], "Guaranteed returns")

    def test_existing_evidence_reference_prevents_missing_reference_finding(self) -> None:
        with self.factory() as db:
            rules = list(db.scalars(select(BrandRuleModel)))
            results = scan_content("25% growth. Source: internal report 2026.", None, rules)
        self.assertIn("numerical_claim", {item["category"] for item in results})
        self.assertNotIn("evidence_reference", {item["category"] for item in results})

    def test_full_submission_analysis_review_and_audit_persist(self) -> None:
        with self.factory() as db:
            draft = create_submission(db, DraftInput(
                title="Launch announcement",
                author="Alex Morgan",
                channel="Website",
                content="Guaranteed returns are up 25% for all customers.",
            ))
            draft_id = draft.id
            self.assertEqual(draft.status, "Draft")

            analyzed = analyze_submission(db, draft_id)
            self.assertEqual(analyzed.status, "In review")
            self.assertGreaterEqual(len(analyzed.findings), 3)
            self.assertTrue(all(item.status == "potential_issue" for item in analyzed.findings))

            reviewed = record_review(db, draft_id, ReviewInput(
                action="approve",
                comment="Reviewed the provided source material.",
            ))
            self.assertEqual(reviewed.status, "Approved")

        with self.factory() as db:
            persisted = db.get(DraftModel, draft_id)
            self.assertIsNotNone(persisted)
            assert persisted is not None
            self.assertEqual(persisted.status, "Approved")
            self.assertIsNotNone(persisted.analyzed_at)
            self.assertEqual(len(persisted.findings), 4)
            self.assertEqual(db.scalar(select(ReviewDecisionModel).where(ReviewDecisionModel.draft_id == draft_id)).action, "approve")
            events = list(db.scalars(select(AuditEventModel).order_by(AuditEventModel.id)))
            self.assertEqual([event.action for event in events], [
                "Draft submitted", "Draft analyzed", "Submission approved",
            ])
            self.assertEqual(events[-1].details, "Reviewed the provided source material.")

    def test_input_validation_rejects_blank_or_oversized_values(self) -> None:
        with self.assertRaises(ValidationError):
            DraftInput(title=" ", author="A", channel="Web", content="test")
        with self.assertRaises(ValidationError):
            DraftInput(title="Title", author="Author", channel="Web", content="x" * 12001)

    def test_reanalysis_replaces_findings_instead_of_duplicating(self) -> None:
        with self.factory() as db:
            draft = create_submission(db, DraftInput(
                title="Metrics post",
                author="Alex Morgan",
                channel="Social media",
                content="We helped 1 million customers. Terms apply.",
                evidence_reference="Report 12, page 4",
            ))
            first = analyze_submission(db, draft.id)
            self.assertEqual(len(first.findings), 1)
            second = analyze_submission(db, draft.id)
            self.assertEqual(len(second.findings), 1)
            count = db.scalar(select(func.count()).select_from(FindingModel).where(FindingModel.draft_id == draft.id))
            self.assertEqual(count, 1)

    def test_each_review_action_records_the_expected_status(self) -> None:
        expected_statuses = {
            "approve": "Approved",
            "reject": "Rejected",
            "request_changes": "Changes requested",
        }
        with self.factory() as db:
            for action, expected_status in expected_statuses.items():
                draft = create_submission(db, DraftInput(
                    title=f"Review action {action}",
                    author="Alex Morgan",
                    channel="Website",
                    content="A draft for review.",
                ))
                analyze_submission(db, draft.id)
                updated = record_review(db, draft.id, ReviewInput(action=action))
                self.assertEqual(updated.status, expected_status)

    def test_ai_provider_results_are_saved_with_provenance_and_rewrite_proposal(self) -> None:
        with self.factory() as db:
            draft = create_submission(db, DraftInput(
                title="Metrics statement",
                author="Alex Morgan",
                channel="Website",
                content="We delivered 25% growth this year. Terms apply.",
            ))
            updated = analyze_submission(db, draft.id, MockAnalysisProvider())
            run = db.scalar(select(AnalysisRunModel).where(AnalysisRunModel.draft_id == draft.id))
            self.assertEqual(updated.analysis_runs[0].mode, "ai_assisted")
            self.assertEqual(run.outcome, "succeeded")
            self.assertEqual(run.provider, "mock")
            self.assertEqual(run.model, "mock-governance-v1")
            self.assertEqual(len(updated.proposed_edits), 1)
            self.assertEqual(updated.proposed_edits[0].status, "proposed")
            self.assertEqual(updated.proposed_edits[0].suggested_text, "Growth was observed during the reported period.")

    def test_malformed_model_quote_uses_explicit_rules_only_fallback(self) -> None:
        class MalformedProvider(MockAnalysisProvider):
            def analyze(self, *, content, policies, evidence):
                result = super().analyze(content=content, policies=policies, evidence=evidence)
                result.findings[0].exact_quote = "Invented source quote"
                return result

        with self.factory() as db:
            draft = create_submission(db, DraftInput(
                title="Malformed model result",
                author="Alex Morgan",
                channel="Website",
                content="25% growth occurred.",
            ))
            updated = analyze_submission(db, draft.id, MalformedProvider())
            self.assertEqual(updated.analysis_runs[0].mode, "rules_only")
            self.assertEqual(updated.analysis_runs[0].outcome, "provider_error")
            self.assertIn("did not complete with a valid response", updated.analysis_runs[0].payload)

    def test_provider_exceptions_fall_back_without_claiming_ai_success(self) -> None:
        class FailingProvider(MockAnalysisProvider):
            def analyze(self, *, content, policies, evidence):
                raise TimeoutError("private request body must not be stored")

        with self.factory() as db:
            draft = create_submission(db, DraftInput(
                title="Provider outage",
                author="Alex Morgan",
                channel="Website",
                content="A campaign draft.",
            ))
            updated = analyze_submission(db, draft.id, FailingProvider())
            self.assertEqual(updated.analysis_runs[0].mode, "rules_only")
            self.assertEqual(updated.analysis_runs[0].outcome, "provider_error")
            self.assertNotIn("private request body", updated.analysis_runs[0].payload)

    def test_missing_api_key_does_not_configure_provider(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(configured_provider())

    def test_openai_client_uses_a_bounded_timeout_without_retries(self) -> None:
        with patch("openai.OpenAI") as openai_client:
            OpenAIProvider("unit-test-key", "unit-test-model")._client()
        openai_client.assert_called_once_with(
            api_key="unit-test-key",
            timeout=20,
            max_retries=0,
        )

    def test_evidence_cannot_be_marked_reviewed_without_human_verification(self) -> None:
        output = MockAnalysisProvider().analyze(
            content="We delivered 25% growth.",
            policies=[{"policy_id": "1", "category": "numerical_claim", "name": "Claims", "description": "Review claims."}],
            evidence=[{"evidence_id": 10, "label": "Source", "excerpt": "25% growth", "status": "user_supplied_unverified"}],
        )
        output.findings[0].evidence_status = "supported_by_reviewed_evidence"
        validated = validate_analysis_references(
            output, content="We delivered 25% growth.", policy_ids={"1"}, evidence_ids={10},
        )
        self.assertEqual(validated.findings[0].evidence_status, "insufficient_evidence")

    def test_provider_errors_are_classified_without_returning_raw_messages(self) -> None:
        self.assertEqual(classify_provider_error(TimeoutError("sensitive request data")), "timeout")

        class AuthenticationError(Exception):
            pass

        self.assertEqual(classify_provider_error(AuthenticationError("secret")), "authentication_error")

    def test_user_supplied_evidence_remains_unverified_but_resolves_missing_source_signal(self) -> None:
        with self.factory() as db:
            draft = create_submission(db, DraftInput(
                title="Evidence coverage",
                author="Alex Morgan",
                channel="Website",
                content="25% growth was reported.",
            ))
            evidence = add_evidence(db, draft.id, EvidenceInput(
                label="Annual report excerpt",
                source_url="https://example.com/report",
                excerpt="The reported growth was 25%.",
            ))
            self.assertEqual(evidence.evidence_status, "user_supplied_unverified")
            updated = analyze_submission(db, draft.id)
            categories = {finding.category for finding in updated.findings}
            self.assertIn("numerical_claim", categories)
            self.assertNotIn("evidence_reference", categories)

    def test_request_changes_revision_creates_history_without_overwriting_prior_version(self) -> None:
        with self.factory() as db:
            draft = create_submission(db, DraftInput(
                title="Revision workflow",
                author="Alex Morgan",
                channel="Website",
                content="Draft content before review.",
            ))
            analyze_submission(db, draft.id)
            record_review(db, draft.id, ReviewInput(action="request_changes"))
            revised = edit_requested_draft(db, draft.id, DraftEditInput(
                content="Draft content after requested changes.",
                change_note="Clarified the draft as requested.",
            ))
            self.assertEqual(revised.status, "Draft")
            self.assertEqual([version.version for version in revised.versions], [1, 2])
            self.assertEqual(revised.versions[0].content, "Draft content before review.")
            self.assertEqual(revised.content, "Draft content after requested changes.")


class ApiWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database_path = Path(self.temp_dir.name) / "api-test.db"
        self.app = create_app(f"sqlite:///{database_path}", provider=MockAnalysisProvider(), initialize_schema=True)
        self.addCleanup(self.app.state.engine.dispose)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_configured_cors_origin_is_available_for_production_frontend(self) -> None:
        origin = "https://aegis-frontend.up.railway.app"
        database_path = Path(self.temp_dir.name) / "cors-test.db"
        with patch.dict("os.environ", {"AEGIS_CORS_ORIGINS": f"{origin}/"}):
            app = create_app(f"sqlite:///{database_path}", provider=MockAnalysisProvider(), initialize_schema=True)
        try:
            with TestClient(app) as client:
                response = client.options(
                    "/api/health",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "GET",
                    },
                )
            self.assertEqual(response.headers.get("access-control-allow-origin"), origin)
        finally:
            app.state.engine.dispose()

    def test_created_rule_and_initial_history_are_persisted_together(self) -> None:
        response = self.client.post("/api/brand-rules", json={
            "name": "Campaign vocabulary",
            "category": "terminology",
            "term": "best ever",
            "replacement": "",
            "description": "Review superlative language.",
            "enabled": True,
        })
        self.assertEqual(response.status_code, 201, response.text)
        rule = response.json()
        versions = self.client.get(f"/api/brand-rules/{rule['id']}/versions")
        self.assertEqual(versions.status_code, 200)
        self.assertEqual([item["version"] for item in versions.json()], [1])
        self.assertEqual(versions.json()[0]["rule"]["name"], rule["name"])
        self.assertTrue(any(
            event["action"] == "Brand rule created" and event["target_id"] == rule["id"]
            for event in self.client.get("/api/audit").json()
        ))

    def test_review_patterns_return_traceable_human_only_recommendations(self) -> None:
        draft_ids = []
        for index, action in enumerate(("approve", "reject"), start=1):
            created = self.client.post("/api/submissions", json={
                "title": f"Recurring claim {index}",
                "author": "Local reviewer",
                "channel": "Website",
                "content": "Guaranteed returns of 25% for every customer.",
            })
            self.assertEqual(created.status_code, 201, created.text)
            draft_id = created.json()["id"]
            draft_ids.append(draft_id)
            analyzed = self.client.post(f"/api/drafts/{draft_id}/analyze")
            self.assertEqual(analyzed.status_code, 200, analyzed.text)
            reviewed = self.client.post(f"/api/drafts/{draft_id}/review", json={"action": action})
            self.assertEqual(reviewed.status_code, 200, reviewed.text)

        response = self.client.get("/api/governance/learning?days=30")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["window"]["days"], 30)
        self.assertEqual(payload["basis"]["completed_decisions"], 2)
        self.assertTrue(payload["basis"]["unverified_actor_labels"])
        recommendation = next(
            item for item in payload["recommendations"]
            if item["basis"]["category"] == "terminology"
        )
        self.assertEqual(set(recommendation["basis"]["draft_ids"]), set(draft_ids))
        self.assertEqual(len(recommendation["basis"]["finding_ids"]), 2)
        self.assertTrue(recommendation["requires_human_policy_review"])
        self.assertFalse(recommendation["automatically_applied"])

        recorded = self.client.post("/api/governance/learning?days=30")
        self.assertEqual(recorded.status_code, 200, recorded.text)
        snapshot = recorded.json()
        self.assertIsInstance(snapshot["run_id"], int)
        history = self.client.get("/api/governance/learning/runs").json()
        self.assertEqual(history[0]["run_id"], snapshot["run_id"])
        self.assertEqual(history[0]["basis"]["decision_ids"], snapshot["basis"]["decision_ids"])
        self.assertTrue(any(
            event["target_type"] == "governance_learning_run" and event["target_id"] == snapshot["run_id"]
            for event in self.client.get("/api/audit").json()
        ))

    def test_health_reports_sqlite_and_migration_status_without_claiming_durability(self) -> None:
        status = self.client.get("/api/health").json()
        self.assertEqual(status["database"]["kind"], "sqlite")
        self.assertFalse(status["database"]["non_sqlite_database_configured"])
        self.assertEqual(status["database"]["durability"], "managed_database_required")

    def test_vercel_refuses_to_start_without_explicit_database_url(self) -> None:
        with patch.dict("os.environ", {"VERCEL": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AEGIS_DATABASE_URL is required on Vercel"):
                create_app()

    def test_alembic_upgrade_creates_schema_and_is_repeatable(self) -> None:
        database_path = Path(self.temp_dir.name) / "migration-test.db"
        database_url = f"sqlite:///{database_path.as_posix()}"
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.dict("os.environ", {"AEGIS_DATABASE_URL": database_url}, clear=False):
            command.upgrade(config, "head")
            command.upgrade(config, "head")
        engine = create_engine(database_url)
        try:
            inspector = inspect(engine)
            self.assertIn("alembic_version", inspector.get_table_names())
            columns = {column["name"] for column in inspector.get_columns("analysis_runs")}
            self.assertTrue({"failure_code", "evidence_version"}.issubset(columns))
            with sessionmaker(bind=engine)() as db:
                self.assertGreater(db.scalar(select(func.count()).select_from(BrandRuleModel)), 0)
        finally:
            engine.dispose()

    def test_vercel_sqlite_demo_applies_versioned_migration_and_reports_ephemeral_storage(self) -> None:
        database_path = Path(self.temp_dir.name) / "vercel-demo.db"
        database_url = f"sqlite:///{database_path.as_posix()}"
        with patch.dict("os.environ", {"VERCEL": "1", "AEGIS_DATABASE_URL": database_url}, clear=False):
            app = create_app(database_url)
        try:
            with TestClient(app) as client:
                health = client.get("/api/health").json()
                self.assertTrue(health["database"]["migrations_applied"])
                self.assertFalse(health["database"]["non_sqlite_database_configured"])
                self.assertGreater(len(client.get("/api/brand-rules").json()), 0)
        finally:
            app.state.engine.dispose()

    def test_adoption_migration_preserves_legacy_rule_and_adds_missing_columns(self) -> None:
        database_path = Path(self.temp_dir.name) / "legacy-migration.db"
        database_url = f"sqlite:///{database_path.as_posix()}"
        engine = create_engine(database_url)
        Base.metadata.create_all(
            engine,
            tables=[table for table in Base.metadata.sorted_tables if table.name != "governance_learning_runs"],
        )
        with sessionmaker(bind=engine)() as db:
            db.add(BrandRuleModel(
                name="Existing legacy rule", category="terminology", term="legacy",
                replacement="", description="Keep this policy.", enabled=True,
            ))
            db.commit()
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE analysis_runs DROP COLUMN failure_code")
            connection.exec_driver_sql("ALTER TABLE analysis_runs DROP COLUMN evidence_version")
            connection.exec_driver_sql("ALTER TABLE findings DROP COLUMN policy_id")
        engine.dispose()

        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with patch.dict("os.environ", {"AEGIS_DATABASE_URL": database_url}, clear=False):
            command.upgrade(config, "head")
        engine = create_engine(database_url)
        try:
            with sessionmaker(bind=engine)() as db:
                rule = db.scalar(select(BrandRuleModel).where(BrandRuleModel.name == "Existing legacy rule"))
                self.assertIsNotNone(rule)
                self.assertEqual(db.scalar(select(func.count()).select_from(BrandRuleModel)), 1)
            self.assertTrue({"failure_code", "evidence_version"}.issubset(
                {column["name"] for column in inspect(engine).get_columns("analysis_runs")}
            ))
            self.assertIn("policy_id", {column["name"] for column in inspect(engine).get_columns("findings")})
        finally:
            engine.dispose()

    def test_failed_initial_rule_history_write_rolls_back_the_rule(self) -> None:
        rule_input = {
            "name": "Must roll back",
            "category": "terminology",
            "term": "must not persist",
            "replacement": "",
            "description": "Used to check transaction boundaries.",
            "enabled": True,
        }
        with patch("main.record_rule_revision", side_effect=RuntimeError("revision write failed")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/brand-rules", json=rule_input)
        names = {rule["name"] for rule in self.client.get("/api/brand-rules").json()}
        self.assertNotIn(rule_input["name"], names)
        self.assertFalse(any(
            event["target_title"] == rule_input["name"]
            for event in self.client.get("/api/audit").json()
        ))

    def test_last_successful_ai_request_survives_a_later_timeout(self) -> None:
        created = self.client.post("/api/submissions", json={
            "title": "Provider status history",
            "author": "Local reviewer",
            "channel": "Website",
            "content": "We reported 25% growth.",
        })
        self.assertEqual(created.status_code, 201, created.text)
        draft_id = created.json()["id"]

        successful = self.client.post(f"/api/drafts/{draft_id}/analyze")
        self.assertEqual(successful.status_code, 200, successful.text)
        status_after_success = self.client.get("/api/intelligence/status").json()
        last_success = status_after_success["last_successful_request_at"]
        self.assertIsNotNone(last_success)

        with patch.object(self.app.state.analysis_provider, "analyze", side_effect=TimeoutError("private provider detail")):
            failed = self.client.post(f"/api/drafts/{draft_id}/analyze")
        self.assertEqual(failed.status_code, 200, failed.text)
        status_after_failure = self.client.get("/api/intelligence/status").json()
        self.assertEqual(status_after_failure["last_request_status"], "provider_error")
        self.assertFalse(status_after_failure["last_request_succeeded"])
        self.assertEqual(status_after_failure["last_successful_request_at"], last_success)

    def test_file_database_data_survives_api_app_restart_on_same_host(self) -> None:
        database_path = Path(self.temp_dir.name) / "restart-test.db"
        first_app = create_app(f"sqlite:///{database_path}", provider=MockAnalysisProvider(), initialize_schema=True)
        try:
            with TestClient(first_app) as client:
                created = client.post("/api/submissions", json={
                    "title": "Same filesystem persistence",
                    "author": "Local reviewer",
                    "channel": "Website",
                    "content": "This local record should survive an app restart.",
                })
                self.assertEqual(created.status_code, 201, created.text)
        finally:
            first_app.state.engine.dispose()

        second_app = create_app(f"sqlite:///{database_path}", provider=MockAnalysisProvider(), initialize_schema=True)
        try:
            with TestClient(second_app) as client:
                rows = client.get("/api/drafts").json()
                self.assertTrue(any(row["title"] == "Same filesystem persistence" for row in rows))
        finally:
            second_app.state.engine.dispose()

    def test_mocked_ai_evidence_rewrite_review_and_audit_workflow_over_http(self) -> None:
        created = self.client.post("/api/submissions", json={
            "title": "Spring performance campaign",
            "author": "Alex Morgan",
            "channel": "Website",
            "content": "We delivered 25% growth in 2026. Terms apply.",
            "evidence_reference": "",
        })
        self.assertEqual(created.status_code, 201, created.text)
        draft_id = created.json()["id"]

        evidence_response = self.client.post(f"/api/drafts/{draft_id}/evidence", json={
            "label": "Q2 internal report excerpt",
            "source_url": "https://example.com/q2-report",
            "excerpt": "Reported growth reached 25%.",
        })
        self.assertEqual(evidence_response.status_code, 201, evidence_response.text)
        self.assertEqual(evidence_response.json()["evidence_status"], "user_supplied_unverified")

        analyzed = self.client.post(f"/api/drafts/{draft_id}/analyze")
        self.assertEqual(analyzed.status_code, 200, analyzed.text)
        analyzed_data = analyzed.json()
        self.assertEqual(analyzed_data["analysis"]["mode"], "ai_assisted")
        self.assertEqual(analyzed_data["analysis"]["outcome"], "succeeded")
        self.assertTrue(analyzed_data["analysis"]["is_current"])
        self.assertEqual(analyzed_data["analysis"]["report"]["findings"][0]["exact_quote"], "25% growth")
        self.assertEqual(analyzed_data["analysis"]["report"]["findings"][0]["evidence_status"], "insufficient_evidence")
        self.assertEqual(analyzed_data["analysis"]["report"]["findings"][0]["evidence_ids"], [evidence_response.json()["id"]])
        self.assertTrue(any(
            finding["category"] == "numerical_claim"
            and finding["matched_text"] == "25% growth"
            for finding in self.client.get("/api/findings").json()
        ))

        assistant = self.client.post(f"/api/drafts/{draft_id}/assistant", json={
            "question": "What evidence should I review?",
        })
        self.assertEqual(assistant.status_code, 200, assistant.text)
        self.assertEqual(assistant.json()["mode"], "ai_assisted")

        requested = self.client.post(f"/api/drafts/{draft_id}/review", json={
            "action": "request_changes",
            "comment": "Clarify the time period and source.",
            "actor": "Reviewer",
        })
        self.assertEqual(requested.status_code, 200, requested.text)
        self.assertEqual(requested.json()["status"], "Changes requested")

        revised = self.client.put(f"/api/drafts/{draft_id}/content", json={
            "content": "We delivered 25% growth during 2026. Terms apply.",
            "evidence_reference": "",
            "actor": "Author",
            "change_note": "Clarified the reporting period.",
        })
        self.assertEqual(revised.status_code, 200, revised.text)
        self.assertEqual(revised.json()["versions"][-1]["version"], 2)
        self.assertEqual(revised.json()["status"], "Draft")

        reanalyzed = self.client.post(f"/api/drafts/{draft_id}/analyze")
        self.assertEqual(reanalyzed.json()["analysis"]["mode"], "ai_assisted")
        self.assertEqual(reanalyzed.json()["analysis"]["content_version"], 2)
        self.assertTrue(reanalyzed.json()["analysis"]["is_current"])

        approved = self.client.post(f"/api/drafts/{draft_id}/review", json={
            "action": "approve",
            "comment": "Reviewed the revised source reference.",
            "actor": "Reviewer",
        })
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "Approved")

        audit = self.client.get("/api/audit").json()
        actions = [item["action"] for item in audit if item["target_id"] == draft_id]
        self.assertIn("Draft revised", actions)
        self.assertIn("Governance assistant queried", actions)
        self.assertIn("Submission approved", actions)
        intelligence_status = self.client.get("/api/intelligence/status").json()
        self.assertTrue(intelligence_status["configured"])
        self.assertTrue(intelligence_status["last_request_succeeded"])
        dashboard = self.client.get("/api/dashboard").json()
        self.assertEqual(dashboard["latest_analysis_mode"], "ai_assisted")
        self.assertEqual(dashboard["review_decisions"]["request_changes"], 1)
        self.assertGreaterEqual(dashboard["unresolved_evidence_requirements"], 1)

    def test_accepted_suggestion_is_versioned_and_must_be_reanalyzed(self) -> None:
        draft_id = self.client.post("/api/submissions", json={
            "title": "Rewrite proposal",
            "author": "Alex Morgan",
            "channel": "Website",
            "content": "We delivered 25% growth. Terms apply.",
        }).json()["id"]
        analyzed = self.client.post(f"/api/drafts/{draft_id}/analyze").json()
        edit = analyzed["proposed_edits"][0]
        accepted = self.client.post(
            f"/api/drafts/{draft_id}/proposed-edits/{edit['id']}/decision",
            json={"action": "accept", "actor": "Reviewer"},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        accepted_data = accepted.json()
        self.assertIn(edit["suggested_text"], accepted_data["content"])
        self.assertEqual(accepted_data["versions"][-1]["version"], 2)
        self.assertFalse(accepted_data["analysis"]["is_current"])

        # An analysis-dependent decision cannot reuse the now-stale report.
        stale_decision = self.client.post(f"/api/drafts/{draft_id}/review", json={
            "action": "approve",
            "actor": "Reviewer",
        })
        self.assertEqual(stale_decision.status_code, 409)
        fresh = self.client.post(f"/api/drafts/{draft_id}/analyze").json()
        self.assertTrue(fresh["analysis"]["is_current"])

    def test_brand_rule_update_is_versioned_and_invalidates_old_analyses(self) -> None:
        draft_id = self.client.post("/api/submissions", json={
            "title": "Policy version workflow",
            "author": "Local reviewer",
            "channel": "Website",
            "content": "We delivered 25% growth. Terms apply.",
        }).json()["id"]
        first_analysis = self.client.post(f"/api/drafts/{draft_id}/analyze").json()
        self.assertTrue(first_analysis["analysis"]["is_current"])

        rule = next(item for item in self.client.get("/api/brand-rules").json() if item["category"] == "numerical_claim")
        changed = self.client.put(f"/api/brand-rules/{rule['id']}", json={
            "name": "Review every numerical statement",
            "category": "numerical_claim",
            "term": "",
            "replacement": "",
            "description": "Review numerical claims and their source period.",
            "enabled": True,
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        versions = self.client.get(f"/api/brand-rules/{rule['id']}/versions").json()
        self.assertEqual([version["version"] for version in versions], [2, 1])

        stale_draft = self.client.get(f"/api/drafts/{draft_id}").json()
        self.assertFalse(stale_draft["analysis"]["is_current"])
        decision = self.client.post(f"/api/drafts/{draft_id}/review", json={
            "action": "approve",
        })
        self.assertEqual(decision.status_code, 409)
        proposed_edit = self.client.get(f"/api/drafts/{draft_id}").json()["proposed_edits"][0]
        stale_edit_decision = self.client.post(
            f"/api/drafts/{draft_id}/proposed-edits/{proposed_edit['id']}/decision",
            json={"action": "accept"},
        )
        self.assertEqual(stale_edit_decision.status_code, 409)
        fresh = self.client.post(f"/api/drafts/{draft_id}/analyze").json()
        self.assertTrue(fresh["analysis"]["is_current"])

    def test_new_evidence_invalidates_analysis_and_requires_reanalysis(self) -> None:
        draft_id = self.client.post("/api/submissions", json={
            "title": "Evidence update workflow",
            "author": "Local reviewer",
            "channel": "Website",
            "content": "25% growth.",
        }).json()["id"]
        analyzed = self.client.post(f"/api/drafts/{draft_id}/analyze").json()
        self.assertTrue(analyzed["analysis"]["is_current"])
        self.client.post(f"/api/drafts/{draft_id}/evidence", json={
            "label": "New source excerpt",
            "excerpt": "A new report excerpt.",
        })
        stale = self.client.get(f"/api/drafts/{draft_id}").json()
        self.assertFalse(stale["analysis"]["is_current"])
        self.assertEqual(stale["status"], "Draft")
        fresh = self.client.post(f"/api/drafts/{draft_id}/analyze").json()
        self.assertTrue(fresh["analysis"]["is_current"])

    def test_rules_only_assistant_is_explicit_when_no_provider_is_configured(self) -> None:
        with TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True):
            app = create_app(f"sqlite:///{Path(temp_dir) / 'rules-only.db'}", initialize_schema=True)
            try:
                with TestClient(app) as client:
                    draft_id = client.post("/api/submissions", json={
                        "title": "Rules-only assistant",
                        "author": "Local reviewer",
                        "channel": "Website",
                        "content": "25% growth was reported without a source.",
                    }).json()["id"]
                    client.post(f"/api/drafts/{draft_id}/analyze")
                    response = client.post(f"/api/drafts/{draft_id}/assistant", json={
                        "question": "What evidence is missing?",
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["mode"], "rules_only")
                    self.assertEqual(response.json()["outcome"], "not_configured")
                    self.assertIsNone(response.json()["failure_code"])
                    self.assertIn("flagged a missing evidence reference", response.json()["answer"]["answer"])
            finally:
                app.state.engine.dispose()


if __name__ == "__main__":
    unittest.main()
