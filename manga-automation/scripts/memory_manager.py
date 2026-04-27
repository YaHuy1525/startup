#!/usr/bin/env python3
"""
ChromaDB Vector Memory Manager.

Three collections:
  - trend_memory       : viral topics, view counts, performance scores
  - account_health     : per-account upload history, shadow-ban flags
  - content_fingerprints: video hashes to prevent re-uploads

Usage (standalone):
    python3 scripts/memory_manager.py --action query-trends --query "JJK manga"
    python3 scripts/memory_manager.py --action stats
"""
import os, sys, json, hashlib, argparse
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

CHROMADB_URL = os.environ.get("CHROMADB_URL", "http://localhost:8001")

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("[WARNING] chromadb not installed. Run: pip install chromadb")


def get_client():
    """Return a ChromaDB HTTP client pointed at the running container."""
    if not CHROMA_AVAILABLE:
        raise RuntimeError("chromadb package not installed")
    host = CHROMADB_URL.replace("http://", "").replace("https://", "").split(":")[0]
    port = int(CHROMADB_URL.split(":")[-1])
    # chromadb >= 1.0 uses HttpClient with tenant/database params
    try:
        return chromadb.HttpClient(host=host, port=port,
                                   tenant="default_tenant",
                                   database="default_database")
    except TypeError:
        # older API without tenant/database
        return chromadb.HttpClient(host=host, port=port)


def get_collections():
    """Get or create all three collections. Returns (trend_memory, account_health, content_fingerprints)."""
    client = get_client()
    trend_memory         = client.get_or_create_collection("trend_memory")
    account_health       = client.get_or_create_collection("account_health")
    content_fingerprints = client.get_or_create_collection("content_fingerprints")
    return trend_memory, account_health, content_fingerprints


# ---------------------------------------------------------------------------
# Trend Memory
# ---------------------------------------------------------------------------

def record_trend(hashtag: str, avg_views: int, post_count: int,
                 trend_velocity: float, region: str = "US"):
    """
    Upsert a trend entry into trend_memory.
    The document text is the hashtag so semantic search works across similar topics.
    """
    trend_memory, _, _ = get_collections()
    doc_id = f"trend_{hashtag.lstrip('#').lower()}_{region}"
    trend_memory.upsert(
        ids=[doc_id],
        documents=[hashtag],
        metadatas=[{
            "hashtag": hashtag,
            "avg_views": avg_views,
            "post_count": post_count,
            "trend_velocity": trend_velocity,
            "region": region,
            "recorded_at": datetime.utcnow().isoformat(),
        }],
    )


