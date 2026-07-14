from __future__ import annotations


class MuyuSearchClient:
    def research_target(self, target: str) -> dict:
        return {
            "job_id": "research-target",
            "status": "unavailable",
            "artifacts": [],
            "error": "muyu-search-mcp client is not connected",
        }

    def research_recent(self, topic: str, months: int = 6) -> dict:
        return {
            "job_id": "research-recent",
            "status": "unavailable",
            "artifacts": [],
            "error": "muyu-search-mcp client is not connected",
        }
