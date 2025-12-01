#!/bin/bash
# Helper script to run embedding generation with API keys

cd "$(dirname "$0")"

# Check if .env file exists and load it
if [ -f .env ]; then
    echo "Loading API keys from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check if API keys are set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  OPENAI_API_KEY not set"
    echo "   Set it with: export OPENAI_API_KEY='your-key'"
    echo "   Or create a .env file with: OPENAI_API_KEY=your-key"
    exit 1
fi

if [ -z "$PINECONE_API_KEY" ]; then
    echo "⚠️  PINECONE_API_KEY not set"
    echo "   Set it with: export PINECONE_API_KEY='your-key'"
    echo "   Or create a .env file with: PINECONE_API_KEY=your-key"
    exit 1
fi

echo "✅ API keys found"
echo "Running embedding generation..."
python3 scripts/regenerate_openai_embeddings.py

