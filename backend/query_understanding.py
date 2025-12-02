#!/usr/bin/env python3
"""
Query understanding using OpenAI API.
Uses structured outputs to parse natural language queries into structured components.
"""
import os
import json
from pathlib import Path
from typing import Dict, Optional, List
from openai import OpenAI
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

class QueryUnderstanding:
    """Parse natural language queries using OpenAI to extract structured information."""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        """
        Initialize OpenAI client for query understanding.
        
        Args:
            model: OpenAI model to use (default: gpt-4o-mini for cost efficiency)
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Get your API key from https://platform.openai.com/api-keys"
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    def parse_query(self, query: str) -> Dict:
        """
        Parse a natural language query into structured components.
        
        Args:
            query: User's natural language query
            
        Returns:
            Dictionary with parsed components:
            {
                "intent": "search" | "filter_previous" | "compare" | "similar" | "accessories",
                "product_type": str or None,
                "product_types": List[str] or None,  # Multiple types
                "attributes": {
                    "colors": List[str],
                    "materials": List[str],
                    "styles": List[str],
                    "features": List[str]  # e.g., ["buttons", "hood", "zipper"]
                },
                "price": {
                    "min": int or None,
                    "max": int or None,
                    "comparison": "cheapest" | "most_expensive" | None
                },
                "filters": {
                    "must_have": List[str],  # Features that must be present
                    "must_not_have": List[str],  # Features that must not be present
                    "strict": bool  # "only" or "just" keyword present
                },
                "reference": {
                    "type": "previous_results" | "tagged_product" | None,
                    "pronouns": List[str]  # ["these", "those", "this", "that"]
                }
            }
        """
        
        schema = {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["search", "filter_previous", "compare", "similar", "accessories"],
                    "description": "The main intent of the query"
                },
                "product_type": {
                    "type": ["string", "null"],
                    "description": "Primary product type mentioned (e.g., 'sweater', 'cardigan', 'sock')"
                },
                "product_types": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "All product types mentioned in the query"
                },
                "attributes": {
                    "type": "object",
                    "properties": {
                        "colors": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Colors mentioned (e.g., ['black', 'navy'])"
                        },
                        "materials": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Materials mentioned (e.g., ['wool', 'cotton'])"
                        },
                        "styles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Style keywords (e.g., ['minimalist', 'classic'])"
                        },
                        "features": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Product features (e.g., ['buttons', 'hood', 'zipper', 'pockets'])"
                        }
                    },
                    "required": ["colors", "materials", "styles", "features"]
                },
                "price": {
                    "type": "object",
                    "properties": {
                        "min": {
                            "type": ["integer", "null"],
                            "description": "Minimum price in dollars (for 'over', 'above', 'more than')"
                        },
                        "max": {
                            "type": ["integer", "null"],
                            "description": "Maximum price in dollars (for 'under', 'below', 'less than')"
                        },
                        "comparison": {
                            "type": ["string", "null"],
                            "enum": ["cheapest", "most_expensive", None],
                            "description": "Price comparison intent ('cheapest' or 'most_expensive')"
                        }
                    },
                    "required": ["min", "max", "comparison"]
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "must_have": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Features that MUST be present (e.g., ['buttons'] for 'with buttons')"
                        },
                        "must_not_have": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Features that MUST NOT be present (e.g., ['pattern'] for 'no pattern')"
                        },
                        "strict": {
                            "type": "boolean",
                            "description": "True if 'only' or 'just' is present, meaning all criteria must match strictly"
                        }
                    },
                    "required": ["must_have", "must_not_have", "strict"]
                },
                "reference": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": ["string", "null"],
                            "enum": ["previous_results", "tagged_product", None],
                            "description": "Type of reference: 'previous_results' for 'these/those', 'tagged_product' for 'this/that'"
                        },
                        "pronouns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Pronouns found (e.g., ['these'], ['this'], ['those'])"
                        }
            },
            "required": ["type", "pronouns"]
            }
        },
        "additionalProperties": False,
            "required": ["intent", "product_type", "product_types", "attributes", "price", "filters", "reference"]
        }
        
        system_prompt = """You are a query understanding system for an e-commerce shopping assistant.
Parse the user's query and extract structured information about what they're looking for.

Key rules:
- Product types: sweater, cardigan, jumper, hoodie, shirt, blouse, pants, trousers, jacket, coat, scarf, vest, sock, socks, glove, gloves, hat, cap, beanie, balaclava, t-shirt, tee
- Features: buttons, button, zipper, zip, hood, pockets, pocket, collar, collars, pattern, patterns
- Colors: black, white, navy, beige, brown, grey, gray, red, blue, green, yellow, pink, purple, orange, tan, camel, cream, ivory, charcoal, olive
- Materials: wool, cotton, cashmere, merino, silk, mohair, linen, polyester
- Styles: minimalist, classic, modern, casual, formal, oversized, fitted, relaxed, elegant, sophisticated, versatile

For intent:
- "search": Regular product search query
- "filter_previous": Query filtering previous results (e.g., "which of these", "which of those")
- "compare": Price comparison (e.g., "cheapest", "most expensive")
- "similar": Finding similar products (e.g., "more like this", "similar to")
- "accessories": Finding accessories (e.g., "accessories to wear with")

For filters:
- "must_have": Features explicitly required (e.g., "with buttons" → ["buttons"])
- "must_not_have": Features explicitly excluded (e.g., "no pattern" → ["pattern"], "without hood" → ["hood"])
- "strict": True if "only" or "just" is present (e.g., "only sweaters" → strict: true)

For reference:
- "previous_results": If query contains "these", "those", "them" → type: "previous_results"
- "tagged_product": If query contains "this", "that", "it" → type: "tagged_product"
- Extract all pronouns found in the query

Be precise and only extract what is explicitly mentioned in the query."""

        try:
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                response_format={"type": "json_schema", "json_schema": {"name": "query_parse", "strict": True, "schema": schema}}
            )
            
            parsed = response.choices[0].message.parsed
            return parsed
            
        except Exception as e:
            print(f"⚠️  OpenAI query parsing error: {e}")
            # Fallback to basic parsing
            return self._fallback_parse(query)
    
    def _fallback_parse(self, query: str) -> Dict:
        """Fallback parsing if OpenAI API fails."""
        query_lower = query.lower()
        
        # Basic intent detection
        if any(word in query_lower for word in ['these', 'those', 'them']):
            intent = "filter_previous"
        elif any(word in query_lower for word in ['this', 'that', 'it']) and any(word in query_lower for word in ['more like', 'similar']):
            intent = "similar"
        elif 'accessories' in query_lower or 'wear with' in query_lower:
            intent = "accessories"
        elif any(word in query_lower for word in ['cheapest', 'most expensive', 'least expensive']):
            intent = "compare"
        else:
            intent = "search"
        
        return {
            "intent": intent,
            "product_type": None,
            "product_types": None,
            "attributes": {
                "colors": [],
                "materials": [],
                "styles": [],
                "features": []
            },
            "price": {
                "min": None,
                "max": None,
                "comparison": None
            },
            "filters": {
                "must_have": [],
                "must_not_have": [],
                "strict": "only" in query_lower or "just" in query_lower
            },
            "reference": {
                "type": "previous_results" if any(word in query_lower for word in ['these', 'those', 'them']) else None,
                "pronouns": [word for word in ['these', 'those', 'them', 'this', 'that', 'it'] if word in query_lower]
            }
        }

