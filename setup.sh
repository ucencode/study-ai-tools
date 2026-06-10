#!/usr/bin/env bash
set -e

echo "[setup] creating virtual environment..."
python3 -m venv venv

echo "[setup] activating venv..."
source venv/bin/activate

echo "[setup] installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "[setup] done. Activate your environment with:"
echo "  source venv/bin/activate"
echo ""
echo "[setup] make sure Ollama is running and you have the required models:"
echo "  Vision (OCR) models  : qwen3-vl, qwen2.5vl, deepseek-ocr, llama3.2-vision, gemma4, ministral-3, glm-ocr"
echo "  Refine/LLM models    : glm-5.1, gemma4, qwen3.5, gpt-oss"
echo ""
echo "  Pull a model example:"
echo "    ollama pull glm-ocr:bf16"
