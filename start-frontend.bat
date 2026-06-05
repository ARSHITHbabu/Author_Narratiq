@echo off
echo ============================================
echo  NarratIQ AI Frontend — Starting...
echo ============================================
cd frontend
echo Installing/updating dependencies...
npm install
echo.
echo Starting Next.js dev server on http://localhost:3000
echo Press CTRL+C to stop
echo.
npm run dev
