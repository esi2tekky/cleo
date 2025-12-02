#!/usr/bin/env python3
"""
OpenAI API client for text embeddings.
Uses OpenAI's text-embedding-3-small or text-embedding-ada-002.
"""
from openai import OpenAI
import os
from typing import Optional, List
import numpy as np

class OpenAIEmbedder:
    """OpenAI embedding client for text embeddings."""
    
    def __init__(self, model: str = "text-embedding-3-small"):
        """
        Initialize OpenAI embedder.
        
        Args:
            model: OpenAI embedding model name
                - "text-embedding-3-small" (recommended, 1536 dim, cheaper)
                - "text-embedding-3-large" (3072 dim, better quality)
                - "text-embedding-ada-002" (1536 dim, older but stable)
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Get your API key from https://platform.openai.com/api-keys"
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model
        # Determine embedding dimension based on model
        if "small" in model or "ada" in model:
            self.embedding_dim = 1536
        elif "large" in model:
            self.embedding_dim = 3072
        else:
            self.embedding_dim = 1536  # Default
    
    def get_embedding(self, text: str, max_retries: int = 3) -> Optional[np.ndarray]:
        """
        Get embedding from OpenAI API.
        
        Args:
            text: Text to embed
            max_retries: Maximum retry attempts
            
        Returns:
            Embedding vector or None if failed
        """
        if not text or len(text.strip()) < 1:
            return None
        
        for attempt in range(max_retries):
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=text.strip()
                )
                embedding = np.array(response.data[0].embedding, dtype=np.float32)
                return embedding
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️  OpenAI embedding attempt {attempt + 1} failed: {e}, retrying...")
                    continue
                else:
                    print(f"❌ OpenAI embedding error after {max_retries} attempts: {e}")
                    return None
    
    def get_embeddings_batch(self, texts: List[str], batch_size: int = 100) -> List[Optional[np.ndarray]]:
        """
        Get embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch (OpenAI limit is 2048)
            
        Returns:
            List of embeddings (None for failed texts)
        """
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                batch_embeddings = [
                    np.array(item.embedding, dtype=np.float32) 
                    for item in response.data
                ]
                results.extend(batch_embeddings)
            except Exception as e:
                print(f"⚠️  Batch embedding error: {e}")
                # Add None for failed batch
                results.extend([None] * len(batch))
        return results


