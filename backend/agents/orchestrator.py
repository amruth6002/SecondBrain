"""Agent Orchestrator — Runs the Planner → Retriever → Executor pipeline.

This is the central coordinator that:
1. Takes raw content input
2. Calls each agent directly via our proven LLM client
3. Tracks pipeline status for real-time UI updates
4. Returns the final ProcessingResult

AutoGen's AssistantAgent/UserProxyAgent framework is used for agent identity;
actual LLM calls go through our robust async httpx client with retry logic.
"""

import asyncio
from typing import Optional

from config import settings
from utils.llm_client import call_llm_json
from models.schemas import (
    PipelineStatus, ProcessingResult, ExtractionPlan, RetrievalResult, ExecutorResult,
    Concept, ConceptConnection, Flashcard, KnowledgeGraphNode, KnowledgeGraphEdge,
    AgentMessage,
)
from utils.spaced_repetition import calculate_next_review

# Import system prompts and agent runners
from agents.planner import PLANNER_SYSTEM_PROMPT, run_planner
from agents.retriever import RETRIEVER_SYSTEM_PROMPT, run_retriever
from agents.executor import EXECUTOR_SYSTEM_PROMPT


# Global pipeline status for SSE streaming
_current_status = PipelineStatus()
_agent_messages: list[AgentMessage] = []

def get_current_status() -> PipelineStatus:
    return _current_status

def _emit_message(agent: str, message: str, msg_type: str = "info", receiver: str = "System", action: str = "LOG"):
    """Append a new agent message and update the status object."""
    global _agent_messages
    msg = AgentMessage(agent=agent, message=message, type=msg_type, receiver=receiver, action=action)
    _agent_messages.append(msg)
    global _current_status
    _current_status = PipelineStatus(
        stage=_current_status.stage,
        progress=_current_status.progress,
        message=_current_status.message,
        planner_output=_current_status.planner_output,
        retriever_output=_current_status.retriever_output,
        executor_output=_current_status.executor_output,
        agent_messages=list(_agent_messages),
    )

def _update_status(
    stage: str,
    progress: float,
    message: str,
    planner_output: Optional[ExtractionPlan] = None,
    retriever_output: Optional[RetrievalResult] = None,
    executor_output: Optional[ExecutorResult] = None,
):
    global _current_status
    _current_status = PipelineStatus(
        stage=stage,
        progress=progress,
        message=message,
        planner_output=planner_output or _current_status.planner_output,
        retriever_output=retriever_output or _current_status.retriever_output,
        executor_output=executor_output or _current_status.executor_output,
        agent_messages=list(_agent_messages),
    )


