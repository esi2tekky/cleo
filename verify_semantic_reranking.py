#!/usr/bin/env python3
"""
Verify that semantic ranking actually reorders results by comparing top-1 results
between Filtering Only and Filtering + Semantic configurations.
"""

import json
import requests
from typing import Dict, List

BASE_URL = 'http://localhost:5001'

def load_eval_queries(filepath: str = 'eval_queries.json') -> List[Dict]:
    """Load evaluation queries from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)

def get_top_result(query_text: str, use_semantic: bool) -> Dict:
    """Get the top result for a query."""
    payload = {
        'query': query_text,
        'gender': 'all',
        'use_filtering': True,
        'use_semantic': use_semantic,
        'top_k': 1
    }
    
    try:
        response = requests.post(
            f'{BASE_URL}/api/query',
            json=payload,
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                return {
                    'index': results[0].get('index'),
                    'name': results[0].get('name', 'N/A')
                }
    except Exception as e:
        print(f"Error: {e}")
    
    return {'index': None, 'name': 'ERROR'}

def main():
    """Compare top-1 results between configurations."""
    print("Verifying Semantic Ranking Reordering")
    print("=" * 60)
    
    queries = load_eval_queries()
    
    # Test first 20 queries
    test_queries = queries[:20]
    
    differences = []
    same = []
    
    print(f"\nComparing top-1 results for {len(test_queries)} queries...\n")
    
    for i, query_data in enumerate(test_queries, 1):
        query_text = query_data['query']
        print(f"[{i}/{len(test_queries)}] {query_text[:50]}...", end=' ', flush=True)
        
        # Get top result without semantic
        result_no_semantic = get_top_result(query_text, use_semantic=False)
        
        # Get top result with semantic
        result_with_semantic = get_top_result(query_text, use_semantic=True)
        
        if result_no_semantic['index'] != result_with_semantic['index']:
            differences.append({
                'query': query_text,
                'no_semantic': result_no_semantic,
                'with_semantic': result_with_semantic
            })
            print(f"✓ DIFFERENT")
            print(f"    Without semantic: [{result_no_semantic['index']}] {result_no_semantic['name']}")
            print(f"    With semantic:    [{result_with_semantic['index']}] {result_with_semantic['name']}")
        else:
            same.append(query_text)
            print(f"  Same")
    
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  Queries with different top-1: {len(differences)}/{len(test_queries)} ({len(differences)/len(test_queries)*100:.1f}%)")
    print(f"  Queries with same top-1: {len(same)}/{len(test_queries)} ({len(same)/len(test_queries)*100:.1f}%)")
    
    if differences:
        print(f"\n{'='*60}")
        print("QUERIES WHERE TOP-1 DIFFERS:")
        print(f"{'='*60}\n")
        for diff in differences[:10]:  # Show first 10
            print(f"Query: {diff['query']}")
            print(f"  Without semantic: [{diff['no_semantic']['index']}] {diff['no_semantic']['name']}")
            print(f"  With semantic:    [{diff['with_semantic']['index']}] {diff['with_semantic']['name']}")
            print()
    else:
        print("\n⚠️  WARNING: No differences found! Semantic ranking may not be working.")

if __name__ == '__main__':
    main()

