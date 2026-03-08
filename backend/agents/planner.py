"""Planner Agent — Analyzes content and creates a Knowledge Acquisition Plan.

The Planner is the strategic coordinator. It receives raw content and:
1. Summarizes the content
2. Identifies key topics to extract
3. Defines learning objectives
4. Plans what connections to look for
"""

from utils.llm_client import call_llm_json
from models.schemas import ExtractionPlan

PLANNER_SYSTEM_PROMPT = """You are the PLANNER AGENT in a multi-agent knowledge management system called SecondBrain.

Your role is to analyze raw educational content and create a structured Knowledge Acquisition Plan.

Given the user's content (from a PDF, YouTube transcript, or notes), you must:
1. Summarize the content briefly
2. Identify the key topics that should be extracted as concepts
3. Define clear learning objectives
4. Suggest cross-topic connections to look for
5. Assess the difficulty level

Respond with this exact JSON structure:
{
    "content_summary": "Brief 2-3 sentence summary of the content",
    "topics_to_extract": ["topic1", "topic2", ...],
    "learning_objectives": ["After studying this, the student should be able to...", ...],
    "connections_to_find": ["How topic X relates to topic Y", ...],
    "difficulty_level": "beginner|intermediate|advanced",
    "estimated_concepts": <number>
}

Be thorough but focused. Identify 5-15 key topics. Learning objectives should use action verbs (explain, compare, implement, analyze)."""


async def run_planner(content: str, existing_concepts: list[str] = None) -> ExtractionPlan:
    """Run the Planner Agent on raw content.

    Args:
        content: Raw text content from PDF, YouTube, or user notes
        existing_concepts: List of concept names the student already knows

    Returns:
        ExtractionPlan with topics, objectives, and connections to find
    """
    # Truncate very long content to stay within token limits
    max_chars = 30000
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[Content truncated for analysis]"

    existing_note = ""
    if existing_concepts:
        existing_note = (
            "\n\nIMPORTANT CONTEXT — The student already knows these concepts from previous study:\n"
            + ", ".join(existing_concepts[:50])
            + "\n\nFocus your plan on NEW topics not yet covered. Note any overlap with existing knowledge."
        )

    user_message = f"Analyze the following educational content and create a Knowledge Acquisition Plan:{existing_note}\n\n{content}"

    result = await call_llm_json(PLANNER_SYSTEM_PROMPT, user_message)

    return ExtractionPlan(
        content_summary=result.get("content_summary", ""),
        topics_to_extract=result.get("topics_to_extract", []),
        learning_objectives=result.get("learning_objectives", []),
        connections_to_find=result.get("connections_to_find", []),
        difficulty_level=result.get("difficulty_level", "intermediate"),
        estimated_concepts=result.get("estimated_concepts", 10),
    )
