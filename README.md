# IELTS Test Generation API - Backend

A production-ready FastAPI backend for generating IELTS Reading and Writing tests using Google's Gemini AI.

## Features

- **IELTS Reading Test Generation**: Generate complete IELTS Academic Reading tests with 3 passages and 40 questions
- **IELTS Writing Test Generation**: Generate IELTS Writing tests with 2 tasks and sample responses at different band levels
- **Schema Compliance**: Reading tests follow IELTS schema v2.0, Writing tests follow schema v3.0
- **Clean Architecture**: Modular structure with services, routers, schemas, and core modules
- **Error Handling**: Comprehensive error handling with proper HTTP status codes
- **CORS Support**: Configurable CORS for frontend integration
- **Async Support**: Full async/await support for non-blocking API calls

## Project Structure

```
Backend/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variables template
├── README.md              # This file
├── core/
│   ├── __init__.py
│   ├── config.py          # Application configuration (Pydantic Settings)
│   ├── exceptions.py      # Custom exceptions
│   └── gemini_client.py   # Gemini API client wrapper
├── routers/
│   ├── __init__.py
│   ├── ielts.py           # Main IELTS router (aggregates sub-routers)
│   ├── reading.py         # Reading test endpoints
│   └── writing.py         # Writing test endpoints
├── schemas/
│   ├── __init__.py
│   ├── reading.py         # Reading test Pydantic models
│   └── writing.py         # Writing test Pydantic models
└── services/
    ├── __init__.py
    ├── base.py            # Base service with common functionality
    ├── reading_service.py # Reading test generation service
    └── writing_service.py # Writing test generation service
```

## Installation

### 1. Create a virtual environment

```bash
cd Backend
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
.\venv\Scripts\activate  # On Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key:

```env
GEMINI_API_KEY=your-gemini-api-key-here
```

You can get a Gemini API key from: https://makersuite.google.com/app/apikey

## Running the Server

### Development mode

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Using Python directly

```bash
python main.py
```

## API Endpoints

### Health Check

```
GET /health
```

Returns the health status of the API.

### Generate Reading Test

```
GET /api/ielts/reading
```

Query Parameters:
- `topics` (optional): List of 3 topics for passages. Example: `?topics=Marine Biology&topics=AI&topics=Climate`
- `difficulty` (optional): Target IELTS band (5.0-9.0). Default: `7.0`

Example:
```bash
curl "http://localhost:8000/api/ielts/reading?difficulty=7.0"
```

### Generate Writing Test

```
GET /api/ielts/writing
```

Query Parameters:
- `module` (optional): "Academic" or "General Training". Default: `Academic`
- `difficulty` (optional): Target IELTS band (5.0-9.0). Default: `7.0`

Example:
```bash
curl "http://localhost:8000/api/ielts/writing?module=Academic&difficulty=7.0"
```

## Response Format

All endpoints return **raw structured IELTS test JSON** that can be directly used by the frontend.

**No wrapper object** like:
```json
{
  "status": "success",
  "data": {...}
}
```

Instead, the exam JSON is returned directly:

### Reading Test Response

```json
{
  "test_type": "IELTS Academic",
  "total_questions": 40,
  "total_duration_minutes": 60,
  "test_metadata": {
    "schema_version": "2.0",
    "generated_at": "2026-02-24T10:00:00",
    "difficulty_band": "7.0",
    "test_source": "AI Generated Practice Test"
  },
  "passages": [...],
  "answer_key": {...}
}
```

### Writing Test Response

```json
{
  "test_name": "IELTS Writing",
  "module": "Academic",
  "total_time_minutes": 60,
  "recommended_time_split": {...},
  "test_metadata": {
    "schema_version": "3.0",
    "generated_at": "2026-02-24T10:00:00",
    "difficulty_band": "7.0",
    "test_source": "AI Generated Practice Test"
  },
  "tasks": [...],
  "assessment": {...}
}
```

## Error Handling

The API returns appropriate HTTP status codes:

- `200`: Success
- `400`: Invalid request parameters
- `500`: Internal server error or schema validation failed
- `502`: Gemini API error

Error response format:
```json
{
  "error": "Error Type",
  "message": "Human readable message",
  "details": {...}
}
```

## API Documentation

Interactive API documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Frontend Integration

The API is designed to work directly with the IELTS Mock frontend. To connect:

1. Ensure the backend is running on `http://localhost:8000`
2. Configure CORS origins in `.env` if needed
3. Fetch tests from the API and use directly in the frontend

Example frontend fetch:
```typescript
// Reading test
const readingTest = await fetch('http://localhost:8000/api/ielts/reading');
const readingData = await readingTest.json();

// Writing test
const writingTest = await fetch('http://localhost:8000/api/ielts/writing?module=Academic');
const writingData = await writingTest.json();
```

## Extending for Listening/Speaking

The architecture is designed to be easily extensible. To add Listening or Speaking:

1. Create new schemas in `schemas/listening.py` or `schemas/speaking.py`
2. Create new services in `services/listening_service.py` or `services/speaking_service.py`
3. Create new routers in `routers/listening.py` or `routers/speaking.py`
4. Include the new router in `routers/ielts.py`

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key (required) | - |
| `HOST` | Server host | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `DEBUG` | Enable debug mode | `false` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://localhost:5173,...` |

## License

MIT License
