# SecondBrain 🧠

**AI-Powered Adaptive Learning & Knowledge Graph Engine**

> *Turn any content into a connected knowledge system that teaches you how to learn — and shows you exactly how the AI did it.*

**Team MoveForward** | Microsoft AI Unlocked Hackathon 2026 | Track: Agent Teamwork

🌐 **Live App**: [secondbrain-grdydthngyc3b9a0.centralindia-01.azurewebsites.net](https://secondbrain-grdydthngyc3b9a0.centralindia-01.azurewebsites.net)

---

## What is SecondBrain?

SecondBrain is an AI-powered study platform that automatically extracts concepts from any content (text, PDF, YouTube), builds a cross-notebook **Knowledge Graph**, and tests your recall with **SM-2 spaced repetition flashcards** — all powered by a transparent multi-agent pipeline using **GPT-4o on Azure AI Foundry**.

### Key Differentiators
- **Multi-Agent AI Pipeline**: Planner → Retriever → Executor agents collaborate to extract structured knowledge
- **Cross-Notebook Knowledge Graph**: Concepts automatically link across all your notebooks
- **Guided Mastery Mode**: BFS-based deep-dive through connected concept clusters with split-pane review
- **Live Agent Wiretap**: Watch each AI agent's decision in real-time — no black box
- **SM-2 Spaced Repetition**: Proven algorithm with persistent mastery tracking

---

## Architecture

```
User Input (Text/PDF/YouTube)
        │
        ▼
┌─────────────────────────────┐
│   Multi-Agent AI Pipeline   │
│  ┌─────────┐ ┌───────────┐  │
│  │ Planner │→│ Retriever │  │     ┌──────────────────┐
│  └─────────┘ └─────┬─────┘  │◄───►│ Azure AI Foundry  │
│              ┌─────▼─────┐  │     │    (GPT-4o)       │
│              │ Executor  │  │     └──────────────────┘
│              └───────────┘  │
└──────────────┬──────────────┘
               │
               ▼
┌──────────────────────────────┐
│   Azure Cosmos DB (vCore)    │
│  Documents + Vector Index    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│   Frontend (React + Vite)    │
│  Dashboard │ Graph │ Review  │
└──────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 + Vite, D3.js / Vis.js, Vanilla CSS |
| **Backend** | Python FastAPI (async) |
| **AI / LLM** | Azure AI Foundry — GPT-4o |
| **Embeddings** | SentenceTransformers (all-MiniLM-L6-v2) |
| **Database** | Azure Cosmos DB for MongoDB (vCore) |
| **Vector Store** | Cosmos DB built-in vector index (IVF) |
| **Deployment** | Azure App Service + GitHub Actions CI/CD |

---

## Features

### 1. Multi-Agent AI Pipeline
Three specialized agents collaborate:
- **Planner**: Analyzes content structure and creates extraction strategy
- **Retriever**: Extracts concepts, resolves synonyms and coreferences
- **Executor**: Maps graph edges, generates flashcards, persists to database

### 2. Knowledge Graph
- Interactive physics-based visualization (Vis.js)
- Cross-notebook concept linking (automatic)
- Click any node to view definition, context, and source notebooks

### 3. Guided Mastery Mode
- BFS traversal discovers connected concept clusters
- Split-pane view: focused sub-graph + flashcard review
- Sequential navigation through cluster with mastery tracking

### 4. SM-2 Spaced Repetition
- Auto-generated flashcards from extracted concepts
- Full SM-2 algorithm (ease factor, interval scaling)
- Cards flagged as "Mastered" at quality ≥ 4 (persisted in DB)

### 5. AI Chat (RAG)
- Ask questions across your entire knowledge base
- Vector similarity search across concept embeddings
- Context-augmented GPT-4o responses with source tracing

### 6. Live Agent Wiretap
- Real-time streaming of each agent's decisions
- Full transparency — see what the AI understood and planned

---

## Project Structure

```
secondbrain/
├── backend/
│   ├── main.py                 # FastAPI app, routes, endpoints
│   ├── agents/
│   │   ├── planner.py          # Planner agent
│   │   ├── retriever.py        # Retriever agent
│   │   └── executor.py         # Executor agent
│   ├── services/
│   │   ├── youtube_service.py  # YouTube transcript extraction (4 strategies)
│   │   └── pdf_service.py      # PDF text extraction
│   ├── utils/
│   │   ├── database.py         # Cosmos DB operations
│   │   └── spaced_repetition.py # SM-2 algorithm
│   └── models/
│       └── schemas.py          # Pydantic models
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main app + routing
│   │   ├── components/
│   │   │   ├── KnowledgeGraph.jsx  # Graph visualization
│   │   │   ├── Flashcards.jsx      # Review + Guided Mastery
│   │   │   └── Dashboard.jsx       # Stats dashboard
│   │   └── api/
│   │       └── client.js       # API client
│   └── index.html
└── .github/
    └── workflows/
        └── deploy.yml          # CI/CD to Azure App Service
```

---

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- Azure Cosmos DB (vCore) instance
- Azure AI Foundry API key (GPT-4o)

### Backend
```bash
cd secondbrain/backend
pip install -r requirements.txt
cp .env.example .env  # Fill in your Azure credentials
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd secondbrain/frontend
npm install
npm run dev
```

---

## Deployment

Deployed via **GitHub Actions CI/CD** to **Azure App Service**.

Every push to `main` triggers:
1. Build React frontend (`npm run build`)
2. Package backend + static assets
3. Deploy to Azure App Service (zero-downtime)

---

## Team

| Member | Role |
|--------|------|
| **Amruth Tetakali** | Team Lead — Full-Stack Development, AI Integration, Architecture |

---

## License

Built for the Microsoft AI Unlocked Hackathon 2026.
