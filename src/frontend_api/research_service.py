from __future__ import annotations


class ResearchService:
    def __init__(self, muyu_client, ingestor=None) -> None:
        self.muyu_client = muyu_client
        self.ingestor = ingestor
        self._jobs: dict[str, dict] = {}

    def research_target(self, target: str) -> dict:
        job = self.muyu_client.research_target(target)
        self._jobs[job["job_id"]] = job
        return job

    def research_recent(self, topic: str, months: int = 6) -> dict:
        job = self.muyu_client.research_recent(topic, months)
        self._jobs[job["job_id"]] = job
        return job

    def ingest_research(self, job_id: str):
        if self.ingestor is None:
            raise ValueError("ingestor is required")
        return self.ingestor.ingest(job_id, self._jobs[job_id]["artifacts"])
