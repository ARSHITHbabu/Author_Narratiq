@echo off
echo ============================================
echo  NarratIQ AI Backend — Starting...
echo ============================================
cd backend
echo Installing/updating dependencies...
pip install -r requirements.txt -q
echo Starting FastAPI server on http://localhost:8000
echo API docs available at http://localhost:8000/docs
echo Press CTRL+C to stop
echo.
uvicorn main:app --reload --host 0.0.0.0 --port 8000
