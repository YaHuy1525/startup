"""
CrewAI Agent definitions for the Manga Arbitrage pipeline.

Agents:
  - manager      : Director — delegates tasks, handles failures autonomously
  - scout        : Trend Scout — finds viral TikTok content
  - harvester    : YouTube Harvester — sources raw video assets
  - operator     : Publisher — uploads to TikTok with stealth
  - analyst      : Reporter — writes results to ChromaDB + dashboard
"""
import os
from dotenv import load_dotenv
load_dotenv()

try:
    from crewai import Agent, LLM
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    raise ImportError("crewai not installed. Run: pip install crewai crewai-tools")


def _make_llm() -> LLM:
    """
    Build the LLM used by all agents.
    Uses Anthropic by default (key already in container env).
    Falls back to OpenRouter if OPEN_ROUTER key is set and has credits.
    """
    anthropic_key  = os.environ.get("ANTHROPIC_API_KEY")
    openrouter_key = os.environ.get("OPEN_ROUTER") or os.environ.get("OPENROUTER_API_KEY")

    # Prefer Anthropic — it's already funded and in the container
    if anthropic_key:
        return LLM(
            model="claude-3-haiku-20240307",  # fast + cheap for agent loops
            api_key=anthropic_key,
        )
    elif openrouter_key:
        return LLM(
            model="openrouter/anthropic/claude-haiku-4.5",
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        raise EnvironmentError(
            "No LLM API key found. Set ANTHROPIC_API_KEY or OPEN_ROUTER in .env"
        )


def build_agents() -> dict:
    """Build and return all agents keyed by role name."""
    llm = _make_llm()

    manager = Agent(
        role="Pipeline Manager",
        goal=(
            "Maximize viral content output on TikTok and YouTube. "
            "Delegate tasks to specialist agents, monitor results, and autonomously "
            "handle failures — if an account is shadow-banned or hits a Captcha, "
            "quarantine it and reassign the task to a spare account."
        ),
        backstory=(
            "You are the director of a content automation pipeline. "
            "You have full visibility over all agents and make strategic decisions "
            "about content focus, account health, and upload scheduling."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=True,
    )

    scout = Agent(
        role="Trend Scout",
        goal=(
            "Find the top trending hashtags and content concepts for the user's specific goal on TikTok. "
            "Cross-reference ChromaDB memory to identify declining trends and rising ones. "
            "Output a ranked list of trending concepts with confidence scores."
        ),
        backstory=(
            "You are a social media analyst specializing in viral content arbitrage. "
            "You have deep knowledge of what makes content go viral on TikTok/Shorts and "
            "you track performance patterns over time using vector memory."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    harvester = Agent(
        role="YouTube Harvester",
        goal=(
            "Given a list of trending concepts from the Scout, find matching high-quality "
            "source videos on YouTube. Filter for: >50k views, under 3 minutes, "
            "not already in content_fingerprints. Return exact YouTube URLs."
        ),
        backstory=(
            "You are a content researcher who finds the best raw video material on YouTube "
            "for repurposing as TikTok content. You are meticulous about avoiding duplicates "
            "and always verify content quality before recommending it."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    operator = Agent(
        role="Platform Publisher",
        goal=(
            "Publish videos to TikTok and YouTube Shorts. For TikTok, use the stealth V2 pipeline "
            "(FFmpeg mutation + curl_cffi TLS bypass) first, with V1 as fallback. For YouTube Shorts, "
            "use the official API. Report precise success/failure for each platform. "
            "Identify if TikTok uploads went to 'published' or just 'drafts'."
        ),
        backstory=(
            "You are an expert platform publisher responsible for executing uploads with maximum "
            "reach and stealth. You understand the nuances of both TikTok's bot detection and "
            "YouTube's Shorts algorithm. You are meticulous about reporting whether a video is "
            "actually live (published) or just saved as a draft."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    analyst = Agent(
        role="Performance Analyst",
        goal=(
            "After each pipeline run, record all results to ChromaDB (trend performance, "
            "account health, content fingerprints). Generate a concise summary report "
            "with actionable recommendations for the next run."
        ),
        backstory=(
            "You are a data analyst who turns raw pipeline results into actionable insights. "
            "You maintain the vector memory that makes the system smarter over time, "
            "and you flag declining trends before they waste upload quota."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    return {
        "manager":   manager,
        "scout":     scout,
        "harvester": harvester,
        "operator":  operator,
        "analyst":   analyst,
    }
