#!/usr/bin/env python3
"""
Manager-led CrewAI pipeline for manga arbitrage content.

Replaces the linear script chain with an autonomous crew that:
  1. Discovers trending content (Scout)
  2. Sources YouTube assets (Harvester)
  3. Downloads + uploads with stealth (Operator)
  4. Records results to ChromaDB (Analyst)
  5. Manager handles failures autonomously — quarantines bad accounts,
     reassigns tasks, and pivots content strategy based on memory.

Usage:
    python3 scripts/crew/pipeline_crew.py --prompt "Post 5 viral JJK manga edits today" --count 5
    python3 scripts/crew/pipeline_crew.py --prompt "Find trending One Piece content" --count 3 --dry-run
"""
import os, sys, json, argparse
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from crewai import Task, Crew, Process
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False


def build_tasks(agents: dict, prompt: str, target_count: int, dry_run: bool = False) -> list:
    """Build the task list for a pipeline run."""
    from scripts.crew.tools import (
        fetch_tiktok_trends, query_trend_memory, get_declining_trends_tool,
        source_youtube_assets, check_content_duplicate, download_pending_assets,
        upload_to_tiktok_v2, upload_to_tiktok_v1, upload_to_youtube,
        get_account_health_tool, get_available_tiktok_accounts, quarantine_account,
        record_upload_result, register_content_fingerprint,
        record_trend_performance,
    )

    task_trend_discovery = Task(
        description=(
            f"User goal: {prompt}\n\n"
            f"1. Call fetch_tiktok_trends to get current trending hashtags.\n"
            f"2. Call query_trend_memory with the main topic to check historical performance.\n"
            f"3. Call get_declining_trends to identify what to avoid.\n"
            f"4. Return a ranked list of the top {target_count} content concepts to pursue, "
            f"with reasoning based on both current trends and historical memory."
        ),
        expected_output=(
            "A JSON list of content concepts: "
            "[{\"concept\": \"...\", \"hashtag\": \"...\", \"confidence\": 0.0-1.0, \"reason\": \"...\"}]"
        ),
        agent=agents["scout"],
        tools=[fetch_tiktok_trends, query_trend_memory, get_declining_trends_tool],
    )

    task_source_assets = Task(
        description=(
            f"Based on the trending concepts or the direct user goal '{prompt}' from the Scout:\n"
            f"IMPORTANT CONSTRAINTS:\n"
            f"- If the user goal includes a specific YouTube channel URL/ID, you MUST source ONLY from that channel.\n"
            f"- In that case call source_youtube_assets(query=\"<the exact channel URL/ID from user goal>\").\n"
            f"- Do NOT substitute with unrelated trending concepts.\n"
            f"1. Iterate through the concepts.\n"
            f"2. For each, call source_youtube_assets(query=\"...\") using the concept name as the query "
            f"to ensure we get matching high-quality videos for that specific topic.\n"
            f"3. For each queued URL, call check_content_duplicate to skip already-uploaded content.\n"
            f"4. Return the list of new, non-duplicate YouTube URLs ready for download."
        ),
        expected_output=(
            "A JSON object: {\"assets_queued\": N, \"urls\": [\"https://youtube.com/...\"]}"
        ),
        agent=agents["harvester"],
        tools=[source_youtube_assets, check_content_duplicate],
        context=[task_trend_discovery],
    )

    task_download = Task(
        description=(
            f"Download the queued YouTube assets:\n"
            f"1. Call download_pending_assets with batch={target_count}.\n"
            f"2. Report how many were downloaded successfully vs failed."
        ),
        expected_output=(
            "A JSON object: {\"downloaded\": N, \"failed\": N, \"local_paths\": [\"...\"]}"
        ),
        agent=agents["harvester"],
        tools=[download_pending_assets],
        context=[task_source_assets],
    )

    upload_instructions = (
        "IMPORTANT: This is a dry run — do NOT call any upload tools. "
        "Just report what WOULD be uploaded."
    ) if dry_run else (
        "Upload the downloaded videos to both TikTok AND YouTube Shorts:\n"
        "1. For TikTok: Call get_available_tiktok_accounts. For each video, call get_account_health "
        "to verify the account is healthy. Try upload_to_tiktok_v2 first, then fallback to V1.\n"
        "2. For YouTube Shorts: Use upload_to_youtube for every video.\n"
        "3. If a TikTok account fails twice, quarantine it.\n"
        "4. After each upload (TikTok or YouTube), call record_upload_result.\n"
        "5. After each successful PUBLISHED upload (not drafts), call register_content_fingerprint.\n"
        "6. Identify and report if TikTok uploads are 'published' or only 'drafts'.\n"
        "7. Summary must show results for BOTH platforms."
    )

    task_upload = Task(
        description=upload_instructions,
        expected_output=(
            "A JSON object: {\"uploaded\": N, \"failed\": N, \"quarantined_accounts\": [], "
            "\"results\": [{\"account\": \"...\", \"success\": true, \"url\": \"...\"}]}"
        ),
        agent=agents["operator"],
        tools=[] if dry_run else [
            get_available_tiktok_accounts, get_account_health_tool,
            upload_to_tiktok_v2, upload_to_tiktok_v1, upload_to_youtube,
            quarantine_account, record_upload_result, register_content_fingerprint,
        ],
        context=[task_download],
    )

    task_report = Task(
        description=(
            f"Analyze the pipeline results and generate a report:\n"
            f"1. For each trend that was used, call record_trend_performance with the results.\n"
            f"2. Identify any patterns (e.g., which content type performed best).\n"
            f"3. Generate actionable recommendations for the next run.\n"
            f"4. Flag any accounts that should be monitored."
        ),
        expected_output=(
            "A JSON report: {\"summary\": \"...\", \"uploaded\": N, \"failed\": N, "
            "\"recommendations\": [\"...\"], \"accounts_to_monitor\": []}"
        ),
        agent=agents["analyst"],
        tools=[record_trend_performance, get_account_health_tool],
        context=[task_upload],
    )

    return [task_trend_discovery, task_source_assets, task_download, task_upload, task_report]