async def run_pipeline(content: str) -> ProcessingResult:
    """
    Async multi-agent pipeline: Planner → Retriever → Executor.
    Each agent calls the LLM directly (httpx + retry) instead of AutoGen initiate_chat,
    avoiding payload/disconnect issues while keeping the live agent feed working.
    """
    global _agent_messages
    _agent_messages.clear()

    try:
        # ── STAGE 1 : PLANNER ──────────────────────────────────────────────
        _emit_message("System", "Pipeline started. Initializing agents...", "info", receiver="All", action="INIT_PIPELINE")
        _update_status("planner", 10, "Planner is analysing your content...")
        
        await asyncio.sleep(1.0)
        _emit_message("UserProxy", f"Analyzing educational content ({len(content)} chars). Please create a Knowledge Acquisition Plan.", "info", receiver="Planner", action="INITIATE_TASK")
        
        await asyncio.sleep(1.5)
        _emit_message("Planner", "Received content. Analyzing document structure and identifying key topics...", "thinking", receiver="Self", action="THINKING")

        plan = await run_planner(content, existing_concepts=existing_concept_names)

        topics_str = ", ".join(plan.topics_to_extract[:5]) if plan.topics_to_extract else "general topics"
        
        await asyncio.sleep(1.0)
        _emit_message("Planner",
            f"Analysis complete. Identified {len(plan.topics_to_extract)} topics: {topics_str}. "
            f"Difficulty: {plan.difficulty_level}.", "success", receiver="UserProxy", action="TASK_COMPLETE")
            
        await asyncio.sleep(1.5)
        _emit_message("Planner",
            f"Handing off to Retriever. Strategy map created with {len(plan.learning_objectives)} learning objectives.", "info", receiver="Retriever", action="PASS_CONTEXT")
            
        _update_status("planner", 33, f"Planner complete — found {len(plan.topics_to_extract)} topics",
                       planner_output=plan)

        # ── STAGE 2 : RETRIEVER ────────────────────────────────────────────
        _update_status("retriever", 40, "Retriever is extracting concepts...")
        
        await asyncio.sleep(1.0)
        _emit_message("Retriever",
            f"Strategy map received. Scanning content for predefined topics across {len(plan.topics_to_extract)} categories...", "thinking", receiver="Planner", action="ACKNOWLEDGE")

        retrieval = await run_retriever(content, plan, existing_concepts=existing_concept_names)

        await asyncio.sleep(1.0)
        _emit_message("Retriever",
            f"Extraction complete. Found {len(retrieval.concepts)} core concepts and "
            f"mapped {len(retrieval.connections)} relationships.", "success", receiver="System", action="LOG")
            
        await asyncio.sleep(1.5)
        _emit_message("Retriever",
            f"Passing raw knowledge graph data to Executor. Important note: {len(retrieval.key_insights)} key insights were discovered that need synthesis.", "info", receiver="Executor", action="PASS_CONTEXT")
            
        _update_status("retriever", 66,
            f"Retriever complete — extracted {len(retrieval.concepts)} concepts",
            retriever_output=retrieval)

        # ── STAGE 3 : EXECUTOR ─────────────────────────────────────────────
        _update_status("executor", 70, "Executor is generating flashcards...")
        _emit_message("Executor",
            f"Received {len(retrieval.concepts)} concepts. Generating Bloom's Taxonomy flashcards "
            f"and synthesis summary...", "thinking")

        # Build compact concept + connection text for executor
        concepts_text = "\n".join(
            f"- {c.name}: {c.definition} (importance: {c.importance})"
            for c in retrieval.concepts
        )
        connections_text = "\n".join(
            f"- {c.from_concept} → {c.to_concept}: {c.relationship}"
            for c in retrieval.connections
        )
        executor_user_msg = (
            f"EXTRACTED CONCEPTS:\n{concepts_text}\n\n"
            f"CONNECTIONS:\n{connections_text}\n\n"
            f"KEY INSIGHTS:\n" + "\n".join(f"- {i}" for i in retrieval.key_insights) +
            "\n\nGenerate flashcards and a summary based on these concepts."
        )

        executor_json = await call_llm_json(EXECUTOR_SYSTEM_PROMPT, executor_user_msg, temperature=0.3, max_tokens=4000)

        # Build flashcards with SM-2 defaults
        concept_name_to_id = {c.name: c.id for c in retrieval.concepts}
        concept_source_map = {c.name: c.source_context for c in retrieval.concepts}
        flashcards = []
        for fc in executor_json.get("flashcards", []):
            concept_id = concept_name_to_id.get(fc.get("concept_name", ""), "")
            source_excerpt = concept_source_map.get(fc.get("concept_name", ""), "")
            sm2 = calculate_next_review(quality=3)
            flashcards.append(Flashcard(
                question=fc.get("question", ""),
                answer=fc.get("answer", ""),
                concept_id=concept_id,
                bloom_level=fc.get("bloom_level", "understand"),
                source_excerpt=source_excerpt,
                **sm2,
            ))

        # Build knowledge graph (with definitions from retrieval)
        graph_nodes = [
            KnowledgeGraphNode(
                id=c.id, label=c.name, category=c.category,
                importance=c.importance, definition=c.definition,
            )
            for c in retrieval.concepts
        ]
        graph_edges = [
            KnowledgeGraphEdge(
                source=concept_name_to_id.get(conn.from_concept, conn.from_concept),
                target=concept_name_to_id.get(conn.to_concept, conn.to_concept),
                label=conn.relationship,
                strength=conn.strength,
            )
            for conn in retrieval.connections
        ]

        execution = ExecutorResult(
            flashcards=flashcards,
            knowledge_graph_nodes=graph_nodes,
            knowledge_graph_edges=graph_edges,
            summary=executor_json.get("summary", ""),
            review_schedule={"total_cards": len(flashcards)},
        )

        _emit_message("Executor",
            f"Generated {len(flashcards)} flashcards across Bloom's levels: remember, understand, apply, analyse.", "success")
        _emit_message("Executor",
            f"Built knowledge graph: {len(graph_nodes)} nodes, {len(graph_edges)} edges. Writing synthesis summary...", "info")
        # ── OVERLAP DETECTION ──
        existing_set = {n.lower() for n in existing_concept_names}
        overlap_names, new_names = [], []
        for c in retrieval.concepts:
            if c.name.lower() in existing_set or c.source_context.startswith("OVERLAP:"):
                overlap_names.append(c.name)
                if c.source_context.startswith("OVERLAP:"):
                    c.source_context = c.source_context[8:].strip()
            else:
                new_names.append(c.name)

        overlap_info = None
        if overlap_names:
            overlap_info = {
                "overlapping_concepts": overlap_names,
                "new_concepts": new_names,
                "message": f"Found {len(overlap_names)} concepts you already know",
            }
            _emit_message("System",
                f"Overlap detected — you already know: {', '.join(overlap_names[:5])}",
                "info", receiver="All", action="OVERLAP_DETECTED")

        _emit_message("System", "All agents completed successfully. Results ready.", "success")
        _update_status("executor", 100, f"Complete — {len(flashcards)} cards", executor_output=execution)
        _update_status("complete", 100, "Pipeline finished successfully!")

        return ProcessingResult(
            success=True,
            pipeline_status=_current_status,
            concepts=retrieval.concepts,
            flashcards=flashcards,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            summary=execution.summary,
            overlap=overlap_info,
        )

    except Exception as e:
        error_msg = str(e) or repr(e)
        tb = traceback.format_exc()
        print(f"[PIPELINE ERROR] {error_msg}\n{tb}")
        _emit_message("System", f"Pipeline failed: {error_msg}", "error")
        _update_status("error", 0, f"❌ Error: {error_msg}")
        return ProcessingResult(
            success=False,
            pipeline_status=_current_status,
            error=error_msg,
        )