def query_similar_trends(query: str, n_results: int = 5) -> list:
    """
    Semantic search over trend_memory.
    Returns list of {hashtag, avg_views, trend_velocity, recorded_at}.
    """
    trend_memory, _, _ = get_collections()
    try:
        results = trend_memory.query(query_texts=[query], n_results=n_results)
        output = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            output.append({
                "hashtag": meta.get("hashtag"),
                "avg_views": meta.get("avg_views"),
                "trend_velocity": meta.get("trend_velocity"),
                "recorded_at": meta.get("recorded_at"),
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
        return output
    except Exception as e:
        print(f"[memory] query_similar_trends failed: {e}")
        return []


def get_declining_trends(min_records: int = 3) -> list:
    """
    Return trends where recent avg_views are lower than historical average.
    Used by the Trend Agent to recommend content pivots.
    """
    trend_memory, _, _ = get_collections()
    try:
        all_items = trend_memory.get(include=["metadatas"])
        # Group by hashtag, sort by recorded_at, compare first vs last avg_views
        from collections import defaultdict
        grouped = defaultdict(list)
        for meta in all_items["metadatas"]:
            grouped[meta["hashtag"]].append(meta)

        declining = []
        for hashtag, records in grouped.items():
            if len(records) < min_records:
                continue
            records.sort(key=lambda x: x["recorded_at"])
            first_views = records[0]["avg_views"]
            last_views  = records[-1]["avg_views"]
            if first_views > 0:
                change_pct = (last_views - first_views) / first_views * 100
                if change_pct < -20:  # >20% decline
                    declining.append({
                        "hashtag": hashtag,
                        "first_avg_views": first_views,
                        "latest_avg_views": last_views,
                        "change_pct": round(change_pct, 1),
                    })
        return sorted(declining, key=lambda x: x["change_pct"])
    except Exception as e:
        print(f"[memory] get_declining_trends failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Account Health
# ---------------------------------------------------------------------------

def record_upload(account_name: str, success: bool, views: int = 0,
                  shadow_banned: bool = False, platform: str = "tiktok"):
    """Record an upload attempt for an account."""
    _, account_health, _ = get_collections()
    doc_id = f"upload_{account_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    account_health.add(
        ids=[doc_id],
        documents=[f"{account_name} upload {'success' if success else 'failed'}"],
        metadatas=[{
            "account": account_name,
            "success": success,
            "views": views,
            "shadow_banned": shadow_banned,
            "platform": platform,
            "recorded_at": datetime.utcnow().isoformat(),
        }],
    )


def get_account_health(account_name: str) -> dict:
    """
    Return health summary for an account:
    {total_uploads, success_rate, avg_views, shadow_ban_count, recommendation}
    """
    _, account_health, _ = get_collections()
    try:
        results = account_health.get(
            where={"account": account_name},
            include=["metadatas"],
        )
        metas = results["metadatas"]
        if not metas:
            return {"account": account_name, "status": "no_data"}

        total     = len(metas)
        successes = sum(1 for m in metas if m.get("success"))
        views     = [m.get("views", 0) for m in metas if m.get("success")]
        bans      = sum(1 for m in metas if m.get("shadow_banned"))

        success_rate = successes / total if total else 0
        avg_views    = sum(views) / len(views) if views else 0

        if bans > 0:
            recommendation = "quarantine"
        elif success_rate < 0.5:
            recommendation = "monitor"
        else:
            recommendation = "healthy"

        return {
            "account": account_name,
            "total_uploads": total,
            "success_rate": round(success_rate, 2),
            "avg_views": round(avg_views),
            "shadow_ban_count": bans,
            "recommendation": recommendation,
        }
    except Exception as e:
        print(f"[memory] get_account_health failed: {e}")
        return {"account": account_name, "error": str(e)}


def get_quarantined_accounts() -> list:
    """Return all accounts flagged for quarantine."""
    _, account_health, _ = get_collections()
    try:
        results = account_health.get(
            where={"shadow_banned": True},
            include=["metadatas"],
        )
        accounts = list({m["account"] for m in results["metadatas"]})
        return accounts
    except Exception as e:
        print(f"[memory] get_quarantined_accounts failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Content Fingerprints
# ---------------------------------------------------------------------------

def compute_fingerprint(file_path: str) -> str:
    """MD5 hash of file content — fast enough for video files."""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_duplicate(file_path: str = None, url: str = None,
                 fingerprint: str = None) -> bool:
    """
    Check if a video has already been uploaded.
    Accepts a file path (computes hash), a YouTube URL, or a pre-computed fingerprint.
    """
    _, _, content_fingerprints = get_collections()

    if fingerprint is None:
        if file_path and os.path.exists(file_path):
            fingerprint = compute_fingerprint(file_path)
        elif url:
            fingerprint = hashlib.md5(url.encode()).hexdigest()
        else:
            return False

    try:
        results = content_fingerprints.get(ids=[fingerprint])
        return len(results["ids"]) > 0
    except Exception:
        return False


def register_content(file_path: str = None, url: str = None,
                     fingerprint: str = None, metadata: dict = None):
    """Register a video as uploaded to prevent future re-uploads."""
    _, _, content_fingerprints = get_collections()

    if fingerprint is None:
        if file_path and os.path.exists(file_path):
            fingerprint = compute_fingerprint(file_path)
        elif url:
            fingerprint = hashlib.md5(url.encode()).hexdigest()
        else:
            return

    meta = metadata or {}
    meta["registered_at"] = datetime.utcnow().isoformat()
    if url:
        meta["url"] = url
    if file_path:
        meta["file_path"] = file_path

    content_fingerprints.upsert(
        ids=[fingerprint],
        documents=[url or file_path or fingerprint],
        metadatas=[meta],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ChromaDB memory manager")
    parser.add_argument("--action", choices=[
        "stats", "query-trends", "declining-trends",
        "account-health", "check-duplicate", "register"
    ], required=True)
    parser.add_argument("--query",   help="Search query (for query-trends)")
    parser.add_argument("--account", help="Account name (for account-health)")
    parser.add_argument("--url",     help="YouTube URL (for check-duplicate / register)")
    parser.add_argument("--file",    help="Video file path (for check-duplicate / register)")
    args = parser.parse_args()

    if args.action == "stats":
        trend_memory, account_health, content_fingerprints = get_collections()
        print(json.dumps({
            "trend_memory":          trend_memory.count(),
            "account_health":        account_health.count(),
            "content_fingerprints":  content_fingerprints.count(),
        }, indent=2))

    elif args.action == "query-trends":
        if not args.query:
            print("--query required"); sys.exit(1)
        results = query_similar_trends(args.query)
        print(json.dumps(results, indent=2))

    elif args.action == "declining-trends":
        results = get_declining_trends()
        print(json.dumps(results, indent=2))

    elif args.action == "account-health":
        if not args.account:
            print("--account required"); sys.exit(1)
        result = get_account_health(args.account)
        print(json.dumps(result, indent=2))

    elif args.action == "check-duplicate":
        result = is_duplicate(file_path=args.file, url=args.url)
        print(json.dumps({"is_duplicate": result}))

    elif args.action == "register":
        register_content(file_path=args.file, url=args.url)
        print(json.dumps({"registered": True}))


if __name__ == "__main__":
    main()
