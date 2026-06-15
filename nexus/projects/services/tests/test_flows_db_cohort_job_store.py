from django.test import SimpleTestCase, override_settings

from nexus.projects.services.flows_db_cohort_job_store import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    build_job_poll_response,
    create_job,
    get_job,
    set_job_completed,
    set_job_failed,
    set_job_running,
)


@override_settings(FLOWS_DB_COHORT_JOB_RESULT_TTL=3600)
class TestFlowsDbCohortJobStore(SimpleTestCase):
    def test_create_and_poll_lifecycle(self):
        job_id = "test-job-1"
        create_job(
            job_id,
            project_id="proj-1",
            delivery="json",
            requested_range={"from_inclusive": "a", "to_inclusive": "b"},
        )
        job = get_job(job_id)
        self.assertEqual(job["status"], STATUS_QUEUED)

        set_job_running(job_id)
        self.assertEqual(get_job(job_id)["status"], STATUS_RUNNING)

        report = {"overall_status": "aligned", "day_summaries": []}
        set_job_completed(job_id, report)
        completed = get_job(job_id)
        self.assertEqual(completed["status"], STATUS_COMPLETED)
        self.assertEqual(completed["report"], report)

        poll = build_job_poll_response(completed)
        self.assertEqual(poll["status"], STATUS_COMPLETED)
        self.assertEqual(poll["report"], report)
        self.assertNotIn("error", poll)

    def test_failed_job_includes_error(self):
        job_id = "test-job-2"
        create_job(
            job_id,
            project_id="proj-1",
            delivery="json",
            requested_range={"from_inclusive": "a", "to_inclusive": "b"},
        )
        set_job_failed(job_id, "boom")
        failed = get_job(job_id)
        self.assertEqual(failed["status"], STATUS_FAILED)

        poll = build_job_poll_response(failed)
        self.assertEqual(poll["error"], "boom")

    def test_get_missing_job_returns_none(self):
        self.assertIsNone(get_job("does-not-exist"))
