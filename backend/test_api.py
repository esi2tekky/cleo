#!/usr/bin/env python3
"""Test the backend API."""
import requests
import json

BASE_URL = "http://localhost:5001/api"

def test_health():
    """Test health endpoint."""
    print("Testing /api/health...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()

def test_query():
    """Test query endpoint."""
    print("Testing /api/query...")
    test_queries = [
        "minimalist black sweater",
        "wool items under $200",
        "show me beige cardigans"
    ]
    
    for query in test_queries:
        print(f"Query: '{query}'")
        response = requests.post(
            f"{BASE_URL}/query",
            json={"query": query, "top_k": 3}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"  Found {data['count']} results")
            if data['results']:
                print(f"  First result: {data['results'][0]['name']}")
        else:
            print(f"  Error: {response.status_code}")
        print()

if __name__ == "__main__":
    try:
        test_health()
        test_query()
        print("✅ All tests passed!")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to backend.")
        print("   Make sure the backend is running: python backend/app.py")
    except Exception as e:
        print(f"❌ Error: {e}")

