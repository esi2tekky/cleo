#!/bin/bash
# Start the backend API server

cd "$(dirname "$0")/backend"
echo "🚀 Starting Shopping Assistant API..."
echo ""
python app.py

