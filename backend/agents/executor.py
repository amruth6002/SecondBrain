"""Executor Agent — Generates flashcards, knowledge graph, and review schedule.

The Executor takes the Retriever's extracted concepts and:
1. Generates flashcards using Bloom's taxonomy
2. Builds knowledge graph nodes and edges
3. Creates a spaced repetition review schedule
"""

from utils.llm_client import call_llm_json
from utils.spaced_repetition import calculate_next_review
from models.schemas import (
    RetrievalResult, ExecutorResult,
    Flashcard, KnowledgeGraphNode, KnowledgeGraphEdge,
)

EXECUTOR_SYSTEM_PROMPT = """You are the EXECUTOR AGENT in a multi-agent knowledge management system called SecondBrain.

Your role is to transform extracted concepts into actionable learning materials.

Given extracted concepts and their connections, you must generate:

1. FLASHCARDS using Bloom's Taxonomy levels:
   - "remember": Basic recall (What is X?)
   - "understand": Explain in own words (Explain how X works)
   - "apply": Use knowledge (Given scenario Y, how would you apply X?)
   - "analyze": Break down and examine (Compare X and Y, What would happen if...?)

   Generate 1-2 flashcards per concept, varying the Bloom's level.

2. A SUMMARY of the material (2-3 paragraphs, student-friendly)

Respond with this exact JSON structure:
{
    "flashcards": [
        {
            "question": "Clear, specific question",
            "answer": "Concise but complete answer",
            "concept_name": "Which concept this tests",
            "bloom_level": "remember|understand|apply|analyze"
        }
    ],
    "summary": "2-3 paragraph summary of all the material, written for a student"
}

Make flashcards that TEST understanding, not just definitions. Include application and analysis questions. Answers should be complete but concise (2-4 sentences)."""


async def run_executor(retrieval: RetrievalResult) -> ExecutorResult:
    """Run the Executor Agent on extracted concepts.

    Args:
        retrieval: RetrievalResult from the Retriever Agent

    Returns:
        ExecutorResult with flashcards, knowledge graph, and review schedule
    """
    # Build concept descriptions for the LLM
    concepts_text = "\n".join(
        f"- {c.name}: {c.definition} (importance: {c.importance})"
        for c in retrieval.concepts
    )

    connections_text = "\n".join(
        f"- {c.from_concept} → {c.to_concept}: {c.relationship}"
        for c in retrieval.connections
    )

    user_message = f"""EXTRACTED CONCEPTS:
{concepts_text}

CONNECTIONS:
{connections_text}

KEY INSIGHTS:
{chr(10).join('- ' + i for i in retrieval.key_insights)}

Generate flashcards and a summary based on these concepts."""

    result = await call_llm_json(EXECUTOR_SYSTEM_PROMPT, user_message)

    # Build flashcards with SM-2 defaults
    flashcards = []
    concept_name_to_id = {c.name: c.id for c in retrieval.concepts}

    for fc in result.get("flashcards", []):
        concept_name = fc.get("concept_name", "")
        concept_id = concept_name_to_id.get(concept_name, "")

        sm2 = calculate_next_review(quality=3)  # Initial: correct with difficulty

        flashcards.append(Flashcard(
            question=fc.get("question", ""),
            answer=fc.get("answer", ""),
            concept_id=concept_id,
            bloom_level=fc.get("bloom_level", "understand"),
            easiness_factor=sm2["easiness_factor"],
            interval=sm2["interval"],
            repetitions=sm2["repetitions"],
            next_review=sm2["next_review"],
        ))

    # Build knowledge graph from concepts and connections
    graph_nodes = []
    for concept in retrieval.concepts:
        graph_nodes.append(KnowledgeGraphNode(
            id=concept.id,
            label=concept.name,
            category=concept.category,
            importance=concept.importance,
        ))

    graph_edges = []
    for conn in retrieval.connections:
        # Find node IDs by concept name
        source_id = concept_name_to_id.get(conn.from_concept, conn.from_concept)
        target_id = concept_name_to_id.get(conn.to_concept, conn.to_concept)
        graph_edges.append(KnowledgeGraphEdge(
            source=source_id,
            target=target_id,
            label=conn.relationship,
            strength=conn.strength,
        ))

    # Build review schedule
    review_schedule = {
        "today": len([f for f in flashcards if f.interval <= 1]),
        "tomorrow": len([f for f in flashcards if f.interval == 1]),
        "this_week": len(flashcards),
        "total_cards": len(flashcards),
    }

    return ExecutorResult(
        flashcards=flashcards,
        knowledge_graph_nodes=graph_nodes,
        knowledge_graph_edges=graph_edges,
        summary=result.get("summary", ""),
        review_schedule=review_schedule,
    )
