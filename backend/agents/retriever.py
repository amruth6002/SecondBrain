"""Retriever Agent — Extracts concepts and discovers connections.

The Retriever takes the Planner's extraction plan and:
1. Extracts detailed concepts with definitions
2. Identifies relationships between concepts
3. Generates key insights
"""

from utils.llm_client import call_llm_json
from models.schemas import ExtractionPlan, RetrievalResult, Concept, ConceptConnection

RETRIEVER_SYSTEM_PROMPT = """You are the RETRIEVER AGENT in a multi-agent knowledge management system called SecondBrain.

Your role is to extract detailed concepts from educational content based on the Planner's extraction plan.

For each topic identified by the Planner, you must:
1. Extract a clear, concise concept with a definition
2. Categorize it (e.g., "definition", "theorem", "process", "example", "formula")
3. Rate its importance (low/medium/high)
4. Identify which other concepts it relates to
5. Include relevant source context

Also identify connections between concepts and generate key insights.

Respond with this exact JSON structure:
{
    "concepts": [
        {
            "name": "Concept Name",
            "definition": "Clear, student-friendly definition",
            "category": "definition|theorem|process|formula|example|principle",
            "importance": "low|medium|high",
            "related_concepts": ["Other Concept 1", "Other Concept 2"],
            "source_context": "Brief quote or reference from the original content"
        }
    ],
    "connections": [
        {
            "from_concept": "Concept A",
            "to_concept": "Concept B",
            "relationship": "How A relates to B",
            "strength": 0.8
        }
    ],
    "key_insights": [
        "An important insight about the material",
        "A connection that might not be obvious"
    ]
}

Extract 4-6 concepts. Each definition should be clear enough for a student to understand without the original text. Generate AT LEAST 4-6 connections — these are the edges in the knowledge graph and are critical for the visualization. Connections should be meaningful and directional, not trivial."""


async def run_retriever(content: str, plan: ExtractionPlan, existing_concepts: list[str] = None) -> RetrievalResult:
    """Run the Retriever Agent using the Planner's extraction plan.

    Args:
        content: Raw text content
        plan: ExtractionPlan from the Planner Agent
        existing_concepts: List of concept names the student already knows

    Returns:
        RetrievalResult with concepts, connections, and insights
    """
    max_chars = 10000
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[Content truncated]"

    existing_note = ""
    if existing_concepts:
        existing_note = (
            "\n\nEXISTING KNOWLEDGE (the student already knows these concepts):\n"
            + ", ".join(existing_concepts[:50])
            + "\n\nFor any extracted concept that overlaps with existing knowledge, "
            "prefix its source_context with 'OVERLAP:' so the system can detect it."
        )

    user_message = f"""EXTRACTION PLAN FROM PLANNER:
- Topics to extract: {', '.join(plan.topics_to_extract)}
- Learning objectives: {', '.join(plan.learning_objectives)}
- Connections to find: {', '.join(plan.connections_to_find)}
- Difficulty level: {plan.difficulty_level}{existing_note}

ORIGINAL CONTENT:
{content}

Extract concepts and connections based on the plan above."""

    result = await call_llm_json(RETRIEVER_SYSTEM_PROMPT, user_message)

    concepts = []
    for c in result.get("concepts", []):
        concepts.append(Concept(
            name=c.get("name", ""),
            definition=c.get("definition", ""),
            category=c.get("category", ""),
            importance=c.get("importance", "medium"),
            related_concepts=c.get("related_concepts", []),
            source_context=c.get("source_context", ""),
        ))

    connections = []
    for conn in result.get("connections", []):
        connections.append(ConceptConnection(
            from_concept=conn.get("from_concept", ""),
            to_concept=conn.get("to_concept", ""),
            relationship=conn.get("relationship", ""),
            strength=conn.get("strength", 0.5),
        ))

    return RetrievalResult(
        concepts=concepts,
        connections=connections,
        key_insights=result.get("key_insights", []),
    )