def run_pipeline(prompt: str, target_count: int = 5, dry_run: bool = False) -> dict:
    """
    Run the full manager-led CrewAI pipeline.
    Returns the final report from the Analyst agent.
    """
    if not CREWAI_AVAILABLE:
        return {"error": "crewai not installed. Run: pip install crewai crewai-tools"}

    from scripts.crew.agents import build_agents

    print(f"\n{'='*60}")
    print(f"  CrewAI Pipeline Starting")
    print(f"  Prompt: {prompt}")
    print(f"  Target: {target_count} uploads")
    print(f"  Dry run: {dry_run}")
    print(f"{'='*60}\n")

    agents = build_agents()
    tasks  = build_tasks(agents, prompt, target_count, dry_run)

    # In sequential mode, all agents run tasks explicitly as defined
    worker_agents = [agents["manager"], agents["scout"], agents["harvester"], agents["operator"], agents["analyst"]]

    crew = Crew(
        agents=worker_agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        max_rpm=10,          # rate limit LLM calls
        memory=False,        # we use ChromaDB for memory, not CrewAI's built-in
    )

    result = crew.kickoff()

    # Parse the final output
    try:
        final_output = result.raw if hasattr(result, "raw") else str(result)
        # Try to extract JSON from the output
        import re
        json_match = re.search(r'\{.*\}', final_output, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"summary": final_output}
    except Exception:
        return {"summary": str(result)}


def main():
    parser = argparse.ArgumentParser(description="Run the CrewAI manga arbitrage pipeline")
    parser.add_argument("--prompt",  required=True, help="Natural language goal for the crew")
    parser.add_argument("--count",   type=int, default=5, help="Target number of uploads")
    parser.add_argument("--dry-run", action="store_true", help="Plan only, no actual uploads")
    args = parser.parse_args()

    result = run_pipeline(args.prompt, args.count, args.dry_run)
    print("\n" + "="*60)
    print("PIPELINE RESULT:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
