#!/usr/bin/env python3
"""
Simplified ablation study for CLEO system.
Tests 2 configurations (filtering always ON):
1. Filtering Only (semantic ranking OFF)
2. Filtering + Semantic (semantic ranking ON)
"""

import json
import requests
import time
from typing import List, Dict, Tuple
from collections import defaultdict

# Configuration
BASE_URL = 'http://localhost:5001'
TIMEOUT = 30

def load_eval_queries(filepath: str = 'eval_queries.json') -> List[Dict]:
    """Load evaluation queries from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)

def check_backend_health(base_url: str = BASE_URL) -> bool:
    """Check if backend is running and healthy."""
    try:
        response = requests.get(f'{base_url}/api/health', timeout=5)
        return response.status_code == 200
    except:
        return False

def evaluate_query(query_data: Dict, use_filtering: bool, use_semantic: bool, base_url: str = BASE_URL) -> Dict:
    """
    Evaluate a single query against the backend.
    
    Returns:
        {
            'query': str,
            'ground_truth': List[int],
            'returned_indices': List[int],
            'correct_indices': List[int],
            'num_correct': int,
            'num_returned': int,
            'num_ground_truth': int,
            'precision': float,
            'all_correct': bool,
            'top1_correct': bool,
            'latency_ms': float
        }
    """
    query_text = query_data['query']
    ground_truth = set(query_data.get('ground_truth', []))
    query_config = query_data.get('query_config', {})
    gender = query_config.get('gender', 'all')
    
    # Prepare request
    payload = {
        'query': query_text,
        'gender': gender,
        'use_filtering': use_filtering,
        'use_semantic': use_semantic,
        'top_k': 10
    }
    
    start_time = time.time()
    try:
        response = requests.post(
            f'{base_url}/api/query',
            json=payload,
            timeout=TIMEOUT
        )
        latency_ms = (time.time() - start_time) * 1000
        
        if response.status_code != 200:
            print(f"  ⚠️  Error {response.status_code} for query: {query_text[:50]}...")
            return {
                'query': query_text,
                'ground_truth': list(ground_truth),
                'returned_indices': [],
                'correct_indices': [],
                'num_correct': 0,
                'num_returned': 0,
                'num_ground_truth': len(ground_truth),
                'precision': 0.0,
                'all_correct': False,
                'top1_correct': False,
                'latency_ms': latency_ms
            }
        
        data = response.json()
        results = data.get('results', [])
        returned_indices = [r.get('index') for r in results if r.get('index') is not None]
        
        # Calculate metrics
        correct_indices = [idx for idx in returned_indices if idx in ground_truth]
        num_correct = len(correct_indices)
        num_returned = len(returned_indices)
        num_ground_truth = len(ground_truth)
        
        precision = num_correct / num_returned if num_returned > 0 else 0.0
        all_correct = num_returned > 0 and num_correct == num_returned
        top1_correct = len(returned_indices) > 0 and returned_indices[0] in ground_truth
        
        return {
            'query': query_text,
            'ground_truth': list(ground_truth),
            'returned_indices': returned_indices,
            'correct_indices': correct_indices,
            'num_correct': num_correct,
            'num_returned': num_returned,
            'num_ground_truth': num_ground_truth,
            'precision': precision,
            'all_correct': all_correct,
            'top1_correct': top1_correct,
            'latency_ms': latency_ms
        }
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        print(f"  ❌ Exception for query: {query_text[:50]}... - {e}")
        return {
            'query': query_text,
            'ground_truth': list(ground_truth),
            'returned_indices': [],
            'correct_indices': [],
            'num_correct': 0,
            'num_returned': 0,
            'num_ground_truth': len(ground_truth),
            'precision': 0.0,
            'all_correct': False,
            'top1_correct': False,
            'latency_ms': latency_ms
        }

def run_evaluation(queries: List[Dict], use_filtering: bool, use_semantic: bool, config_name: str) -> Dict:
    """Run evaluation for a single configuration."""
    print(f"\n{'='*60}")
    print(f"Testing: {config_name}")
    print(f"  Filtering: {'ON' if use_filtering else 'OFF'}")
    print(f"  Semantic: {'ON' if use_semantic else 'OFF'}")
    print(f"{'='*60}\n")
    
    results = []
    total_latency = 0.0
    
    for i, query_data in enumerate(queries, 1):
        query_text = query_data['query']
        print(f"[{i}/{len(queries)}] {query_text[:60]}...", end=' ', flush=True)
        
        result = evaluate_query(query_data, use_filtering, use_semantic)
        results.append(result)
        total_latency += result['latency_ms']
        
        # Print quick status
        if result['num_correct'] > 0:
            print(f"✓ {result['num_correct']}/{result['num_returned']} correct")
        else:
            print(f"✗ 0/{result['num_returned']} correct")
    
    # Aggregate metrics
    total_queries = len(results)
    total_correct = sum(r['num_correct'] for r in results)
    total_returned = sum(r['num_returned'] for r in results)
    perfect_queries = sum(1 for r in results if r['all_correct'])
    top1_correct_queries = sum(1 for r in results if r['top1_correct'])
    
    avg_precision = sum(r['precision'] for r in results) / total_queries if total_queries > 0 else 0.0
    perfect_rate = (perfect_queries / total_queries * 100) if total_queries > 0 else 0.0
    top1_correct_rate = (top1_correct_queries / total_queries * 100) if total_queries > 0 else 0.0
    avg_correct = total_correct / total_queries if total_queries > 0 else 0.0
    avg_latency = total_latency / total_queries if total_queries > 0 else 0.0
    
    return {
        'config_name': config_name,
        'use_filtering': use_filtering,
        'use_semantic': use_semantic,
        'total_queries': total_queries,
        'avg_precision': avg_precision,
        'perfect_rate': perfect_rate,
        'top1_correct_rate': top1_correct_rate,
        'avg_correct_per_query': avg_correct,
        'avg_latency_ms': avg_latency,
        'query_results': results
    }

def print_comparison_table(results: List[Dict]):
    """Print a formatted comparison table."""
    print(f"\n{'='*80}")
    print("ABLATION STUDY RESULTS")
    print(f"{'='*80}\n")
    
    # Header
    print(f"{'Configuration':<30} {'Filtering':<12} {'Semantic':<12} {'Avg Prec':<12} {'Perfect %':<12} {'Top-1 %':<12} {'Avg Correct':<12} {'Latency (ms)':<12}")
    print("-" * 80)
    
    # Rows
    for result in results:
        config = result['config_name']
        filtering = 'ON' if result['use_filtering'] else 'OFF'
        semantic = 'ON' if result['use_semantic'] else 'OFF'
        avg_prec = f"{result['avg_precision']:.3f}"
        perfect = f"{result['perfect_rate']:.1f}%"
        top1 = f"{result['top1_correct_rate']:.1f}%"
        avg_correct = f"{result['avg_correct_per_query']:.1f}"
        latency = f"{result['avg_latency_ms']:.1f}"
        
        print(f"{config:<30} {filtering:<12} {semantic:<12} {avg_prec:<12} {perfect:<12} {top1:<12} {avg_correct:<12} {latency:<12}")
    
    print(f"\n{'='*80}\n")

def main():
    """Main function to run ablation study."""
    print("CLEO Ablation Study")
    print("=" * 60)
    
    # Check backend health
    print("\nChecking backend health...")
    if not check_backend_health():
        print("❌ Backend is not running or not accessible!")
        print(f"   Please start the backend at {BASE_URL}")
        return
    
    print("✅ Backend is healthy\n")
    
    # Load queries
    print("Loading evaluation queries...")
    queries = load_eval_queries()
    print(f"✅ Loaded {len(queries)} queries\n")
    
    # Define configurations (filtering always ON, comparing semantic ranking)
    configurations = [
        {
            'name': 'Filtering Only',
            'use_filtering': True,
            'use_semantic': False
        },
        {
            'name': 'Filtering + Semantic',
            'use_filtering': True,
            'use_semantic': True
        }
    ]
    
    # Run evaluations
    all_results = []
    for config in configurations:
        result = run_evaluation(
            queries,
            config['use_filtering'],
            config['use_semantic'],
            config['name']
        )
        all_results.append(result)
    
    # Print comparison table
    print_comparison_table(all_results)
    
    # Save results
    output_file = 'ablation_study_results.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"✅ Results saved to {output_file}\n")
    
    # Print summary
    print("SUMMARY:")
    print("-" * 60)
    filtering_only = next(r for r in all_results if r['config_name'] == 'Filtering Only')
    filtering_semantic = next(r for r in all_results if r['config_name'] == 'Filtering + Semantic')
    
    print(f"Filtering Only Precision: {filtering_only['avg_precision']:.3f}")
    print(f"Filtering + Semantic Precision: {filtering_semantic['avg_precision']:.3f}")
    if filtering_only['avg_precision'] > 0:
        improvement = ((filtering_semantic['avg_precision'] - filtering_only['avg_precision']) / filtering_only['avg_precision']) * 100
        print(f"Semantic Ranking Impact: {improvement:+.1f}%")
    print(f"\nFiltering Only Top-1 Correct: {filtering_only['top1_correct_rate']:.1f}%")
    print(f"Filtering + Semantic Top-1 Correct: {filtering_semantic['top1_correct_rate']:.1f}%")

if __name__ == '__main__':
    main()

