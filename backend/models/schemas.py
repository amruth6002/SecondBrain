"""Pydantic data models for the SecondBrain application."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta
import uuid


# --- Input Models ---

class ContentInput(BaseModel):
    """User-submitted content to process."""
    content_type: str = Field(..., description="Type: 'pdf', 'youtube', 'text'")
    text_content: Optional[str] = Field(None, description="Raw text or notes")
    youtube_url: Optional[str] = Field(None, description="YouTube video URL")
    # PDF files are handled via multipart upload, not this model


# --- Agent Output Models ---

class ExtractionPlan(BaseModel):
    """Output of the Planner Agent."""
    content_summary: str = Field(..., description="Brief summary of the input content")
    topics_to_extract: list[str] = Field(..., description="Key topics to extract")
    learning_objectives: list[str] = Field(..., description="What the student should learn")
    connections_to_find: list[str] = Field(..., description="Cross-topic connections to look for")
    difficulty_level: str = Field(default="intermediate", description="Content difficulty")
    estimated_concepts: int = Field(default=10, description="Expected number of concepts")


class Concept(BaseModel):
    """A single extracted concept."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    definition: str
    category: str = ""
    importance: str = Field(default="medium", description="low/medium/high")
    related_concepts: list[str] = Field(default_factory=list)
    source_context: str = ""


class ConceptConnection(BaseModel):
    """A connection between two concepts."""
    from_concept: str
    to_concept: str
    relationship: str
    strength: float = Field(default=0.5, ge=0.0, le=1.0)


class RetrievalResult(BaseModel):
    """Output of the Retriever Agent."""
    concepts: list[Concept] = Field(default_factory=list)
    connections: list[ConceptConnection] = Field(default_factory=list)
    key_insights: list[str] = Field(default_factory=list)


class Flashcard(BaseModel):
    """A single flashcard with spaced repetition data."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    question: str
    answer: str
    concept_id: str = ""
    bloom_level: str = Field(default="understand", description="remember/understand/apply/analyze")
    source_excerpt: str = Field(default="", description="Original text excerpt this card was derived from")
    # SM-2 spaced repetition fields
    easiness_factor: float = Field(default=2.5)
    interval: int = Field(default=1, description="Days until next review")
    repetitions: int = Field(default=0)
    next_review: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


class KnowledgeGraphNode(BaseModel):
    """Node in the knowledge graph."""
    id: str
    label: str
    category: str = ""
    importance: str = "medium"
    definition: str = ""


class KnowledgeGraphEdge(BaseModel):
    """Edge in the knowledge graph."""
    source: str
    target: str
    label: str = ""
    strength: float = 0.5


class ExecutorResult(BaseModel):
    """Output of the Executor Agent."""
    flashcards: list[Flashcard] = Field(default_factory=list)
    knowledge_graph_nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    knowledge_graph_edges: list[KnowledgeGraphEdge] = Field(default_factory=list)
    summary: str = ""
    review_schedule: dict = Field(default_factory=dict)


# --- Pipeline Models ---

class AgentMessage(BaseModel):
    """A single agent-to-agent communication message for the live feed."""
    agent: str = Field(..., description="Agent name: Planner/Retriever/Executor/System")
    receiver: str = Field(default="System", description="Agent receiving the message")
    action: str = Field(default="LOG", description="Action type like INITIATE_CHAT, PASS_CONTEXT, etc.")
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    type: str = Field(default="info", description="info/success/error/thinking")


class PipelineStatus(BaseModel):
    """Status of the agent pipeline."""
    stage: str = Field(default="idle", description="idle/planner/retriever/executor/complete/error")
    progress: float = Field(default=0.0, description="0-100 progress")
    message: str = ""
    planner_output: Optional[ExtractionPlan] = None
    retriever_output: Optional[RetrievalResult] = None
    executor_output: Optional[ExecutorResult] = None
    agent_messages: list[AgentMessage] = Field(default_factory=list)


class ProcessingResult(BaseModel):
    """Final result returned to the frontend."""
    success: bool
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    pipeline_status: PipelineStatus
    concepts: list[Concept] = Field(default_factory=list)
    flashcards: list[Flashcard] = Field(default_factory=list)
    graph_nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    graph_edges: list[KnowledgeGraphEdge] = Field(default_factory=list)
    summary: str = ""
    error: Optional[str] = None
    overlap: Optional[dict] = Field(default=None, description="Overlap with existing knowledge")


class SessionSummary(BaseModel):
    """Lightweight session info for the history sidebar."""
    id: str
    created_at: str
    title: str
    summary: str


# --- Notebook Models ---

class BlockCreate(BaseModel):
    """Input for creating a new content block."""
    block_type: str = Field(..., description="text, pdf, or youtube")
    title: str = Field(default="", description="Block title")
    content: str = Field(default="", description="Block content")


class Block(BaseModel):
    """A content block within a notebook."""
    id: str
    notebook_id: str
    block_type: str
    title: str = ""
    content: str = ""
    position: int = 0
    created_at: str = ""


class NotebookSummary(BaseModel):
    """Lightweight notebook info for the sidebar."""
    id: str
    name: str
    created_at: str
    updated_at: str
    block_count: int = 0


class NotebookDetail(BaseModel):
    """Full notebook with blocks and extracted knowledge."""
    id: str
    name: str
    created_at: str
    updated_at: str
    blocks: list[Block] = Field(default_factory=list)
    concepts: list[dict] = Field(default_factory=list)
    flashcards: list[dict] = Field(default_factory=list)
    graph_nodes: list[dict] = Field(default_factory=list)
    graph_edges: list[dict] = Field(default_factory=list)
    overlap: Optional[dict] = None
