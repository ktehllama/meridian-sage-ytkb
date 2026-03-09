# Sage Chat — Backend startup script
# Run from project root: .\start_api.ps1

$env:CHROMA_DB_PATH = "./yc_vectors"
$env:SQLITE_DB_PATH = "./knowledge.db"
$env:CHROMA_COLLECTION = "transcripts"
$env:GCP_PROJECT = "YOUR_GCP_PROJECT_NUMBER"
$env:GCP_LOCATION = "us-central1"
$env:GEMINI_MODEL = "gemini-2.0-flash"

uvicorn api.main:app --reload --port 8000
