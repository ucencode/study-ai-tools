#!/usr/bin/env bash
set -e

echo "[setup] creating virtual environment..."
python3 -m venv venv

echo "[setup] activating venv..."
source venv/bin/activate

echo "[setup] installing python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

if command -v npm >/dev/null 2>&1; then
  echo "[setup] installing frontend dependencies..."
  (cd frontend && npm install)

  echo "[setup] building the web UI..."
  (cd frontend && npm run build)
else
  echo "[setup] npm not found — skipping the web UI."
  echo "        Install Node 18+ and run: cd frontend && npm install && npm run build"
fi

echo ""
echo "[setup] done. Activate your environment with:"
echo "  source venv/bin/activate"
echo ""
echo "[setup] start the web app (serves the UI and the API on one port):"
echo "  uvicorn main:app --host 127.0.0.1 --port 8000"
echo "  then open http://127.0.0.1:8000"
echo ""
echo "[setup] make sure Ollama is running and you have the required models:"
echo "  Vision (OCR) models  : qwen3-vl, qwen2.5vl, deepseek-ocr, llama3.2-vision, gemma4, ministral-3, glm-ocr"
echo "  Refine/LLM models    : glm-5.1, gemma4, qwen3.5, gpt-oss"
echo ""
echo "  Pull a model example:"
echo "    ollama pull glm-ocr:bf16"
echo ""
echo "[setup] the OCR tool also needs poppler on PATH (pdf2image):"
echo "  Debian/Ubuntu : sudo apt install poppler-utils"
echo "  macOS         : brew install poppler"
