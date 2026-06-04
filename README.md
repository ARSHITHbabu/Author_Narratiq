# NarratIQ AI — v3.0

**AI-Powered Long-Form Storytelling Platform**

A full-stack web application for novelists, fiction authors, and serious storytellers.

---

## Quick Start

### 1. Start the Backend (FastAPI + SQLite)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs at: **http://localhost:8000**
API docs: **http://localhost:8000/docs**

### 2. Start the Frontend (Next.js 14)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: **http://localhost:3000**

---

## Project Structure

```
narratiq-ai/
├── backend/                    # FastAPI Python backend
│   ├── main.py                 # Entry point + all router registration
│   ├── database.py             # SQLAlchemy + SQLite setup
│   ├── models.py               # All database models
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── routers/
│   │   ├── auth.py             # Register, login, JWT auth
│   │   ├── projects.py         # Story CRUD
│   │   ├── chapters.py         # Chapter CRUD + version history
│   │   ├── intake.py           # Genre detection (AI placeholder)
│   │   ├── plot_assistant.py   # Plot suggestions (AI placeholder)
│   │   ├── ai_transform.py     # Refine, tone, emotion, translate (AI placeholders)
│   │   ├── ocr.py              # Image upload + OCR (AI placeholder)
│   │   ├── manuscript.py       # Full manuscript upload + ingestion pipeline
│   │   └── export.py           # DOCX/PDF export
│   └── services/
│       └── ai_service.py       # ALL AI model placeholders (connect models here)
│
└── frontend/                   # Next.js 14 frontend
    ├── app/
    │   ├── page.tsx            # Landing page
    │   ├── (auth)/
    │   │   ├── login/          # Login page
    │   │   └── register/       # Register page
    │   └── (dashboard)/
    │       ├── dashboard/      # Projects dashboard
    │       └── projects/[id]/
    │           ├── page.tsx    # Main editor (3-column layout)
    │           ├── intake/     # Story intake / genre detection
    │           └── analytics/  # Writing statistics
    ├── components/
    │   ├── editor/
    │   │   ├── StoryEditor.tsx      # TipTap rich text editor
    │   │   └── ChapterSidebar.tsx   # Chapter navigation
    │   ├── ai-tools/
    │   │   └── AIToolsSidebar.tsx   # Refine/Tone/Emotion/Translate/Style/Age
    │   ├── plot-assistant/
    │   │   └── PlotAssistantPanel.tsx
    │   └── ocr/
    │       └── OCRPanel.tsx
    └── lib/
        ├── api.ts              # All API calls (axios)
        ├── types.ts            # TypeScript interfaces
        └── auth.tsx            # Auth context (JWT stored in localStorage)
```

---

## AI Model Placeholders

All AI functionality is connected via stub functions in `backend/services/ai_service.py`.

Each function is marked with `# MODEL_PLACEHOLDER` and includes the exact connection details:

| Feature | Placeholder Function | Production Model |
|---------|---------------------|-----------------|
| Genre Detection | `detect_genre()` | Qwen2.5-7B-Instruct via vLLM |
| Text Refinement | `refine_text()` | Qwen2.5-7B-Instruct |
| Tone Transform | `transform_tone()` | Qwen2.5-7B-Instruct |
| Emotion Rewrite | `rewrite_emotion()` | Qwen2.5-7B-Instruct |
| Age Adaptation | `adapt_for_age()` | Qwen2.5-7B + textstat |
| Style Transform | `transform_style()` | Qwen2.5-7B-Instruct |
| Translation | `translate_text()` | Helsinki-NLP opus-mt + Qwen2.5-7B |
| AI Suggestions | `generate_suggestions()` | BGE-M3 + Qwen2.5-7B |
| Plot Assistant | `generate_plot_suggestions()` | BGE-M3 + Qwen2.5-7B + Qdrant |
| OCR Processing | `process_ocr_image()` | PaddleOCR + TrOCR + Qwen2.5-7B |
| Embeddings | `embed_text()` | BAAI/bge-m3 |
| Chapter Summary | `generate_chapter_summary()` | Qwen2.5-7B-Instruct |

### Connecting vLLM (when ready)

```python
# In ai_service.py, replace placeholder with:
import httpx

async def refine_text(text: str, mode: str = "standard", context: str = "") -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/v1/chat/completions",
            json={
                "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
                "messages": [
                    {"role": "system", "content": f"You are a literary prose editor. Mode: {mode}. {context}"},
                    {"role": "user", "content": f"Improve this text:\n\n{text}"},
                ],
                "max_tokens": 2048,
                "temperature": 0.7,
            }
        )
        return response.json()["choices"][0]["message"]["content"]
```

---

## API Routes

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Login + get JWT |
| GET | `/api/projects/` | List all stories |
| POST | `/api/projects/` | Create story |
| GET | `/api/stories/{id}/chapters` | List chapters |
| PATCH | `/api/stories/{id}/chapters/{cid}` | Auto-save chapter |
| POST | `/api/intake/{id}` | AI genre detection |
| POST | `/api/plot-assistant/` | Get plot suggestions |
| POST | `/api/ai/refine` | Refine prose |
| POST | `/api/ai/tone` | Transform tone |
| POST | `/api/ai/emotion` | Emotion rewrite |
| POST | `/api/ai/translate` | Literary translation |
| POST | `/api/ocr/extract/{id}` | OCR image upload |
| POST | `/api/manuscript/upload/{id}` | Full manuscript ingestion |
| POST | `/api/export/` | Export DOCX/PDF |

Full interactive docs at `/docs` (Swagger UI).

---

## Tech Stack

**Frontend:** Next.js 14, TypeScript, TailwindCSS, TipTap editor, Lucide icons, Radix UI  
**Backend:** FastAPI, SQLAlchemy, SQLite (dev), Pydantic v2, python-jose (JWT)  
**AI (placeholders):** Qwen2.5-7B-Instruct, BAAI/bge-m3, PaddleOCR, TrOCR, Helsinki-NLP opus-mt  
**Production DB:** PostgreSQL (swap DATABASE_URL in .env)  
**Vector DB:** Qdrant (connect in ai_service.py)  
**Inference:** vLLM (serve Qwen2.5-7B-AWQ on A10G)  

---

## Features Implemented

- [x] Landing page with feature showcase
- [x] User auth (register/login/JWT)
- [x] Projects dashboard with stats
- [x] Story Intake — AI genre detection with editable results
- [x] 3-column editor layout (Chapter Sidebar | TipTap Editor | AI Tools)
- [x] Chapter management (add, rename, delete, auto-save)
- [x] Version history (auto-saved on every chapter update)
- [x] AI Tools sidebar: Refine, Tone (9 types), Emotion (6 types), Age Adaptation, Style, Translation
- [x] AI Plot Assistant with suggestion templates
- [x] Handwritten Notes OCR panel (upload → extract → confirm → save)
- [x] Writing Analytics (word count, readability, dialogue ratio, chapter breakdown)
- [x] Full manuscript upload + background ingestion pipeline
- [x] Export to DOCX/PDF

## Phase 2 (Not Yet Built)
- [ ] Real Qdrant vector store for RAG retrieval
- [ ] BGE-M3 embedding pipeline
- [ ] Plot hole detection
- [ ] Character consistency analysis
- [ ] Emotion flow graph visualization
- [ ] TrOCR genuine handwriting OCR
- [ ] EPUB/Kindle export
