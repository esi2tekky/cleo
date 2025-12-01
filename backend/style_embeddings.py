#!/usr/bin/env python3
"""
Style embeddings for situational queries.
Maps queries like "suitable for a night in paris" to style contexts.
"""
from typing import Dict, Optional, List
import numpy as np

# Pre-defined style contexts for common situations
STYLE_CONTEXTS = {
    # Occasions
    "night in paris": {
        "keywords": ["elegant", "sophisticated", "refined", "classic", "timeless", "dressy", "evening", "chic", "polished"],
        "occasion": "evening",
        "vibe": "sophisticated",
        "style_tags": ["elegant", "sophisticated", "classic", "dressy"]
    },
    "night out": {
        "keywords": ["dressy", "elegant", "stylish", "evening", "sophisticated", "chic"],
        "occasion": "evening",
        "vibe": "stylish",
        "style_tags": ["dressy", "elegant", "stylish"]
    },
    "casual day": {
        "keywords": ["comfortable", "relaxed", "casual", "everyday", "versatile", "easy"],
        "occasion": "casual",
        "vibe": "relaxed",
        "style_tags": ["casual", "comfortable", "relaxed"]
    },
    "office": {
        "keywords": ["professional", "polished", "tailored", "smart", "business", "formal", "corporate"],
        "occasion": "work",
        "vibe": "professional",
        "style_tags": ["professional", "polished", "tailored"]
    },
    "weekend": {
        "keywords": ["casual", "relaxed", "comfortable", "easy", "laid-back"],
        "occasion": "casual",
        "vibe": "relaxed",
        "style_tags": ["casual", "relaxed", "comfortable"]
    },
    "date night": {
        "keywords": ["elegant", "romantic", "dressy", "sophisticated", "chic", "refined"],
        "occasion": "evening",
        "vibe": "romantic",
        "style_tags": ["elegant", "dressy", "sophisticated"]
    },
    "beach": {
        "keywords": ["lightweight", "breathable", "summer", "casual", "relaxed", "comfortable"],
        "occasion": "casual",
        "vibe": "relaxed",
        "style_tags": ["lightweight", "casual", "summer"]
    },
    "winter": {
        "keywords": ["warm", "cozy", "layered", "insulated", "comfortable", "practical"],
        "occasion": "casual",
        "vibe": "cozy",
        "style_tags": ["warm", "cozy", "practical"]
    },
    "formal event": {
        "keywords": ["formal", "elegant", "sophisticated", "polished", "refined", "dressy"],
        "occasion": "formal",
        "vibe": "sophisticated",
        "style_tags": ["formal", "elegant", "polished"]
    },
    # Cities/Locations (style vibes)
    "paris": {
        "keywords": ["elegant", "sophisticated", "classic", "chic", "refined", "timeless"],
        "vibe": "sophisticated",
        "style_tags": ["elegant", "sophisticated", "classic"]
    },
    "new york": {
        "keywords": ["modern", "sleek", "urban", "sophisticated", "polished"],
        "vibe": "urban",
        "style_tags": ["modern", "sleek", "urban"]
    },
    "london": {
        "keywords": ["classic", "tailored", "sophisticated", "refined", "polished"],
        "vibe": "sophisticated",
        "style_tags": ["classic", "tailored", "sophisticated"]
    },
    "california": {
        "keywords": ["casual", "relaxed", "beach", "laid-back", "comfortable", "easy"],
        "vibe": "relaxed",
        "style_tags": ["casual", "relaxed", "comfortable"]
    },
}

def extract_style_context(query: str) -> Optional[Dict]:
    """
    Extract style context from query.
    
    Args:
        query: User query text
        
    Returns:
        Style context dict or None if no match
    """
    query_lower = query.lower()
    
    # Check for direct matches
    for context_name, context_data in STYLE_CONTEXTS.items():
        if context_name in query_lower:
            return context_data
    
    # Check for partial matches (e.g., "paris" matches "night in paris")
    for context_name, context_data in STYLE_CONTEXTS.items():
        context_words = context_name.split()
        if all(word in query_lower for word in context_words if len(word) > 3):
            return context_data
    
    return None

def enhance_query_with_style(query: str, style_context: Dict) -> str:
    """
    Enhance query with style keywords.
    
    Args:
        query: Original query
        style_context: Style context dict
        
    Returns:
        Enhanced query with style keywords
    """
    style_keywords = " ".join(style_context.get("style_tags", style_context.get("keywords", [])))
    enhanced = f"{query} {style_keywords}"
    return enhanced.strip()

def get_style_embedding_query(query: str, embedder, parsed_components: Optional[Dict] = None) -> Optional[np.ndarray]:
    """
    Get style-enhanced embedding for query.
    
    Args:
        query: User query
        embedder: Embedding function (OpenAI or sentence-transformers)
        parsed_components: Optional parsed query components from QueryParser
        
    Returns:
        Style-enhanced embedding or regular embedding
    """
    # If parsed components provided, use them to build enhanced query
    if parsed_components and parsed_components.get("style_keywords"):
        from backend.query_parser import QueryParser
        parser = QueryParser()
        enhanced_query = parser.build_enhanced_query(query, parsed_components)
        return embedder.get_embedding(enhanced_query)
    
    # Fallback to simple style context matching
    style_context = extract_style_context(query)
    
    if style_context:
        enhanced_query = enhance_query_with_style(query, style_context)
        return embedder.get_embedding(enhanced_query)
    
    # Fallback to regular embedding
    return embedder.get_embedding(query)

