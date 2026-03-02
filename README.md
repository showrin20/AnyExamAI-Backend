# AnyExamAI — Backend

FastAPI backend for generating IELTS Reading, Writing & Listening tests using Google Gemini AI, with AI-powered audio generation via Edge-TTS.

## Features

- **Reading Test Generation** — 3 passages, 40 questions, schema v2.0
- **Writing Test Generation** — Task 1 & 2 with sample responses at multiple band levels
- **Listening Test Generation** — 4 sections, 40 questions with AI-generated audio (Edge-TTS), multiple accents
- **Writing Evaluation** — AI-powered essay scoring with detailed band-level feedback
- **Gemini AI Integration** — Uses Google Gemini for all content generation
- **Async Architecture** — Full async/await, non-blocking API
- **CORS Support** — Configurable origins for frontend integration

## Quick Start

### Prerequisites

- Python 3.11+
- [Google Gemini API key](https://makersuite.google.com/app/apikey)

### Local Setup

```bash
# Clone & enter directory
cd AnyExamAI_Backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# .\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env → add your GEMINI_API_KEY

# Run
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
# Build & run
docker build -t anyexam-backend .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data anyexam-backend
```

Or with docker-compose (from the root `AnyExamAI/` directory):

```bash
docker-compose up --build backend
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/ielts/reading` | Generate reading test |
| `GET` | `/api/ielts/writing` | Generate writing test |
| `GET` | `/api/ielts/listening/generate` | Generate listening test with audio |
| `GET` | `/api/ielts/listening/tests` | List available listening tests |
| `GET` | `/api/ielts/listening/generated/{filename}` | Load a specific listening test |
| `POST` | `/api/ielts/writing/evaluate` | Evaluate a writing submission |

**Docs**: http://localhost:8000/docs

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key (**required**) | — |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `DEBUG` | Enable debug/reload mode | `false` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://localhost:5173,...` |

## Project Structure

```
├── main.py              # FastAPI entry point
├── core/
│   ├── config.py        # Pydantic settings
│   ├── exceptions.py    # Custom exceptions
│   └── gemini_client.py # Gemini API client
├── routers/
│   ├── ielts.py         # Main router (aggregates sub-routers)
│   ├── reading.py       # Reading endpoints
│   ├── writing.py       # Writing endpoints
│   ├── listening.py     # Listening endpoints
│   └── writing_evaluation.py
├── services/
│   ├── base.py          # Base service
│   ├── reading_service.py
│   ├── writing_service.py
│   ├── listening_service.py
│   └── writing_evaluation_service.py
├── schemas/             # Pydantic models
├── data/generated/      # Generated tests & audio (persisted)
├── Dockerfile
└── requirements.txt
```

## License

MIT
