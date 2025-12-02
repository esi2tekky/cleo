#!/usr/bin/env python3
"""
Pinecone client for vector search.
Handles querying Pinecone index for semantic search.
"""
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np
from dotenv import load_dotenv

# Load environment variables from backend/.env or backend/.env.local
backend_dir = Path(__file__).parent
env_files = [
    backend_dir / ".env.local",
    backend_dir / ".env",
    Path(__file__).parent.parent / ".env.local",
    Path(__file__).parent.parent / ".env"
]
for env_file in env_files:
    if env_file.exists():
        load_dotenv(env_file)
        break

class PineconeClient:
    """Client for querying Pinecone vector database."""
    
    def __init__(self, index_name: Optional[str] = None):
        """
        Initialize Pinecone client.
        
        Args:
            index_name: Name of Pinecone index (defaults to env var)
        """
        self.index = None
        self.index_name = index_name or os.getenv("PINECONE_INDEX_NAME", "cos-products")
        
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            print("⚠️  PINECONE_API_KEY not set, Pinecone will not be available")
            return
        
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=api_key)
            
            # Check if index exists
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            if self.index_name not in existing_indexes:
                print(f"⚠️  Pinecone index '{self.index_name}' does not exist")
                print("   Run scripts/regenerate_openai_embeddings.py to create and populate it")
                return
            
            self.index = pc.Index(self.index_name)
            print(f"✅ Pinecone index '{self.index_name}' connected")
        except Exception as e:
            print(f"⚠️  Pinecone initialization failed: {e}")
            self.index = None
    
    def is_available(self) -> bool:
        """Check if Pinecone is available."""
        return self.index is not None
    
    def query(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filter: Optional[Dict] = None,
        include_metadata: bool = True
    ) -> List[Dict]:
        """
        Query Pinecone index for similar vectors.
        
        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            filter: Metadata filter (e.g., {"product_type": "sweater"})
            include_metadata: Whether to include metadata in results
            
        Returns:
            List of matches with id, score, and metadata
        """
        if not self.index:
            return []
        
        try:
            # Convert numpy array to list
            query_vector_list = query_vector.tolist()
            
            # Build query
            query_kwargs = {
                "vector": query_vector_list,
                "top_k": top_k,
                "include_metadata": include_metadata
            }
            
            if filter:
                query_kwargs["filter"] = filter
            
            # Query Pinecone
            results = self.index.query(**query_kwargs)
            
            # Format results
            matches = []
            for match in results.matches:
                matches.append({
                    "id": match.id,
                    "score": match.score,
                    "metadata": match.metadata or {}
                })
            
            return matches
        except Exception as e:
            print(f"⚠️  Pinecone query error: {e}")
            return []
    
    def query_with_product_indices(
        self,
        query_vector: np.ndarray,
        product_indices: List[int],
        top_k: int = 10
    ) -> List[Tuple[int, float]]:
        """
        Query Pinecone but only return results that match product indices.
        This is used when we've already filtered products and want to re-rank them.
        
        Args:
            query_vector: Query embedding vector
            product_indices: List of product indices to filter by
            top_k: Number of results to return
            
        Returns:
            List of (product_index, similarity_score) tuples
        """
        if not self.index:
            return []
        
        try:
            # Query with a larger top_k to get more candidates
            # We'll filter by product_indices afterwards
            query_vector_list = query_vector.tolist()
            
            # Query for more results than we need (in case some don't match)
            results = self.index.query(
                vector=query_vector_list,
                top_k=min(top_k * 3, 100),  # Get 3x more to account for filtering
                include_metadata=True
            )
            
            # Filter results to only include products in product_indices
            matches = []
            product_indices_set = set(product_indices)
            
            for match in results.matches:
                # Extract product index from id or metadata
                product_idx = None
                
                # Try to get from metadata first (check both possible keys)
                if match.metadata:
                    if "product_index" in match.metadata:
                        product_idx = int(match.metadata["product_index"])
                    elif "product_id" in match.metadata:
                        # The regenerate script uses "product_id" not "product_index"
                        product_idx = int(match.metadata["product_id"])
                
                # If not in metadata, try to extract from id
                if product_idx is None:
                    try:
                        # ID format from regenerate script: "product_{idx}_text"
                        if match.id.startswith("product_"):
                            # Extract: "product_123_text" -> "123"
                            idx_str = match.id.replace("product_", "").replace("_text", "")
                            product_idx = int(idx_str)
                        elif "_text" in match.id:
                            # Old format: "{name}_{index}_text" - extract last number before "_text"
                            idx_str = match.id.rsplit("_text", 1)[0].split("_")[-1]
                            product_idx = int(idx_str)
                    except (ValueError, IndexError):
                        continue
                
                if product_idx is not None and product_idx in product_indices_set:
                    matches.append((product_idx, match.score))
                    
                    # Stop if we have enough results
                    if len(matches) >= top_k:
                        break
            
            return matches
        except Exception as e:
            print(f"⚠️  Pinecone query error: {e}")
            return []

