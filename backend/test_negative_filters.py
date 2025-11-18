#!/usr/bin/env python3
"""Test negative filter extraction."""
import re

queries = [
    'show me sweaters with no buttons',
    'sweaters without a hood',
    'no zippers',
    'show me black sweaters with no pattern'
]

product_types = ['sweater', 'sweaters', 'cardigan', 'cardigans', 'hoodie', 'hoodies',
                 'shirt', 'shirts', 'top', 'tops', 'pants', 'trousers', 'jacket', 'jackets']

patterns = [
    r'\bno\s+(\w+)s?\b',
    r'\bwithout\s+(?:a\s+)?(\w+)s?\b',
    r'\bwith\s+no\s+(\w+)s?\b',
]

for query in queries:
    query_lower = query.lower()
    excluded_features = []
    
    for pattern in patterns:
        matches = re.findall(pattern, query_lower)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    for m in match:
                        if m and m.lower() not in product_types:
                            excluded_features.append(m)
                else:
                    if match and match.lower() not in product_types:
                        excluded_features.append(match)
    
    print(f"Query: '{query}'")
    print(f"  Excluded features: {excluded_features}")
    print()

