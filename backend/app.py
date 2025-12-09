#!/usr/bin/env python3
"""
Backend API server for the shopping assistant chatbot.
Serves enriched product data and handles style-related queries.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import pickle
from pathlib import Path
import numpy as np
from typing import List, Dict, Optional
import os
import json
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

# Import enrichment utilities
import sys
sys.path.append(str(Path(__file__).parent.parent))
from utils.enrich import StyleEnricher, load_embeddings
from backend.pinecone_client import PineconeClient
from backend.query_understanding import QueryUnderstanding

app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome extension

# Global variables for loaded data
products_df = None
embeddings_dict = None
enricher = None
query_understanding = None
pinecone_client = None
openai_embedder = None

def load_data():
    """Load enriched data and embeddings."""
    global products_df, embeddings_dict, enricher, openai_embedder
    
    data_dir = Path(__file__).parent.parent / "data" / "processed"
    
    # Load enriched products
    csv_file = data_dir / "enriched_cos_all_products.csv"
    if csv_file.exists():
        products_df = pd.read_csv(csv_file)
        print(f"✅ Loaded {len(products_df)} products from {csv_file.name}")
    else:
        print(f"⚠️  Enriched data not found at {csv_file}")
        print(f"   Run enrichment: python3.13 enrich_new_data.py")
        products_df = pd.DataFrame()
    
    # Load embeddings (only needed as fallback if Pinecone isn't available)
    embeddings_file = data_dir / "embeddings.pkl"
    if embeddings_file.exists():
        embeddings_dict = load_embeddings(embeddings_file)
        print(f"✅ Loaded {len(embeddings_dict)} local embeddings (fallback only)")
    else:
        print(f"⚠️  No local embeddings found at {embeddings_file}")
        embeddings_dict = {}
    
    # Initialize enricher (for query encoding - only used if Pinecone not available)
    enricher = StyleEnricher(use_clip=False)  # Don't need CLIP for query encoding
    print("✅ Enricher initialized (sentence-transformers, 384-dim)")
    
    # Initialize OpenAI embedder (for queries when Pinecone is available)
    try:
        from backend.openai_client import OpenAIEmbedder
        openai_embedder = OpenAIEmbedder()
        print("✅ OpenAI embedder initialized (1536-dim, for Pinecone queries)")
    except ValueError as e:
        print(f"⚠️  OpenAI embedder not available: {e}")
        print("   Will use sentence-transformers for queries (may not match Pinecone dimensions)")
        openai_embedder = None
    
    # Initialize query understanding (with fallback if API key not set)
    global query_understanding
    try:
        query_understanding = QueryUnderstanding()
        print("✅ Query understanding initialized (OpenAI)")
    except ValueError as e:
        print(f"⚠️  Query understanding not available: {e}")
        print("   Falling back to keyword-based parsing")
        query_understanding = None
    
    # Initialize Pinecone client (for vector search)
    global pinecone_client
    try:
        pinecone_client = PineconeClient()
        if pinecone_client.is_available():
            print("✅ Pinecone client initialized")
            if openai_embedder:
                print("   Using OpenAI embeddings (1536-dim) for queries to match Pinecone index")
            else:
                print("   ⚠️  WARNING: OpenAI embedder not available, queries may fail due to dimension mismatch")
        else:
            print("⚠️  Pinecone not available, using local embeddings (sentence-transformers)")
    except Exception as e:
        print(f"⚠️  Pinecone initialization failed: {e}")
        pinecone_client = None

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'products_loaded': len(products_df) if products_df is not None else 0,
        'embeddings_loaded': len(embeddings_dict) if embeddings_dict else 0
    })

@app.route('/api/products', methods=['GET'])
def get_products():
    """Get all products with optional filtering."""
    if products_df is None or products_df.empty:
        return jsonify({'error': 'No products loaded'}), 404
    
    # Get query parameters
    limit = int(request.args.get('limit', 20))
    offset = int(request.args.get('offset', 0))
    
    # Filter by color, material, etc.
    filtered_df = products_df.copy()
    
    if 'color' in request.args:
        color = request.args.get('color').lower()
        filtered_df = filtered_df[
            filtered_df['colors'].astype(str).str.lower().str.contains(color, na=False)
        ]
    
    if 'material' in request.args:
        material = request.args.get('material').lower()
        filtered_df = filtered_df[
            filtered_df['materials'].astype(str).str.lower().str.contains(material, na=False)
        ]
    
    if 'style' in request.args:
        style = request.args.get('style').lower()
        filtered_df = filtered_df[
            filtered_df['style_keywords'].astype(str).str.lower().str.contains(style, na=False)
        ]
    
    # Paginate
    paginated = filtered_df.iloc[offset:offset+limit]
    
    # Replace NaN with None for JSON serialization
    products_dict = paginated.replace({np.nan: None}).to_dict('records')
    
    return jsonify({
        'products': products_dict,
        'total': len(filtered_df),
        'limit': limit,
        'offset': offset
    })

@app.route('/api/search', methods=['POST'])
def search_products():
    """
    Semantic search using text embeddings.
    
    Request body:
    {
        "query": "minimalist black sweater",
        "top_k": 5,
        "use_visual": false
    }
    """
    if products_df is None or products_df.empty:
        return jsonify({'error': 'No products loaded'}), 404
    
    if not embeddings_dict:
        return jsonify({'error': 'No embeddings loaded'}), 404
    
    data = request.get_json()
    query_text = data.get('query', '')
    top_k = data.get('top_k', 5)
    use_visual = data.get('use_visual', False)
    
    if not query_text:
        return jsonify({'error': 'Query text required'}), 400
    
    # Encode query
    if use_visual:
        # Would need query image URL
        query_emb = None
    else:
        query_emb = enricher.get_text_embedding(query_text)
    
    if query_emb is None:
        return jsonify({'error': 'Failed to encode query'}), 500
    
    # Compute similarities
    similarities = []
    for idx, row in products_df.iterrows():
        product_id = f"{row.get('name', idx)}_{idx}"
        emb_key = f"{product_id}_text" if not use_visual else f"{product_id}_visual"
        
        if emb_key in embeddings_dict:
            product_emb = np.array(embeddings_dict[emb_key])
            # Cosine similarity
            similarity = np.dot(query_emb, product_emb) / (
                np.linalg.norm(query_emb) * np.linalg.norm(product_emb)
            )
            # Replace NaN with None for JSON serialization
            product_dict = row.where(pd.notna(row), None).to_dict()
            similarities.append({
                'index': idx,
                'similarity': float(similarity),
                'product': product_dict
            })
    
    # Sort by similarity
    similarities.sort(key=lambda x: x['similarity'], reverse=True)
    
    # Return top_k (products already have NaN replaced)
    results = [s['product'] for s in similarities[:top_k]]
    
    return jsonify({
        'query': query_text,
        'results': results,
        'count': len(results)
    })

@app.route('/api/query', methods=['POST'])
def handle_query():
    """
    Handle natural language queries about products.
    Combines semantic search with attribute filtering.
    
    Request body:
    {
        "query": "show me wool sweaters under $200",
        "top_k": 10,
        "tagged_products": [{"index": 123, "name": "..."}]
    }
    """
    if products_df is None or products_df.empty:
        return jsonify({'error': 'No products loaded'}), 404
    
    data = request.get_json()
    query_text = data.get('query', '')
    top_k = data.get('top_k', 10)
    tagged_products = data.get('tagged_products', [])
    last_displayed_products = data.get('last_displayed_products', [])  # Products from last query
    gender_filter = data.get('gender', 'all')  # 'men', 'women', or 'all'
    
    # Ablation study flags (default to True for normal operation)
    use_filtering = data.get('use_filtering', True)
    use_semantic = data.get('use_semantic', True)
    
    if not query_text:
        return jsonify({'error': 'Query text required'}), 400
    
    # Parse query using OpenAI if available
    parsed_query = None
    if query_understanding:
        try:
            parsed_query = query_understanding.parse_query(query_text)
            print(f"📊 Parsed query: {json.dumps(parsed_query, indent=2)}")
        except Exception as e:
            print(f"⚠️  Query parsing failed: {e}, falling back to keyword-based")
            parsed_query = None
    
    # Check if query is filtering previous results (e.g., "which of these do not have buttons")
    query_lower = query_text.lower()
    reference_words = ['these', 'those', 'them']
    has_reference = any(word in query_lower for word in reference_words)
    has_which = 'which' in query_lower or 'what' in query_lower
    
    # Check for negative filters in the query
    negative_patterns = [
        r'do\s+not\s+have',
        r'does\s+not\s+have',
        r'don\'t\s+have',
        r'without',
        r'no\s+',
        r'not\s+have'
    ]
    import re
    has_negative_filter = any(re.search(pattern, query_lower) for pattern in negative_patterns)
    
    # Check for price filters in the query
    has_price_filter = any(keyword in query_lower for keyword in ['under', 'over', 'above', 'below', 'less than', 'more than', '$', 'dollar'])
    
    # Check for price comparison queries (cheapest, most expensive, cheaper, etc.)
    comparison_keywords = ['cheapest', 'most expensive', 'least expensive', 'most.*expensive', 'least.*expensive', 'lowest price', 'highest price']
    comparison_simple_keywords = ['cheapest', 'most expensive', 'least expensive', 'lowest', 'highest', 'cheaper', 'more expensive', 'less expensive', 'costs less', 'costs more']
    has_comparison = any(re.search(pattern, query_lower) for pattern in comparison_keywords) or \
                    any(keyword in query_lower for keyword in comparison_simple_keywords)
    
    # Check for recommendation/opinion queries (e.g., "which would be a good gift", "which is better")
    recommendation_keywords = ['good gift', 'better', 'best', 'recommend', 'suggest', 'prefer', 'should i', 'would be good', 'would be better']
    has_recommendation = any(keyword in query_lower for keyword in recommendation_keywords)
    
    # If query references previous results with a filter OR recommendation, handle those results
    if (has_reference or has_which) and (has_negative_filter or 'have' in query_lower or has_price_filter or has_comparison or has_recommendation) and last_displayed_products:
        print(f"🔍 Filtering previous results based on: {query_text}")
        print(f"   Previous results count: {len(last_displayed_products)}")
        
        # Extract price filter if present
        max_price = None
        min_price = None
        
        if has_price_filter:
            # Try $200 format first
            price_matches = re.findall(r'\$(\d+)', query_text)
            if price_matches:
                price_value = int(price_matches[0])
                if 'under' in query_lower or 'below' in query_lower or 'less than' in query_lower:
                    max_price = price_value
                elif 'over' in query_lower or 'above' in query_lower or 'more than' in query_lower:
                    min_price = price_value
                else:
                    # Default to max if just "$200" without context
                    max_price = price_value
            else:
                # Try "200 dollars" or "200 dollar" format
                price_matches = re.findall(r'(\d+)\s*dollars?', query_lower)
                if price_matches:
                    price_value = int(price_matches[0])
                    if 'under' in query_lower or 'below' in query_lower or 'less than' in query_lower:
                        max_price = price_value
                    elif 'over' in query_lower or 'above' in query_lower or 'more than' in query_lower:
                        min_price = price_value
                    else:
                        max_price = price_value
                else:
                    # Try "under 200" or "below 200" format (number after "under"/"below")
                    price_matches = re.findall(r'(?:under|below|less than|max|maximum)\s+(\d+)', query_lower)
                    if price_matches:
                        max_price = int(price_matches[0])
                    else:
                        # Try "over 200" or "above 200" format
                        price_matches = re.findall(r'(?:over|above|more than|min|minimum)\s+(\d+)', query_lower)
                        if price_matches:
                            min_price = int(price_matches[0])
        
        # Extract the feature to filter by (e.g., "buttons", "pattern", "hood")
        feature_keywords = {
            'button': ['button', 'buttons'],
            'pattern': ['pattern', 'patterns'],
            'hood': ['hood'],
            'zipper': ['zipper', 'zip'],
            'pocket': ['pocket', 'pockets'],
            'collar': ['collar', 'collars'],
        }
        
        filtered_results = []
        for product in last_displayed_products:
            # Apply price filter first
            if max_price is not None or min_price is not None:
                product_price = product.get('price')
                if product_price is None:
                    continue
                try:
                    price = int(float(str(product_price)))
                    if max_price is not None and price > max_price:
                        continue
                    if min_price is not None and price < min_price:
                        continue
                except (ValueError, TypeError):
                    continue
            
            # Apply feature filters
            product_name = str(product.get('name', '')).lower()
            product_desc = str(product.get('description', '')).lower()
            product_text = f"{product_name} {product_desc}"
            
            # Check if this is a negative filter (exclude products with the feature)
            should_exclude = False
            for feature, keywords in feature_keywords.items():
                if any(keyword in query_lower for keyword in keywords):
                    # Check if product has this feature
                    has_feature = any(keyword in product_text for keyword in keywords)
                    if has_negative_filter and has_feature:
                        # Negative filter: exclude products with the feature
                        should_exclude = True
                        break
                    elif not has_negative_filter and 'have' in query_lower and not has_feature:
                        # Positive filter: exclude products without the feature
                        should_exclude = True
                        break
            
            if not should_exclude:
                filtered_results.append(product)
        
        # Handle recommendation queries (return all previous results if no filters applied)
        if has_recommendation and not (has_negative_filter or 'have' in query_lower or has_price_filter or has_comparison):
            # For recommendation queries without specific filters, return all previous results
            # The user is asking for an opinion/recommendation, so show all options
            filtered_results = last_displayed_products.copy()
            print(f"💡 Recommendation query: returning all {len(filtered_results)} previous results for user to choose")
        
        # Handle price comparison queries (cheapest, most expensive)
        if has_comparison and filtered_results:
            # Sort by price
            def get_price(product):
                price = product.get('price')
                if price is None:
                    return float('inf')  # Put products without price at the end
                try:
                    return int(float(str(price)))
                except (ValueError, TypeError):
                    return float('inf')
            
            filtered_results.sort(key=get_price)
            
            # Determine if we want cheapest or most expensive
            if any(keyword in query_lower for keyword in ['cheapest', 'least expensive', 'lowest', 'cheaper', 'less expensive', 'costs less']):
                # Return only the cheapest product(s) - handle ties
                if filtered_results:
                    cheapest_price = get_price(filtered_results[0])
                    cheapest_products = [p for p in filtered_results if get_price(p) == cheapest_price]
                    filtered_results = cheapest_products
            elif any(keyword in query_lower for keyword in ['most expensive', 'highest', 'more expensive', 'costs more']):
                # Return only the most expensive product(s) - handle ties
                if filtered_results:
                    filtered_results.reverse()  # Most expensive first
                    most_expensive_price = get_price(filtered_results[0])
                    most_expensive_products = [p for p in filtered_results if get_price(p) == most_expensive_price]
                    filtered_results = most_expensive_products
        
        if filtered_results:
            # Return all filtered results (don't limit to top_k since we're filtering a specific set)
            return jsonify({
                'query': query_text,
                'results': filtered_results,
                'count': len(filtered_results)
            })
        else:
            return jsonify({
                'query': query_text,
                'results': [],
                'count': 0,
                'message': "No products from previous results match that criteria."
            })
    
    # Check if query references a tagged product (e.g., "show me more like this")
    referenced_product = None
    
    # Check for pronouns that reference products
    pronoun_patterns = ['this', 'that', 'it', 'this one', 'that one']
    has_pronoun = any(pronoun in query_lower for pronoun in pronoun_patterns)
    
    # Check for "more like" or "similar" patterns
    similar_patterns = ['more like', 'similar', 'like this', 'like that', 'same style']
    has_similar_intent = any(pattern in query_lower for pattern in similar_patterns)
    
    # Check for "accessories" or "wear with" patterns
    accessories_patterns = ['accessories', 'accessory', 'wear with', 'goes with', 'pair with', 'pair well', 'match with', 'would pair', 'should i wear', 'what should i wear', 'what to wear', 'what should', 'what would', 'go well', 'would go']
    has_accessories_intent = any(pattern in query_lower for pattern in accessories_patterns)
    
    # If query has pronoun or similar intent AND we have tagged products, use the first tagged product
    if (has_pronoun or has_similar_intent or has_accessories_intent) and tagged_products:
        referenced_product = tagged_products[0]  # Use most recently tagged
        ref_idx = referenced_product.get('index')
        print(f"🔍 Detected product reference: using tagged product index {ref_idx}")
        print(f"   Query intent: accessories={has_accessories_intent}, similar={has_similar_intent}, pronoun={has_pronoun}")
        
        # Handle "accessories" or "wear with" queries - show complementary items, not similar ones
        # Prioritize accessories intent over similar intent
        if has_accessories_intent:
            if ref_idx is not None:
                try:
                    ref_idx = int(ref_idx)
                    if 0 <= ref_idx < len(products_df):
                        ref_product = products_df.iloc[ref_idx]
                        ref_category = str(ref_product.get('category', '')).lower()
                        ref_name = str(ref_product.get('name', '')).lower()
                        
                        # === STEP 1: Extract gender from tagged product ===
                        ref_gender = None
                        # Check if gender column exists and has a value (ref_product is a Series)
                        if 'gender' in ref_product.index and pd.notna(ref_product['gender']):
                            ref_gender = str(ref_product['gender']).lower()
                        elif ref_category:
                            # Fallback: Extract gender from category (e.g., "Women's Knitwear" -> "women")
                            if 'women' in ref_category:
                                ref_gender = 'women'
                            elif 'men' in ref_category:
                                ref_gender = 'men'
                        
                        # Use tagged product's gender if available, otherwise fall back to UI filter
                        effective_gender = ref_gender if ref_gender else gender_filter
                        print(f"   👤 Tagged product gender: {ref_gender}, UI filter: {gender_filter}, effective: {effective_gender}")
                        
                        # === STEP 2: Extract requested product type from query ===
                        requested_type = None
                        query_product_types_list = [
                            'pants', 'trousers', 'jeans', 'chinos',
                            'jacket', 'coat', 'blazer',
                            'shirt', 'blouse', 'top',
                            'sweater', 'cardigan', 'jumper', 'hoodie',
                            'skirt', 'dress',
                            'scarf', 'hat', 'cap', 'beanie', 'glove', 'sock', 'belt', 'tie',
                            'shoe', 'boot', 'sneaker'
                        ]
                        for ptype in query_product_types_list:
                            if ptype in query_lower:
                                requested_type = ptype
                                print(f"   🎯 Requested product type from query: {requested_type}")
                                break
                        
                        # Determine what type of product the reference is
                        ref_product_type = None
                        if 'sweater' in ref_name or 'cardigan' in ref_name or 'jumper' in ref_name or 'hoodie' in ref_name:
                            ref_product_type = 'sweater'
                        elif 'shirt' in ref_name or 'blouse' in ref_name:
                            ref_product_type = 'shirt'
                        elif 'pants' in ref_name or 'trousers' in ref_name:
                            ref_product_type = 'pants'
                        elif 'jacket' in ref_name or 'coat' in ref_name:
                            ref_product_type = 'jacket'
                        
                        # Filter to complementary items (pants, jackets, shoes, accessories, etc.)
                        # Exclude the same product type as the reference
                        results_df = products_df.copy()
                        
                        # === STEP 3: Apply gender filter from tagged product ===
                        if effective_gender and effective_gender != 'all':
                            if 'gender' in results_df.columns:
                                gender_mask = results_df['gender'].astype(str).str.lower() == effective_gender.lower()
                                results_df = results_df[gender_mask]
                                print(f"   👤 Gender filter ({effective_gender}) for 'wear with': {len(results_df)} products")
                            elif 'category' in results_df.columns:
                                if effective_gender.lower() == 'men':
                                    gender_mask = results_df['category'].astype(str).str.lower().str.contains("men", na=False)
                                elif effective_gender.lower() == 'women':
                                    gender_mask = results_df['category'].astype(str).str.lower().str.contains("women", na=False)
                                else:
                                    gender_mask = pd.Series([True] * len(results_df), index=results_df.index)
                                results_df = results_df[gender_mask]
                                print(f"   👤 Gender filter ({effective_gender}) from category for 'wear with': {len(results_df)} products")
                        
                        # === STEP 4: If user requested specific product type, filter to that ===
                        if requested_type:
                            # Map related terms (e.g., pants -> trousers)
                            type_synonyms = {
                                'pants': ['pants', 'trousers', 'jeans', 'chinos'],
                                'trousers': ['pants', 'trousers', 'jeans', 'chinos'],
                                'jacket': ['jacket', 'coat', 'blazer'],
                                'coat': ['jacket', 'coat', 'blazer'],
                                'shirt': ['shirt', 'blouse'],
                                'blouse': ['shirt', 'blouse'],
                                'sweater': ['sweater', 'cardigan', 'jumper', 'pullover'],
                                'cardigan': ['sweater', 'cardigan', 'jumper', 'pullover'],
                            }
                            search_terms = type_synonyms.get(requested_type, [requested_type])
                            
                            type_mask = pd.Series([False] * len(results_df), index=results_df.index)
                            for term in search_terms:
                                type_mask |= results_df['name'].astype(str).str.lower().str.contains(term, na=False)
                                # Also check category for the type
                                if 'category' in results_df.columns:
                                    type_mask |= results_df['category'].astype(str).str.lower().str.contains(term, na=False)
                            results_df = results_df[type_mask]
                            print(f"   🎯 Filtered to requested type '{requested_type}' (terms: {search_terms}): {len(results_df)} products")
                        
                        # Only apply complementary type filtering if user didn't request a specific type
                        # If user asked for "pants", we already filtered to pants above
                        if not requested_type:
                            # Define complementary product types based on reference
                            # IMPORTANT: Do NOT include the same product type (e.g., don't include sweaters when reference is a sweater)
                            complementary_types = {
                                'shirt': ['pants', 'trousers', 'jacket', 'coat', 'blazer', 'shoe', 'boot', 'sneaker', 'scarf', 'hat', 'cap', 'beanie', 'belt', 'tie', 'sock'],
                                'sweater': ['pants', 'trousers', 'jacket', 'coat', 'shirt', 'blouse', 'shoe', 'boot', 'sneaker', 'scarf', 'hat', 'cap', 'beanie', 'glove', 'sock', 'belt'],
                                'pants': ['shirt', 'blouse', 'sweater', 'cardigan', 'jacket', 'coat', 'blazer', 'shoe', 'boot', 'sneaker', 'belt', 'sock'],
                                'jacket': ['shirt', 'blouse', 'sweater', 'cardigan', 'pants', 'trousers', 'shoe', 'boot', 'sneaker', 'scarf', 'hat', 'cap', 'beanie', 'glove', 'belt'],
                                'default': ['pants', 'trousers', 'jacket', 'coat', 'blazer', 'shirt', 'blouse', 'shoe', 'boot', 'sneaker', 'scarf', 'hat', 'cap', 'beanie', 'glove', 'sock', 'belt', 'tie', 'vest']
                            }
                            
                            # Get complementary keywords for this product type
                            comp_keywords = complementary_types.get(ref_product_type, complementary_types['default'])
                            
                            # Also include accessories
                            accessory_keywords = ['scarf', 'glove', 'sock', 'hat', 'cap', 'beanie', 'balaclava', 'vest', 'belt', 'tie', 'ring']
                            all_keywords = list(set(comp_keywords + accessory_keywords))
                            
                            # Build mask for complementary items
                            complementary_mask = pd.Series([False] * len(results_df), index=results_df.index)
                            
                            for keyword in all_keywords:
                                name_match = results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
                                category_match = results_df['category'].astype(str).str.lower().str.contains(keyword, na=False)
                                complementary_mask |= (name_match | category_match)
                            
                            # Also check if category is "accessories" or other complementary categories
                            if 'category' in results_df.columns:
                                comp_categories = ['accessories', 'outerwear', 'bottoms', 'footwear', 'tops']
                                for cat in comp_categories:
                                    cat_match = results_df['category'].astype(str).str.lower().str.contains(cat, na=False)
                                    complementary_mask |= cat_match
                            
                            results_df = results_df[complementary_mask]
                            
                            # Exclude the same product type as reference (more strict exclusion)
                            if ref_product_type:
                                exclude_keywords = {
                                    'sweater': ['sweater', 'cardigan', 'jumper', 'hoodie'],
                                    'shirt': ['shirt', 'blouse', 'polo', 'tee', 't-shirt', 'henley'],
                                    'pants': ['pants', 'trousers', 'jeans', 'chinos'],
                                    'jacket': ['jacket', 'coat', 'blazer', 'overshirt']
                                }
                                if ref_product_type in exclude_keywords:
                                    # Build exclusion mask: exclude items that contain ANY of the exclude keywords
                                    exclude_mask = pd.Series([False] * len(results_df), index=results_df.index)
                                    for keyword in exclude_keywords[ref_product_type]:
                                        exclude_mask |= results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
                                    # Keep only items that DON'T match the exclusion mask
                                    results_df = results_df[~exclude_mask]
                                    print(f"   🚫 Excluded {ref_product_type} products: {len(results_df)} remaining")
                        
                        # Exclude the reference product itself (ensure it's not in results)
                        initial_count = len(results_df)
                        results_df = results_df[results_df.index != ref_idx]
                        print(f"   Excluded reference product (index {ref_idx}) from results")
                        print(f"   Results: {initial_count} -> {len(results_df)} products after exclusion")
                        
                        # Limit results
                        results_df = results_df.head(top_k)
                        
                        # Convert to dict format
                        results_dict = []
                        for idx, row in results_df.iterrows():
                            # Skip if this is the reference product (extra safety check)
                            if idx == ref_idx:
                                print(f"   ⚠️  Warning: Reference product {ref_idx} found in results, skipping")
                                continue
                            product_dict = row.replace({np.nan: None}).to_dict()
                            product_dict['index'] = int(idx)
                            results_dict.append(product_dict)
                        
                        print(f"   Final results: {len(results_dict)} products (tagged product excluded)")
                        
                        if results_dict:
                            return jsonify({
                                'query': query_text,
                                'results': results_dict,
                                'count': len(results_dict)
                            })
                        else:
                            return jsonify({
                                'query': query_text,
                                'results': [],
                                'count': 0,
                                'message': "I couldn't find any accessories. Try a different query."
                            })
                except (ValueError, IndexError, KeyError) as e:
                    print(f"⚠️  Error finding accessories: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fall through to regular search
        
        # Handle "similar" or "more like" queries
        elif has_similar_intent or has_pronoun:
            # Find similar products using semantic search
            ref_idx = referenced_product.get('index')
            if ref_idx is not None:
                try:
                    ref_idx = int(ref_idx)
                    if 0 <= ref_idx < len(products_df):
                        ref_product = products_df.iloc[ref_idx]
                        print(f"🔍 Finding similar products to: {ref_product.get('name', ref_idx)} (index {ref_idx})")
                        
                        # Get reference product embedding - use Pinecone if available, otherwise local
                        ref_id = f"{ref_product.get('name', ref_idx)}_{ref_idx}"
                        ref_emb = None
                        
                        # Try Pinecone first (if available and OpenAI embedder is available)
                        if pinecone_client and pinecone_client.is_available() and openai_embedder:
                            # Build text representation of reference product for embedding
                            ref_text_parts = []
                            if pd.notna(ref_product.get('name')):
                                ref_text_parts.append(str(ref_product.get('name')))
                            if pd.notna(ref_product.get('description')):
                                ref_text_parts.append(str(ref_product.get('description')))
                            if pd.notna(ref_product.get('colors')):
                                ref_text_parts.append(f"colors: {ref_product.get('colors')}")
                            if pd.notna(ref_product.get('materials')):
                                ref_text_parts.append(f"materials: {ref_product.get('materials')}")
                            if pd.notna(ref_product.get('style_keywords')):
                                ref_text_parts.append(f"style: {ref_product.get('style_keywords')}")
                            
                            ref_text = " ".join(ref_text_parts)
                            ref_emb = openai_embedder.get_embedding(ref_text)
                            
                            if ref_emb is not None:
                                # Query Pinecone for similar products
                                # Get all product indices except the reference
                                all_indices = [idx for idx in products_df.index if idx != ref_idx]
                                matches = pinecone_client.query_with_product_indices(
                                    ref_emb,
                                    all_indices,
                                    top_k=top_k * 2  # Get more candidates to filter by similarity threshold
                                )
                                
                                if matches:
                                    # Filter by similarity threshold (only keep products with similarity > 0.7)
                                    filtered_matches = [(idx, score) for idx, score in matches if score > 0.7]
                                    if filtered_matches:
                                        # Sort by similarity and take top_k
                                        filtered_matches.sort(key=lambda x: x[1], reverse=True)
                                        similar_indices = [idx for idx, _ in filtered_matches[:top_k]]
                                        results_df = products_df.loc[similar_indices]
                                        print(f"   ✅ Found {len(results_df)} similar products using Pinecone (similarity > 0.7)")
                                    else:
                                        print(f"   ⚠️  No products with similarity > 0.7, using top matches")
                                        similar_indices = [idx for idx, _ in matches[:top_k]]
                                        results_df = products_df.loc[similar_indices]
                                else:
                                    print(f"   ⚠️  Pinecone returned no matches, falling back to local embeddings")
                                    ref_emb = None  # Fall through to local embeddings
                        
                        # Fallback to local embeddings
                        if ref_emb is None:
                            ref_emb_key = f"{ref_id}_text"
                            if ref_emb_key in embeddings_dict:
                                ref_emb = np.array(embeddings_dict[ref_emb_key])
                                
                                # Find similar products using local embeddings
                                similarities = []
                                for idx, row in products_df.iterrows():
                                    if idx == ref_idx:  # Skip the reference product itself
                                        continue
                                    product_id = f"{row.get('name', idx)}_{idx}"
                                    emb_key = f"{product_id}_text"
                                    
                                    if emb_key in embeddings_dict:
                                        product_emb = np.array(embeddings_dict[emb_key])
                                        similarity = np.dot(ref_emb, product_emb) / (
                                            np.linalg.norm(ref_emb) * np.linalg.norm(product_emb)
                                        )
                                        # Only include products with similarity > 0.7
                                        if similarity > 0.7:
                                            similarities.append((idx, similarity))
                                
                                # Sort by similarity and return top results
                                if similarities:
                                    similarities.sort(key=lambda x: x[1], reverse=True)
                                    similar_indices = [idx for idx, _ in similarities[:top_k]]
                                    results_df = products_df.loc[similar_indices]
                                    print(f"   ✅ Found {len(results_df)} similar products using local embeddings (similarity > 0.7)")
                                else:
                                    print(f"   ⚠️  No products with similarity > 0.7, returning empty results")
                                    results_df = pd.DataFrame()
                            else:
                                print(f"   ⚠️  Reference product embedding not found in local embeddings")
                                results_df = pd.DataFrame()
                        
                        # === Extract gender from tagged product for similar products ===
                        ref_category_similar = str(ref_product.get('category', '')).lower()
                        ref_gender_similar = None
                        # Check if gender column exists and has a value (ref_product is a Series)
                        if 'gender' in ref_product.index and pd.notna(ref_product['gender']):
                            ref_gender_similar = str(ref_product['gender']).lower()
                        elif ref_category_similar:
                            # Fallback: Extract gender from category (e.g., "Women's Knitwear" -> "women")
                            if 'women' in ref_category_similar:
                                ref_gender_similar = 'women'
                            elif 'men' in ref_category_similar:
                                ref_gender_similar = 'men'
                        
                        # Use tagged product's gender if available, otherwise fall back to UI filter
                        effective_gender_similar = ref_gender_similar if ref_gender_similar else gender_filter
                        print(f"   👤 Tagged product gender: {ref_gender_similar}, UI filter: {gender_filter}, effective: {effective_gender_similar}")
                        
                        # Apply gender filter from tagged product
                        if not results_df.empty and effective_gender_similar and effective_gender_similar != 'all':
                            if 'gender' in results_df.columns:
                                gender_mask = results_df['gender'].astype(str).str.lower() == effective_gender_similar.lower()
                                results_df = results_df[gender_mask]
                                print(f"   👤 Gender filter ({effective_gender_similar}) for similar products: {len(results_df)} products")
                            elif 'category' in results_df.columns:
                                if effective_gender_similar.lower() == 'men':
                                    gender_mask = results_df['category'].astype(str).str.lower().str.contains("men", na=False)
                                elif effective_gender_similar.lower() == 'women':
                                    gender_mask = results_df['category'].astype(str).str.lower().str.contains("women", na=False)
                                else:
                                    gender_mask = pd.Series([True] * len(results_df), index=results_df.index)
                                results_df = results_df[gender_mask]
                                print(f"   👤 Gender filter ({effective_gender_similar}) from category for similar products: {len(results_df)} products")
                        
                        # Apply filters from the query (e.g., "patterned sweaters" should filter by product type and pattern)
                        if not results_df.empty:
                            # Use parsed query if available, otherwise fall back to keyword matching
                            query_lower_similar = query_text.lower()
                            
                            # Filter by product type from parsed query or keywords
                            if parsed_query:
                                # Use parsed query product types
                                product_types_to_filter = []
                                if parsed_query.get('product_type'):
                                    product_types_to_filter.append(parsed_query['product_type'])
                                if parsed_query.get('product_types'):
                                    product_types_to_filter.extend(parsed_query['product_types'])
                                
                                if product_types_to_filter:
                                    type_mask = pd.Series([False] * len(results_df), index=results_df.index)
                                    for product_type in product_types_to_filter:
                                        product_type_lower = product_type.lower()
                                        # Check name and category
                                        name_match = results_df['name'].astype(str).str.lower().str.contains(product_type_lower, na=False)
                                        category_match = results_df['category'].astype(str).str.lower().str.contains(product_type_lower, na=False)
                                        type_mask |= (name_match | category_match)
                                    results_df = results_df[type_mask]
                                    print(f"   🎯 Filtered by parsed product type(s): {product_types_to_filter} -> {len(results_df)} products")
                            else:
                                # Fallback: keyword-based product type filtering
                                if 'sweater' in query_lower_similar or 'cardigan' in query_lower_similar or 'jumper' in query_lower_similar:
                                    sweater_keywords = ['sweater', 'cardigan', 'jumper', 'hoodie']
                                    type_mask = pd.Series([False] * len(results_df), index=results_df.index)
                                    for keyword in sweater_keywords:
                                        type_mask |= results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
                                    results_df = results_df[type_mask]
                                    print(f"   🧶 Filtered to sweaters/cardigans/jumpers: {len(results_df)} products")
                                
                                if 'shirt' in query_lower_similar or 'top' in query_lower_similar or 'polo' in query_lower_similar:
                                    shirt_keywords = ['shirt', 'top', 'polo', 'blouse', 'henley', 'tee', 't-shirt']
                                    type_mask = pd.Series([False] * len(results_df), index=results_df.index)
                                    for keyword in shirt_keywords:
                                        type_mask |= results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
                                    results_df = results_df[type_mask]
                                    print(f"   👔 Filtered to shirts/tops: {len(results_df)} products")
                            
                            # Filter by pattern if mentioned (from parsed query or keywords)
                            has_pattern_filter = False
                            if parsed_query:
                                # Check if pattern is in must_have features
                                must_have = parsed_query.get('filters', {}).get('must_have', [])
                                if 'pattern' in [f.lower() for f in must_have]:
                                    has_pattern_filter = True
                            
                            if has_pattern_filter or 'pattern' in query_lower_similar or 'patterned' in query_lower_similar:
                                # Keep only products with patterns
                                pattern_mask = (
                                    results_df['patterns'].notna() & 
                                    (results_df['patterns'].astype(str).str.lower() != 'nan') &
                                    (results_df['patterns'].astype(str).str.strip() != '')
                                )
                                results_df = results_df[pattern_mask]
                                print(f"   🎨 Filtered to patterned products: {len(results_df)} products")
                            
                            # Remove duplicates by index
                            results_df = results_df[~results_df.index.duplicated(keep='first')]
                            
                            # Final safety check: exclude the reference product itself
                            results_df = results_df[results_df.index != ref_idx]
                            print(f"   ✅ Excluded reference product (index {ref_idx}) from results")
                            
                            # Convert to dict format with deduplication
                            results_dict = []
                            seen_indices = set()
                            for idx, row in results_df.iterrows():
                                if idx in seen_indices:
                                    continue
                                seen_indices.add(idx)
                                product_dict = row.replace({np.nan: None}).to_dict()
                                product_dict['index'] = int(idx)
                                results_dict.append(product_dict)
                            
                            return jsonify({
                                'query': query_text,
                                'results': results_dict,
                                'count': len(results_dict)
                            })
                        else:
                            return jsonify({
                                'query': query_text,
                                'results': [],
                                'count': 0,
                                'message': "No similar products found. Try a different product or query."
                            })
                except (ValueError, IndexError, KeyError) as e:
                    print(f"⚠️  Error finding similar products: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fall through to regular search
    
    # Simple keyword-based filtering (can be enhanced with NLP)
    query_lower = query_text.lower()
    
    # Early check: Does this query imply a product search?
    # If not, return empty results immediately
    product_action_words = ['show', 'find', 'search', 'look', 'get', 'buy', 'want', 'need',
                           'see', 'display', 'list', 'recommend', 'suggest', 'give me',
                           'i want', 'i need', 'i\'m looking for', 'looking for', 'what',
                           'which', 'where can i']
    
    product_type_words = ['sweater', 'cardigan', 'shirt', 'pants', 'trousers', 'jacket', 
                         'coat', 'scarf', 'vest', 'sock', 'glove', 'hoodie', 'top', 'polo',
                         'henley', 'balaclava', 'jumper', 'blouse', 'tee', 't-shirt', 'sweatpants',
                         'hoodie', 'cardigan', 'jumper', 'overshirt', 'overshirts', 'accessories', 'accessory',
                         'dress', 'dresses', 'skirt', 'skirts', 'tank', 'tanks', 'blazer', 'blazers',
                         'jeans', 'jean', 'shorts', 'short', 'leggings', 'legging', 'joggers', 'jogger',
                         'jumpsuit', 'jumpsuits', 'gilet', 'gilets']
    
    product_attribute_words = ['black', 'white', 'navy', 'beige', 'brown', 'grey', 'gray',
                              'wool', 'cotton', 'cashmere', 'merino', 'silk', 'mohair',
                              'minimalist', 'classic', 'modern', 'casual', 'formal', 'oversized',
                              'fitted', 'relaxed', 'elegant', 'colorful', 'color', 'vibrant', 'bright',
                              'pop of color', 'bold', 'statement']
    
    # Category keywords that should also trigger product search
    category_keywords_for_search = ['accessories', 'knitwear', 'outerwear', 'bottoms', 'tops', 
                                   'footwear', 'bags', 'jewelry', 'underwear']
    
    price_words = ['price', 'dollar', 'cost', 'under', 'over', 'below', 'above', 'cheap',
                  'expensive', 'affordable', '$']
    
    has_action_word = any(action in query_lower for action in product_action_words)
    has_product_type = any(ptype in query_lower for ptype in product_type_words)
    has_attribute = any(attr in query_lower for attr in product_attribute_words)
    has_price = any(price_word in query_lower for price_word in price_words)
    has_category = any(cat in query_lower for cat in category_keywords_for_search)
    
    # Check for style/color phrases that indicate product search
    style_phrases = ['pop of color', 'something to wear', 'something for', 'wear for', 'wear with',
                     'what would i wear', 'what can i wear', 'what should i wear', 'what could i wear',
                     'what to wear', 'wear in', 'wear to', 'outfit for', 'clothes for', 'dress for',
                     'cold night', 'warm day', 'beach day', 'fall day', 'winter', 'summer', 'spring']
    has_style_phrase = any(phrase in query_lower for phrase in style_phrases)
    
    # Query implies product search if it has product-related content
    # Allow queries with just attributes (e.g., "black wool") as they're clearly product searches
    implies_product_search = (
        has_product_type or  # Has a product type
        has_category or  # Has a category keyword (e.g., "accessories", "knitwear")
        (has_action_word and (has_attribute or has_price or has_style_phrase)) or  # Action + attribute/price/style
        (has_attribute and has_price) or  # Attribute + price
        has_attribute or  # Just attributes (e.g., "black wool", "minimalist classic")
        has_style_phrase or  # Style phrases like "pop of color", "something to wear"
        (len([x for x in [has_action_word, has_product_type, has_attribute, has_price, has_category, has_style_phrase] if x]) >= 2)
    )
    
    # If query doesn't imply product search, return empty immediately
    if not implies_product_search:
        return jsonify({
            'query': query_text,
            'results': [],
            'count': 0
        })
    
    # Start with all products
    results_df = products_df.copy()
    
    # Apply gender filter if specified
    if gender_filter and gender_filter != 'all':
        # Check if products have a gender column
        if 'gender' in results_df.columns:
            # Use exact match (case-insensitive) for gender
            gender_mask = results_df['gender'].astype(str).str.lower() == gender_filter.lower()
            results_df = results_df[gender_mask]
            print(f"   👤 Gender filter ({gender_filter}): {len(results_df)} products")
        else:
            # Fallback: try to infer from category or name
            if 'category' in results_df.columns:
                if gender_filter.lower() == 'men':
                    gender_mask = results_df['category'].astype(str).str.lower().str.contains("men", na=False)
                elif gender_filter.lower() == 'women':
                    gender_mask = results_df['category'].astype(str).str.lower().str.contains("women", na=False)
                else:
                    gender_mask = pd.Series([True] * len(results_df), index=results_df.index)
                results_df = results_df[gender_mask]
                print(f"   👤 Gender filter ({gender_filter}) from category: {len(results_df)} products")
    
    # Use parsed query if available, otherwise fall back to keyword-based
    # Only apply filtering if use_filtering is True
    if parsed_query and use_filtering:
        # Apply filters based on parsed query
        strict_mode = parsed_query.get('filters', {}).get('strict', False)
        
        # Filter by product type from parsed query
        # Use the existing product_types dictionary for accurate matching
        product_types_to_filter = []
        if parsed_query.get('product_type'):
            product_types_to_filter.append(parsed_query['product_type'])
        if parsed_query.get('product_types'):
            product_types_to_filter.extend(parsed_query['product_types'])
        
        # Remove duplicates
        product_types_to_filter = list(set(product_types_to_filter))
        
        if product_types_to_filter:
            # Load product_types dictionary (defined later in fallback code)
            # We'll define it here for use with parsed queries
            product_types_dict = {
                'scarf': {'keywords': ['scarf', 'scarves'], 'related': []},
                'vest': {'keywords': ['vest', 'vests', 'waistcoat', 'waistcoats'], 'related': []},
                'sock': {'keywords': ['sock', 'socks', 'hosiery'], 'related': []},
                'socks': {'keywords': ['sock', 'socks', 'hosiery'], 'related': []},
                't-shirt': {'keywords': ['t-shirt', 't shirt', 'tshirt', 'tee', 'tees', 't-shirts'], 'related': []},
                'glove': {'keywords': ['glove', 'gloves', 'mitten', 'mittens'], 'related': []},
                'sweater': {'keywords': ['sweater', 'sweaters'], 'related': ['cardigan', 'jumper', 'hoodie']},
                'cardigan': {'keywords': ['cardigan', 'cardigans'], 'related': ['sweater']},
                'jumper': {'keywords': ['jumper', 'jumpers'], 'related': ['sweater']},
                'hoodie': {'keywords': ['hoodie', 'hoodies'], 'related': ['sweater']},
                'shirt': {'keywords': ['shirt', 'shirts', 'blouse', 'blouses', 'overshirt', 'overshirts'], 'related': ['polo', 'henley', 't-shirt']},
                'pants': {'keywords': ['pants', 'trousers', 'trouser'], 'related': []},
                'jacket': {'keywords': ['jacket', 'jackets', 'coat', 'coats'], 'related': []},
                'top': {'keywords': ['top', 'tops'], 'related': ['shirt', 't-shirt', 'polo', 'henley']},
                'polo': {'keywords': ['polo', 'polos'], 'related': ['shirt']},
                'henley': {'keywords': ['henley', 'henleys'], 'related': ['shirt', 'top']},
                'balaclava': {'keywords': ['balaclava', 'balaclavas'], 'related': []},
                'hat': {'keywords': ['hat', 'hats', 'cap', 'caps', 'beanie', 'beanies'], 'related': ['balaclava']},
                'dress': {'keywords': ['dress', 'dresses'], 'related': []},
                'skirt': {'keywords': ['skirt', 'skirts'], 'related': []},
                'tank': {'keywords': ['tank', 'tanks', 'camisole', 'camisoles'], 'related': ['top']},
                'blazer': {'keywords': ['blazer', 'blazers'], 'related': ['jacket']},
                'jeans': {'keywords': ['jeans', 'jean'], 'related': ['pants']},
                'shorts': {'keywords': ['shorts', 'short'], 'related': ['pants', 'bottoms']},
                'leggings': {'keywords': ['leggings', 'legging'], 'related': ['pants', 'bottoms']},
                'joggers': {'keywords': ['joggers', 'jogger'], 'related': ['pants', 'bottoms']},
                'jumpsuit': {'keywords': ['jumpsuit', 'jumpsuits', 'romper', 'rompers'], 'related': []},
                'gilet': {'keywords': ['gilet', 'gilets'], 'related': ['vest', 'jacket']},
            }
            
            type_mask = pd.Series([False] * len(results_df), index=results_df.index)
            for product_type in product_types_to_filter:
                product_type_lower = product_type.lower()
                # Find matching product type in dictionary
                type_info = None
                for pt_key, pt_info in product_types_dict.items():
                    if product_type_lower == pt_key or product_type_lower in pt_info['keywords']:
                        type_info = pt_info
                        break
                
                if type_info:
                    # Get all keywords including related types
                    all_keywords = type_info['keywords'].copy()
                    for related_type in type_info['related']:
                        if related_type in product_types_dict:
                            all_keywords.extend(product_types_dict[related_type]['keywords'])
                    
                    # Check both name and category
                    name_match = results_df['name'].astype(str).str.lower().str.contains(
                        '|'.join(all_keywords), na=False, regex=True
                    )
                    category_match = results_df['category'].astype(str).str.lower().str.contains(
                        product_type_lower, na=False
                    )
                    type_mask |= (name_match | category_match)
                else:
                    # Fallback: direct string match
                    name_match = results_df['name'].astype(str).str.lower().str.contains(
                        product_type_lower, na=False
                    )
                    category_match = results_df['category'].astype(str).str.lower().str.contains(
                        product_type_lower, na=False
                    )
                    type_mask |= (name_match | category_match)
            
            results_df = results_df[type_mask]
        
        # Apply attribute filters from parsed query
        attributes = parsed_query.get('attributes', {})
        
        # Filter by colors
        if attributes.get('colors'):
            color_mask = pd.Series([False] * len(results_df), index=results_df.index)
            for color in attributes['colors']:
                color_mask |= results_df['colors'].astype(str).str.lower().str.contains(color, na=False)
            results_df = results_df[color_mask]
        
        # Filter by materials
        if attributes.get('materials'):
            material_mask = pd.Series([False] * len(results_df), index=results_df.index)
            for material in attributes['materials']:
                material_mask |= results_df['materials'].astype(str).str.lower().str.contains(material, na=False)
            results_df = results_df[material_mask]
        
        # Filter by styles from parsed query (e.g., "pop of color", "funky", "professional")
        if attributes.get('styles'):
            style_mask = pd.Series([False] * len(results_df), index=results_df.index)
            for style in attributes['styles']:
                # Check style_keywords column (populated during enrichment)
                style_mask |= results_df['style_keywords'].astype(str).str.lower().str.contains(style.lower(), na=False)
                # Also check name and description for style-related terms
                name_desc = (
                    results_df['name'].astype(str).str.lower() + ' ' + 
                    results_df['description'].astype(str).str.lower()
                )
                style_mask |= name_desc.str.contains(style.lower(), na=False)
            results_df = results_df[style_mask]
            print(f"   🎨 Filtered by OpenAI-parsed styles: {attributes['styles']} -> {len(results_df)} products")
        
        # Filter by features (must_have and must_not_have)
        filters = parsed_query.get('filters', {})
        must_have_features = filters.get('must_have', [])
        must_not_have_features = filters.get('must_not_have', [])
        
        # Apply must_have features
        if must_have_features:
            for feature in must_have_features:
                feature_lower = feature.lower()
                # Check in name and description
                name_desc = (results_df['name'].astype(str) + ' ' + 
                           results_df.get('description', pd.Series([''] * len(results_df))).astype(str)).str.lower()
                has_feature = name_desc.str.contains(feature_lower, na=False, regex=False)
                results_df = results_df[has_feature]
        
        # Apply must_not_have features
        if must_not_have_features:
            for feature in must_not_have_features:
                feature_lower = feature.lower()
                # Check in name and description
                name_desc = (results_df['name'].astype(str) + ' ' + 
                           results_df.get('description', pd.Series([''] * len(results_df))).astype(str)).str.lower()
                has_feature = name_desc.str.contains(feature_lower, na=False, regex=False)
                results_df = results_df[~has_feature]
        
        # Apply price filters
        price_info = parsed_query.get('price', {})
        if price_info.get('max') is not None:
            results_df = results_df[results_df['price'].astype(int) <= price_info['max']]
        if price_info.get('min') is not None:
            results_df = results_df[results_df['price'].astype(int) >= price_info['min']]
        
    else:
        # Fallback to keyword-based filtering (existing code)
        pass
    
    # Detect "only" keyword - this enforces strict filtering
    strict_mode = 'only' in query_lower or 'just' in query_lower
    
    # Flag to control whether fallback filtering runs
    # When parsed_query is available (OpenAI parsing worked), skip keyword-based filtering
    # to avoid over-filtering on situational queries like "what would I wear in paris"
    # However, if parsed_query exists but has no useful filtering info (null product_type, etc.),
    # we should still run fallback filtering
    # Also respect use_filtering flag
    if parsed_query:
        # Check if parsed query has useful filtering information
        has_product_type = parsed_query.get('product_type') or parsed_query.get('product_types')
        has_attributes = any(parsed_query.get('attributes', {}).values())
        has_price = parsed_query.get('price', {}).get('min') or parsed_query.get('price', {}).get('max')
        has_filters = parsed_query.get('filters', {}).get('must_have') or parsed_query.get('filters', {}).get('must_not_have')
        has_useful_info = has_product_type or has_attributes or has_price or has_filters
        # Only skip fallback if parsed query has useful filtering info
        use_fallback_filtering = not has_useful_info and use_filtering
    else:
        use_fallback_filtering = use_filtering
    
    # Filter by product type (scarf, vest, sock, t-shirt, glove, etc.)
    # Define product types with their keywords and related types (e.g., cardigans are sweaters)
    product_types = {
        'scarf': {
            'keywords': ['scarf', 'scarves'],
            'related': []
        },
        'vest': {
            'keywords': ['vest', 'vests', 'waistcoat', 'waistcoats'],
            'related': []
        },
        'sock': {
            'keywords': ['sock', 'socks', 'hosiery'],
            'related': []
        },
        't-shirt': {
            'keywords': ['t-shirt', 't shirt', 'tshirt', 'tee', 'tees', 't-shirts'],
            'related': []
        },
        'glove': {
            'keywords': ['glove', 'gloves', 'mitten', 'mittens'],
            'related': []
        },
        'sweater': {
            'keywords': ['sweater', 'sweaters'],
            'related': ['cardigan', 'jumper', 'hoodie']  # Cardigans and jumpers are types of sweaters
        },
        'cardigan': {
            'keywords': ['cardigan', 'cardigans'],
            'related': ['sweater']  # Cardigans are sweaters
        },
        'jumper': {
            'keywords': ['jumper', 'jumpers'],
            'related': ['sweater']  # Jumpers are sweaters
        },
        'hoodie': {
            'keywords': ['hoodie', 'hoodies'],
            'related': ['sweater']  # Hoodies are sweaters
        },
        'shirt': {
            'keywords': ['shirt', 'shirts', 'blouse', 'blouses', 'overshirt', 'overshirts'],
            'related': ['polo', 'henley', 't-shirt']
        },
        'pants': {
            'keywords': ['pants', 'trousers', 'trouser'],
            'related': []
        },
        'jacket': {
            'keywords': ['jacket', 'jackets', 'coat', 'coats'],
            'related': []
        },
        'top': {
            'keywords': ['top', 'tops'],
            'related': ['shirt', 't-shirt', 'polo', 'henley']
        },
        'polo': {
            'keywords': ['polo', 'polos'],
            'related': ['shirt']
        },
        'henley': {
            'keywords': ['henley', 'henleys'],
            'related': ['shirt', 'top']
        },
        'balaclava': {
            'keywords': ['balaclava', 'balaclavas'],
            'related': []
        },
        'hat': {
            'keywords': ['hat', 'hats', 'cap', 'caps', 'beanie', 'beanies'],
            'related': ['balaclava']
        },
        'dress': {
            'keywords': ['dress', 'dresses'],
            'related': []
        },
        'skirt': {
            'keywords': ['skirt', 'skirts'],
            'related': []
        },
        'tank': {
            'keywords': ['tank', 'tanks', 'camisole', 'camisoles'],
            'related': ['top']
        },
        'blazer': {
            'keywords': ['blazer', 'blazers'],
            'related': ['jacket']
        },
        'jeans': {
            'keywords': ['jeans', 'jean'],
            'related': ['pants']
        },
        'shorts': {
            'keywords': ['shorts', 'short'],
            'related': ['pants', 'bottoms']
        },
        'leggings': {
            'keywords': ['leggings', 'legging'],
            'related': ['pants', 'bottoms']
        },
        'joggers': {
            'keywords': ['joggers', 'jogger'],
            'related': ['pants', 'bottoms']
        },
        'jumpsuit': {
            'keywords': ['jumpsuit', 'jumpsuits', 'romper', 'rompers'],
            'related': []
        },
        'gilet': {
            'keywords': ['gilet', 'gilets'],
            'related': ['vest', 'jacket']
        },
        'accessories': {
            'keywords': ['scarf', 'scarves', 'glove', 'gloves', 'sock', 'socks', 'hat', 'hats', 'cap', 'caps', 'beanie', 'beanies', 'balaclava', 'vest', 'vests', 'belt', 'belts', 'tie', 'ties', 'ring', 'rings'],
            'related': []  # Accessories are standalone, not related to other types
        },
        'bottoms': {
            'keywords': ['pants', 'trousers', 'trouser', 'jeans', 'chinos', 'shorts', 'leggings', 'joggers', 'skirt', 'skirts'],
            'related': []  # Bottoms are standalone
        },
        'tops': {
            'keywords': ['top', 'tops', 'shirt', 'shirts', 'blouse', 'blouses', 't-shirt', 't shirt', 'tshirt', 'tee', 'tees', 'polo', 'polos', 'henley', 'henleys'],
            'related': []  # Tops are standalone
        },
    }
    
    detected_product_types = []
    for product_type, type_info in product_types.items():
        # Check if the product type name itself is in the query (e.g., "accessories", "bottoms", "tops")
        if product_type in query_lower:
            detected_product_types.append(product_type)
        # Also check keywords
        for keyword in type_info['keywords']:
            if keyword in query_lower:
                if product_type not in detected_product_types:
                    detected_product_types.append(product_type)
                break
    
    # Apply product type filter (including related types)
    # Only apply if using fallback filtering (OpenAI parsing not available)
    if use_fallback_filtering and detected_product_types:
        type_mask = pd.Series([False] * len(results_df), index=results_df.index)
        for product_type in detected_product_types:
            type_info = product_types[product_type]
            # Get all keywords including related types
            all_keywords = type_info['keywords'].copy()
            for related_type in type_info['related']:
                if related_type in product_types:
                    all_keywords.extend(product_types[related_type]['keywords'])
            
            # Check both name and category
            name_match = results_df['name'].astype(str).str.lower().str.contains(
                '|'.join(all_keywords), na=False, regex=True
            )
            category_match = results_df['category'].astype(str).str.lower().str.contains(
                product_type, na=False
            )
            type_mask |= (name_match | category_match)
        results_df = results_df[type_mask]
    
    # Also check for category names in query (e.g., "knitwear", "accessories", "bottoms", "tops")
    # But only if they weren't already detected as product types (to avoid double filtering)
    category_keywords = ['knitwear', 'outerwear', 'footwear', 'bags', 'jewelry', 'underwear']
    detected_categories = []
    for category_keyword in category_keywords:
        if category_keyword in query_lower:
            detected_categories.append(category_keyword)
    
    # Filter by category if detected (only for categories that aren't product types)
    # Only apply if using fallback filtering
    if use_fallback_filtering and detected_categories:
        category_mask = pd.Series([False] * len(results_df), index=results_df.index)
        for category_keyword in detected_categories:
            # Use exact match or word boundary to avoid partial matches
            category_mask |= results_df['category'].astype(str).str.lower().str.contains(
                category_keyword, na=False, regex=False
            )
        results_df = results_df[category_mask]
    
        # Special handling: if "accessories" is in query, apply strict filtering
        if 'accessories' in query_lower or 'accessory' in query_lower:
            # Filter by accessory keywords in name (must match at least one)
            accessory_name_mask = pd.Series([False] * len(results_df), index=results_df.index)
            accessory_keywords = ['scarf', 'glove', 'sock', 'hat', 'cap', 'beanie', 'balaclava', 'vest', 'belt', 'tie', 'ring']
        for keyword in accessory_keywords:
            accessory_name_mask |= results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
        results_df = results_df[accessory_name_mask]
        
        # Also check category if available
        if 'category' in results_df.columns:
            category_mask = results_df['category'].astype(str).str.lower().str.contains('accessories', na=False, regex=False)
            # Combine: must match name keywords OR category
            results_df = results_df[accessory_name_mask | category_mask]
        
        # Explicitly exclude non-accessories (dresses, skirts, sweaters, shorts, etc.)
        exclude_keywords = ['dress', 'skirt', 'sweater', 'cardigan', 'jumper', 'hoodie', 'shirt', 'blouse', 'polo', 'top', 'pants', 'trousers', 'jeans', 'shorts', 'jacket', 'coat', 'jumper', 'overshirt']
        exclude_mask = pd.Series([False] * len(results_df), index=results_df.index)
        for keyword in exclude_keywords:
            exclude_mask |= results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
        results_df = results_df[~exclude_mask]
        
        print(f"   🎯 Strict accessories filter: {len(results_df)} products")
    
    if use_fallback_filtering and 'bottoms' in query_lower and 'bottoms' not in [pt.lower() for pt in detected_product_types]:
        # Filter to only bottoms category
        category_mask = results_df['category'].astype(str).str.lower().str.contains('bottoms', na=False, regex=False)
        results_df = results_df[category_mask]
        # Also filter by bottom keywords in name
        bottom_name_mask = pd.Series([False] * len(results_df), index=results_df.index)
        bottom_keywords = ['pants', 'trousers', 'jeans', 'chinos', 'shorts', 'leggings']
        for keyword in bottom_keywords:
            bottom_name_mask |= results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
        results_df = results_df[bottom_name_mask]
        # Exclude tops explicitly
        top_exclude_mask = ~results_df['name'].astype(str).str.lower().str.contains('top|shirt|blouse|dress', na=False, regex=True)
        results_df = results_df[top_exclude_mask]
        print(f"   🎯 Strict bottoms filter: {len(results_df)} products")
    
    if use_fallback_filtering and 'tops' in query_lower and 'tops' not in [pt.lower() for pt in detected_product_types]:
        # Filter to only tops category
        category_mask = results_df['category'].astype(str).str.lower().str.contains('tops', na=False, regex=False)
        results_df = results_df[category_mask]
        # Also filter by top keywords in name
        top_name_mask = pd.Series([False] * len(results_df), index=results_df.index)
        top_keywords = ['top', 'shirt', 'blouse', 't-shirt', 'polo', 'henley', 'tee']
        for keyword in top_keywords:
            top_name_mask |= results_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
        results_df = results_df[top_name_mask]
        # Exclude bottoms explicitly
        bottom_exclude_mask = ~results_df['name'].astype(str).str.lower().str.contains('pants|trousers|jeans|chinos|shorts', na=False, regex=True)
        results_df = results_df[bottom_exclude_mask]
        print(f"   🎯 Strict tops filter: {len(results_df)} products")
    
    # Filter by material (apply before color to avoid empty sets)
    materials = ['wool', 'cotton', 'cashmere', 'merino', 'silk', 'mohair', 'alpaca']
    material_filters = []
    for material in materials:
        if material in query_lower:
            material_filters.append(material)
            break  # Only take first material found
    
    if use_fallback_filtering and material_filters:
        material = material_filters[0]
        results_df = results_df[
            results_df['materials'].astype(str).str.lower().str.contains(material, na=False)
        ]
    
    # Filter by color - check ALL colors in query
    colors = ['black', 'white', 'navy', 'beige', 'brown', 'grey', 'gray', 'red', 'blue', 
              'green', 'yellow', 'pink', 'purple', 'orange', 'tan', 'camel', 'cream', 
              'ivory', 'charcoal', 'olive']
    color_filters = []
    for color in colors:
        if color in query_lower:
            color_filters.append(color)
    
    # Apply color filters (must match at least one)
    # Only apply if using fallback filtering
    if use_fallback_filtering and color_filters:
        # If only one color is specified, be strict: only return products where it's the primary color
        if len(color_filters) == 1:
            color = color_filters[0]
            # Split colors and check if the requested color is first (primary)
            def is_primary_color(colors_str, target_color):
                if pd.isna(colors_str) or not colors_str:
                    return False
                colors_list = [c.strip().lower() for c in str(colors_str).split(',')]
                # Check if target color is first (primary) or if there's only one color
                if len(colors_list) == 0:
                    return False
                # Primary color is the first one, or if only one color exists
                first_color = colors_list[0].strip()
                return first_color == target_color.lower() or (len(colors_list) == 1 and first_color == target_color.lower())
            
            # Only keep products where the requested color is primary
            initial_count = len(results_df)
            primary_color_mask = results_df['colors'].apply(lambda x: is_primary_color(x, color))
            results_df = results_df[primary_color_mask]
            print(f"   🔴 Strict color filter: {initial_count} -> {len(results_df)} products where '{color}' is the primary color")
            if len(results_df) > 0:
                print(f"   Sample filtered products:")
                for idx, row in results_df.head(5).iterrows():
                    print(f"      - {row.get('name', 'N/A')}: colors='{row.get('colors', 'N/A')}'")
            else:
                print(f"   ⚠️  No products found with '{color}' as primary color")
        else:
            # Multiple colors: match any of them
            color_mask = pd.Series([False] * len(results_df), index=results_df.index)
            for color in color_filters:
                color_match = results_df['colors'].astype(str).str.lower().str.contains(color, na=False)
                color_mask |= color_match
            results_df = results_df[color_mask]
    
    # Handle style/color phrases like "pop of color", "colorful", "vibrant"
    # Only apply if OpenAI parsing didn't already handle it via style keywords
    # AND if using fallback filtering
    if use_fallback_filtering and (not parsed_query or not parsed_query.get('attributes', {}).get('styles')):
        # Fallback: use keyword matching only if OpenAI didn't parse styles
        if 'pop of color' in query_lower or 'colorful' in query_lower or 'vibrant' in query_lower or 'bright' in query_lower:
            # Filter for products with vibrant colors (exclude neutral/muted colors)
            neutral_colors = ['black', 'white', 'navy', 'beige', 'brown', 'grey', 'gray', 'tan', 'camel', 'cream', 'ivory', 'charcoal', 'olive']
            vibrant_colors = ['red', 'blue', 'green', 'yellow', 'pink', 'purple', 'orange']
            
            # Keep products that have vibrant colors as primary or secondary
            color_mask = pd.Series([False] * len(results_df), index=results_df.index)
            for idx, row in results_df.iterrows():
                colors_str = str(row.get('colors', ''))
                if pd.notna(colors_str) and colors_str.lower() != 'nan':
                    colors_list = [c.strip().lower() for c in colors_str.split(',')]
                    # Check if any vibrant color is in the list
                    has_vibrant = any(color in vibrant_colors for color in colors_list)
                    # Exclude if only neutral colors
                    only_neutral = all(color in neutral_colors for color in colors_list if color)
                    if has_vibrant and not only_neutral:
                        color_mask[idx] = True
            
            results_df = results_df[color_mask]
            print(f"   🎨 Filtered for colorful/vibrant products: {len(results_df)} products")
    
    # Filter by price (apply last, as it's often optional)
    # Only apply if using fallback filtering
    if use_fallback_filtering and ('under' in query_lower or '$' in query_lower or 'dollar' in query_lower):
        # Extract price - handle multiple formats: "$200", "200 dollars", "under 200", etc.
        import re
        max_price = None
        
        # Try $200 format first
        price_matches = re.findall(r'\$(\d+)', query_text)
        if price_matches:
            max_price = int(price_matches[0])
        else:
            # Try "200 dollars" or "200 dollar" format
            price_matches = re.findall(r'(\d+)\s*dollars?', query_lower)
            if price_matches:
                max_price = int(price_matches[0])
            else:
                # Try "under 200" or "below 200" format (number after "under"/"below")
                price_matches = re.findall(r'(?:under|below|less than|max|maximum)\s+(\d+)', query_lower)
                if price_matches:
                    max_price = int(price_matches[0])
        
        if max_price is not None:
            results_df = results_df[results_df['price'].astype(int) <= max_price]
    
    # Filter by style - only use hardcoded list if OpenAI parsing didn't provide styles
    # (OpenAI parsing handles "pop of color", "funky", "professional", etc.)
    # Also only apply if using fallback filtering
    style_filters = []
    if use_fallback_filtering and (not parsed_query or not parsed_query.get('attributes', {}).get('styles')):
        # Fallback: use hardcoded style keywords only if OpenAI didn't parse any
        styles = ['minimalist', 'classic', 'modern', 'casual', 'formal', 'oversized', 'fitted', 
                  'relaxed', 'elegant', 'sophisticated', 'versatile']
        for style in styles:
            if style in query_lower:
                style_filters.append(style)
        
        # Apply style filters
        # In strict mode ("only"), style must match. Otherwise, use for ranking only.
        if style_filters:
            if strict_mode:
                # Strict mode: must match at least one style keyword
                style_mask = pd.Series([False] * len(results_df), index=results_df.index)
                for style in style_filters:
                    style_mask |= results_df['style_keywords'].astype(str).str.lower().str.contains(style, na=False)
                results_df = results_df[style_mask]
            # In non-strict mode, style filters are used for semantic ranking later
    
    # Handle negative filters (exclusions) - generalized approach
    # Only apply if using fallback filtering
    normalized_excluded = []
    excluded_features = []  # Initialize here so it's always defined
    if use_fallback_filtering:
        # Detect "no X", "without X", "no Xs" patterns
        import re
        
        # Common product types to ignore when extracting exclusions
        # NOTE: This is a list, not the product_types dictionary defined earlier
        product_type_names = ['sweater', 'sweaters', 'cardigan', 'cardigans', 'hoodie', 'hoodies',
                             'shirt', 'shirts', 'top', 'tops', 'pants', 'trousers', 'jacket', 'jackets']
        
        # Pattern to match: "no/without [feature]" or "[feature] with no/without [feature2]"
        negative_patterns = [
            r'\bno\s+(\w+)s?\b',  # "no buttons", "no pattern"
            r'\bwithout\s+(?:a\s+)?(\w+)s?\b',  # "without a hood", "without buttons"
            r'\bwith\s+no\s+(\w+)s?\b',  # "with no buttons" (captures buttons, not sweaters)
        ]
        
        excluded_features = []
        
        # Extract excluded features from query
        for pattern in negative_patterns:
            matches = re.findall(pattern, query_lower)
            if matches:
                for match in matches:
                    if isinstance(match, tuple):
                        # For patterns with multiple groups, take the feature (not product type)
                        for m in match:
                            if m and m.lower() not in product_type_names:
                                excluded_features.append(m)
                    else:
                        if match and match.lower() not in product_type_names:
                            excluded_features.append(match)
    
    # Normalize feature names
    feature_mapping = {
        'pattern': 'pattern',
        'patterns': 'pattern',
        'button': 'button',
        'buttons': 'button',
        'hood': 'hood',
        'zipper': 'zipper',
        'zippers': 'zipper',
        'zip': 'zipper',
        'pocket': 'pocket',
        'pockets': 'pocket',
        'collar': 'collar',
        'collars': 'collar',
               'sleeve': 'sleeve',
        'sleeves': 'sleeve',
        'cuff': 'cuff',
        'cuffs': 'cuff',
    }
    
    normalized_excluded = []
    for feature in excluded_features:
        normalized = feature_mapping.get(feature.lower(), feature.lower())
        if normalized not in normalized_excluded:
            normalized_excluded.append(normalized)
    
    # Apply exclusions
    for feature in normalized_excluded:
        if feature == 'pattern':
            # Exclude items with patterns
            pattern_mask = (
                results_df['patterns'].isna() | 
                (results_df['patterns'].astype(str).str.lower() == 'nan') |
                (results_df['patterns'].astype(str).str.strip() == '') |
                (results_df['patterns'].astype(str).str.lower() == 'none')
            )
            results_df = results_df[pattern_mask]
        else:
            # For other features, check product name and description
            # Exclude items that mention the feature
            feature_keywords = {
                'button': ['button', 'buttons', 'buttoned', 'button-up', 'button down'],
                'hood': ['hood', 'hooded', 'hoodie'],
                'zipper': ['zipper', 'zip', 'zipped', 'zip-up', 'zip up'],
                'pocket': ['pocket', 'pockets'],
                'collar': ['collar', 'collared'],
                'sleeve': ['sleeve', 'sleeved'],  # Note: "sleeveless" means no sleeves, handled separately
                'cuff': ['cuff', 'cuffs', 'cuffed'],
            }
            
            if feature in feature_keywords:
                keywords = feature_keywords[feature]
                # Check both name and description
                name_desc = (
                    results_df['name'].astype(str).str.lower() + ' ' + 
                    results_df['description'].astype(str).str.lower()
                )
                
                # Exclude items that contain any of the keywords
                exclude_mask = pd.Series([False] * len(results_df), index=results_df.index)
                for keyword in keywords:
                    exclude_mask |= name_desc.str.contains(keyword, na=False, regex=False)
                
                # Exclude matching items
                results_df = results_df[~exclude_mask]
    
    # Special cases for common exclusions
    # "sleeveless" means no sleeves
    # Only apply if using fallback filtering
    if use_fallback_filtering and 'sleeveless' in query_lower:
        name_desc = (
            results_df['name'].astype(str).str.lower() + ' ' + 
            results_df['description'].astype(str).str.lower()
        )
        # Keep only items that mention "sleeveless"
        results_df = results_df[name_desc.str.contains('sleeveless', na=False, regex=False)]
    
    # "solid" can mean no pattern
    # Only apply if using fallback filtering
    if use_fallback_filtering and 'solid' in query_lower and 'pattern' not in normalized_excluded:
        # "solid" means no pattern
        pattern_mask = (
            results_df['patterns'].isna() | 
            (results_df['patterns'].astype(str).str.lower() == 'nan') |
            (results_df['patterns'].astype(str).str.strip() == '') |
            (results_df['patterns'].astype(str).str.lower().str.contains('solid', na=False))
        )
        results_df = results_df[pattern_mask]
    
    # Track which filters were applied (so we don't lose them)
    has_accessories_filter = 'accessories' in query_lower or 'accessory' in query_lower
    has_bottoms_filter = 'bottoms' in query_lower
    has_tops_filter = 'tops' in query_lower
    
    filters_applied = {
        'product_type': len(detected_product_types) > 0,
        'category': len(detected_categories) > 0,
        'accessories': has_accessories_filter,
        'bottoms': has_bottoms_filter,
        'tops': has_tops_filter,
        'color': len(color_filters) > 0,
        'material': any(material in query_lower for material in materials),
        'style': len(style_filters) > 0 and strict_mode,  # Style only enforced in strict mode
        'price': 'under' in query_lower or '$' in query_lower or 'dollar' in query_lower or 'below' in query_lower,
        'exclusions': len(normalized_excluded) > 0,
        'strict': strict_mode
    }
    
    # Apply semantic ranking if enabled (for ablation study)
    if use_semantic:
        # If we have embeddings and filtered results, do semantic search ONLY on filtered results
        # IMPORTANT: Store the filtered indices BEFORE semantic search to ensure we don't add back non-matching products
        filtered_indices_before_semantic = set(results_df.index) if not results_df.empty else set()
        print(f"   📊 Before semantic search: {len(filtered_indices_before_semantic)} products passed all filters")
        
        if not results_df.empty:
            # Choose embedding method based on what's available
            query_emb = None
            
            # If Pinecone is available, use OpenAI embeddings (1536-dim) to match Pinecone index
            if pinecone_client and pinecone_client.is_available() and openai_embedder:
                query_emb = openai_embedder.get_embedding(query_text)
                if query_emb is not None:
                    # Use Pinecone for vector search on filtered products
                    product_indices = results_df.index.tolist()
                    matches = pinecone_client.query_with_product_indices(
                        query_emb,
                        product_indices,
                        top_k=top_k
                    )
                    
                    if matches:
                        # Sort by similarity score (already sorted by Pinecone)
                        sorted_indices = [idx for idx, _ in matches]
                        print(f"   🔍 Pinecone returned {len(sorted_indices)} matches")
                        # STRICT: Only keep indices that are in our filtered results
                        sorted_indices = [idx for idx in sorted_indices if idx in filtered_indices_before_semantic]
                        print(f"   ✅ After strict filter check: {len(sorted_indices)} matches still in filtered set")
                        if sorted_indices:
                            # Reorder filtered results by similarity, but only include products that passed all filters
                            results_df = results_df.loc[sorted_indices]
                            print(f"   📦 Final results: {len(results_df)} products (all should have '{color_filters[0] if color_filters else 'N/A'}' as primary color)")
                        else:
                            # If Pinecone didn't return any matching products, keep the filtered results as-is
                            print(f"   ⚠️  Pinecone returned no products matching filters, using filtered results as-is")
                    else:
                        # If Pinecone returned no matches, keep the filtered results as-is
                        pass
                else:
                    # OpenAI embedder unavailable, will fall back to local embeddings below
                    pass
            
            # Fallback to local embeddings (sentence-transformers, 384-dim) ONLY if Pinecone is not available
            # IMPORTANT: If Pinecone is available but returned no matches, we should NOT fall back to local embeddings
            # because that would mix 1536-dim (OpenAI) with 384-dim (sentence-transformers) embeddings
            # Instead, we just use the filtered results as-is (which is already done above)
            use_local_embeddings = False
            if query_emb is None and enricher and embeddings_dict:
                # Pinecone not available OR OpenAI embedder not available, use local embeddings
                # This is the only case where we should use local embeddings
                if not (pinecone_client and pinecone_client.is_available() and openai_embedder):
                    query_emb = enricher.get_text_embedding(query_text)
                    use_local_embeddings = True
                    print(f"   📦 Using local embeddings (Pinecone not available or OpenAI embedder not available)")
            
            if query_emb is not None and embeddings_dict and use_local_embeddings:
                # Use local embeddings (384-dim sentence-transformers)
                similarities = []
                for idx in results_df.index:
                    row = results_df.loc[idx]
                    product_id = f"{row.get('name', idx)}_{idx}"
                    emb_key = f"{product_id}_text"
                    
                    if emb_key in embeddings_dict:
                        product_emb = np.array(embeddings_dict[emb_key])
                        # Verify dimensions match
                        if len(query_emb) != len(product_emb):
                            print(f"   ⚠️  Dimension mismatch: query={len(query_emb)}, product={len(product_emb)}, skipping")
                            continue
                        similarity = np.dot(query_emb, product_emb) / (
                            np.linalg.norm(query_emb) * np.linalg.norm(product_emb)
                        )
                        similarities.append((idx, similarity))
                
                # Sort by similarity and reorder results
                if similarities:
                    similarities.sort(key=lambda x: x[1], reverse=True)
                    sorted_indices = [idx for idx, _ in similarities]
                    # STRICT: Only include indices that are in our filtered results (before semantic search)
                    sorted_indices = [idx for idx in sorted_indices if idx in filtered_indices_before_semantic]
                    # Reorder results_df by similarity, but only include products that passed all filters
                    if sorted_indices:
                        results_df = results_df.loc[sorted_indices]
                    else:
                        # If no products match after filtering, keep filtered results as-is
                        print(f"   ⚠️  Semantic search returned no products matching strict filters, using filtered results as-is")
                # If no similarities found, keep the filtered results as-is (they're already filtered correctly)
    else:
        print("   🚫 Semantic ranking disabled for ablation study.")
        # When semantic ranking is disabled, sort results by index to ensure consistent ordering
        # This prevents returning results in arbitrary DataFrame order
        if not results_df.empty:
            results_df = results_df.sort_index()
            print(f"   📊 Results sorted by index (semantic disabled): {len(results_df)} products")
    
    # If results are empty BUT filters were applied, reapply filters and use semantic search on filtered set
    if use_semantic and embeddings_dict and enricher and results_df.empty and any(filters_applied.values()):
        # Rebuild the filtered set (respecting all filters)
        filtered_df = products_df.copy()
        
        # Reapply gender filter FIRST if it was applied
        if gender_filter and gender_filter != 'all':
            if 'gender' in filtered_df.columns:
                gender_mask = filtered_df['gender'].astype(str).str.lower() == gender_filter.lower()
                filtered_df = filtered_df[gender_mask]
                print(f"   👤 Reapplied gender filter ({gender_filter}): {len(filtered_df)} products")
            elif 'category' in filtered_df.columns:
                if gender_filter.lower() == 'men':
                    gender_mask = filtered_df['category'].astype(str).str.lower().str.contains("men", na=False)
                elif gender_filter.lower() == 'women':
                    gender_mask = filtered_df['category'].astype(str).str.lower().str.contains("women", na=False)
                else:
                    gender_mask = pd.Series([True] * len(filtered_df), index=filtered_df.index)
                filtered_df = filtered_df[gender_mask]
                print(f"   👤 Reapplied gender filter ({gender_filter}) from category: {len(filtered_df)} products")
        
        # Reapply product type filter if it was applied
        if filters_applied['product_type']:
            type_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            for product_type in detected_product_types:
                type_info = product_types[product_type]
                # Get all keywords including related types
                all_keywords = type_info['keywords'].copy()
                for related_type in type_info['related']:
                    if related_type in product_types:
                        all_keywords.extend(product_types[related_type]['keywords'])
                
                name_match = filtered_df['name'].astype(str).str.lower().str.contains(
                    '|'.join(all_keywords), na=False, regex=True
                )
                category_match = filtered_df['category'].astype(str).str.lower().str.contains(
                    product_type, na=False
                )
                type_mask |= (name_match | category_match)
            filtered_df = filtered_df[type_mask]
        
        # Reapply category filter if it was applied
        if filters_applied['category']:
            category_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            for category_keyword in detected_categories:
                category_mask |= filtered_df['category'].astype(str).str.lower().str.contains(
                    category_keyword, na=False
                )
            filtered_df = filtered_df[category_mask]
        
        # Reapply accessories filter if it was applied
        if filters_applied.get('accessories'):
            # Filter by accessory keywords in name (must match at least one)
            accessory_name_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            accessory_keywords = ['scarf', 'glove', 'sock', 'hat', 'cap', 'beanie', 'balaclava', 'vest', 'belt', 'tie', 'ring']
            for keyword in accessory_keywords:
                accessory_name_mask |= filtered_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
            
            # Also check category if available
            if 'category' in filtered_df.columns:
                category_mask = filtered_df['category'].astype(str).str.lower().str.contains('accessories', na=False, regex=False)
                filtered_df = filtered_df[accessory_name_mask | category_mask]
            else:
                filtered_df = filtered_df[accessory_name_mask]
            
            # Explicitly exclude non-accessories
            exclude_keywords = ['dress', 'skirt', 'sweater', 'cardigan', 'jumper', 'hoodie', 'shirt', 'blouse', 'polo', 'top', 'pants', 'trousers', 'jeans', 'shorts', 'jacket', 'coat', 'overshirt']
            exclude_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            for keyword in exclude_keywords:
                exclude_mask |= filtered_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
            filtered_df = filtered_df[~exclude_mask]
            print(f"   🎯 Reapplied accessories filter: {len(filtered_df)} products")
        
        # Reapply bottoms filter if it was applied
        if filters_applied.get('bottoms'):
            # Filter to only bottoms category
            if 'category' in filtered_df.columns:
                category_mask = filtered_df['category'].astype(str).str.lower().str.contains('bottoms', na=False, regex=False)
                filtered_df = filtered_df[category_mask]
            # Also filter by bottom keywords in name
            bottom_name_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            bottom_keywords = ['pants', 'trousers', 'jeans', 'chinos', 'shorts', 'leggings']
            for keyword in bottom_keywords:
                bottom_name_mask |= filtered_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
            filtered_df = filtered_df[bottom_name_mask]
            # Exclude tops explicitly
            top_exclude_mask = ~filtered_df['name'].astype(str).str.lower().str.contains('top|shirt|blouse|dress', na=False, regex=True)
            filtered_df = filtered_df[top_exclude_mask]
            print(f"   🎯 Reapplied bottoms filter: {len(filtered_df)} products")
        
        # Reapply tops filter if it was applied
        if filters_applied.get('tops'):
            # Filter to only tops category
            if 'category' in filtered_df.columns:
                category_mask = filtered_df['category'].astype(str).str.lower().str.contains('tops', na=False, regex=False)
                filtered_df = filtered_df[category_mask]
            # Also filter by top keywords in name
            top_name_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            top_keywords = ['top', 'shirt', 'blouse', 't-shirt', 'polo', 'henley', 'tee']
            for keyword in top_keywords:
                top_name_mask |= filtered_df['name'].astype(str).str.lower().str.contains(keyword, na=False)
            filtered_df = filtered_df[top_name_mask]
            # Exclude bottoms explicitly
            bottom_exclude_mask = ~filtered_df['name'].astype(str).str.lower().str.contains('pants|trousers|jeans|chinos|shorts', na=False, regex=True)
            filtered_df = filtered_df[bottom_exclude_mask]
            print(f"   🎯 Reapplied tops filter: {len(filtered_df)} products")
        
        # Reapply color filter if it was applied (use strict filtering if single color)
        if filters_applied['color']:
            if len(color_filters) == 1:
                # Strict: only primary color matches
                color = color_filters[0]
                def is_primary_color(colors_str, target_color):
                    if pd.isna(colors_str) or not colors_str:
                        return False
                    colors_list = [c.strip().lower() for c in str(colors_str).split(',')]
                    if len(colors_list) == 0:
                        return False
                    first_color = colors_list[0].strip()
                    return first_color == target_color.lower() or (len(colors_list) == 1 and first_color == target_color.lower())
                primary_color_mask = filtered_df['colors'].apply(lambda x: is_primary_color(x, color))
                filtered_df = filtered_df[primary_color_mask]
            else:
                # Multiple colors: match any
                color_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
                for color in color_filters:
                    color_mask |= filtered_df['colors'].astype(str).str.lower().str.contains(color, na=False)
                filtered_df = filtered_df[color_mask]
        
        # Reapply material filter if it was applied
        if filters_applied['material']:
            for material in materials:
                if material in query_lower:
                    filtered_df = filtered_df[
                        filtered_df['materials'].astype(str).str.lower().str.contains(material, na=False)
                    ]
                    break
        
        # Reapply style filter if it was applied (only in strict mode)
        if filters_applied['style']:
            style_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            for style in style_filters:
                style_mask |= filtered_df['style_keywords'].astype(str).str.lower().str.contains(style, na=False)
            filtered_df = filtered_df[style_mask]
        
        # Reapply price filter if it was applied
        if filters_applied['price']:
            import re
            max_price = None
            
            # Try $200 format first
            price_matches = re.findall(r'\$(\d+)', query_text)
            if price_matches:
                max_price = int(price_matches[0])
            else:
                # Try "200 dollars" or "200 dollar" format
                price_matches = re.findall(r'(\d+)\s*dollars?', query_lower)
                if price_matches:
                    max_price = int(price_matches[0])
                else:
                    # Try "under 200" or "below 200" format
                    price_matches = re.findall(r'(?:under|below|less than|max|maximum)\s+(\d+)', query_lower)
                    if price_matches:
                        max_price = int(price_matches[0])
            
            if max_price is not None:
                filtered_df = filtered_df[filtered_df['price'].astype(int) <= max_price]
        
        # Reapply exclusions if they were applied
        if filters_applied['exclusions']:
            for feature in normalized_excluded:
                if feature == 'pattern':
                    pattern_mask = (
                        filtered_df['patterns'].isna() | 
                        (filtered_df['patterns'].astype(str).str.lower() == 'nan') |
                        (filtered_df['patterns'].astype(str).str.strip() == '') |
                        (filtered_df['patterns'].astype(str).str.lower() == 'none')
                    )
                    filtered_df = filtered_df[pattern_mask]
                elif feature in ['button', 'hood', 'zipper', 'pocket', 'collar', 'sleeve', 'cuff']:
                    feature_keywords = {
                        'button': ['button', 'buttons', 'buttoned', 'button-up', 'button down'],
                        'hood': ['hood', 'hooded', 'hoodie'],
                        'zipper': ['zipper', 'zip', 'zipped', 'zip-up', 'zip up'],
                        'pocket': ['pocket', 'pockets'],
                        'collar': ['collar', 'collared'],
                        'sleeve': ['sleeve', 'sleeved'],
                        'cuff': ['cuff', 'cuffs', 'cuffed'],
                    }
                    if feature in feature_keywords:
                        keywords = feature_keywords[feature]
                        name_desc = (
                            filtered_df['name'].astype(str).str.lower() + ' ' + 
                            filtered_df['description'].astype(str).str.lower()
                        )
                        exclude_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
                        for keyword in keywords:
                            exclude_mask |= name_desc.str.contains(keyword, na=False, regex=False)
                        filtered_df = filtered_df[~exclude_mask]
        
        # Now do semantic search ONLY on the filtered set (respecting all filters)
        if not filtered_df.empty:
            query_emb = enricher.get_text_embedding(query_text)
            if query_emb is not None:
                similarities = []
                for idx in filtered_df.index:
                    row = filtered_df.loc[idx]
                    product_id = f"{row.get('name', idx)}_{idx}"
                    emb_key = f"{product_id}_text"
                    
                    if emb_key in embeddings_dict:
                        product_emb = np.array(embeddings_dict[emb_key])
                        similarity = np.dot(query_emb, product_emb) / (
                            np.linalg.norm(query_emb) * np.linalg.norm(product_emb)
                        )
                        similarities.append((idx, similarity))
                
                if similarities:
                    similarities.sort(key=lambda x: x[1], reverse=True)
                    semantic_indices = [idx for idx, _ in similarities[:top_k]]
                    results_df = filtered_df.loc[semantic_indices]
                else:
                    # No embeddings found, just use filtered results
                    results_df = filtered_df.head(top_k)
            else:
                # Couldn't encode query, just use filtered results
                results_df = filtered_df.head(top_k)
        else:
            # Filtered set is empty, return empty results (don't fall back to all products)
            # In strict mode, this is expected - return empty
            results_df = filtered_df
    
    # If results are empty but query implies product search, try semantic search
    # (We already checked that query implies product search above)
    if results_df.empty and embeddings_dict and enricher:
        # If filters were applied but resulted in empty, rebuild filtered set and do semantic search
        if any(filters_applied.values()):
            # Rebuild filtered set (same logic as before)
            filtered_df = products_df.copy()
            
            # Reapply gender filter FIRST if it was applied
            if gender_filter and gender_filter != 'all':
                if 'gender' in filtered_df.columns:
                    gender_mask = filtered_df['gender'].astype(str).str.lower() == gender_filter.lower()
                    filtered_df = filtered_df[gender_mask]
                    print(f"   👤 Reapplied gender filter ({gender_filter}): {len(filtered_df)} products")
                elif 'category' in filtered_df.columns:
                    if gender_filter.lower() == 'men':
                        gender_mask = filtered_df['category'].astype(str).str.lower().str.contains("men", na=False)
                    elif gender_filter.lower() == 'women':
                        gender_mask = filtered_df['category'].astype(str).str.lower().str.contains("women", na=False)
                    else:
                        gender_mask = pd.Series([True] * len(filtered_df), index=filtered_df.index)
                    filtered_df = filtered_df[gender_mask]
                    print(f"   👤 Reapplied gender filter ({gender_filter}) from category: {len(filtered_df)} products")
            
            # Reapply all filters
            if filters_applied['product_type']:
                type_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
                for product_type in detected_product_types:
                    name_match = filtered_df['name'].astype(str).str.lower().str.contains(
                        '|'.join(product_types[product_type]), na=False, regex=True
                    )
                    category_match = filtered_df['category'].astype(str).str.lower().str.contains(
                        product_type, na=False
                    )
                    type_mask |= (name_match | category_match)
                filtered_df = filtered_df[type_mask]
            
            if filters_applied['color']:
                color_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
                for color in color_filters:
                    color_mask |= filtered_df['colors'].astype(str).str.lower().str.contains(color, na=False)
                filtered_df = filtered_df[color_mask]
            
            if filters_applied['material']:
                for material in materials:
                    if material in query_lower:
                        filtered_df = filtered_df[
                            filtered_df['materials'].astype(str).str.lower().str.contains(material, na=False)
                        ]
                        break
            
            if filters_applied['price']:
                import re
                max_price = None
                price_matches = re.findall(r'\$(\d+)', query_text)
                if price_matches:
                    max_price = int(price_matches[0])
                else:
                    price_matches = re.findall(r'(\d+)\s*dollars?', query_lower)
                    if price_matches:
                        max_price = int(price_matches[0])
                    else:
                        price_matches = re.findall(r'(?:under|below|less than|max|maximum)\s+(\d+)', query_lower)
                        if price_matches:
                            max_price = int(price_matches[0])
                if max_price is not None:
                    filtered_df = filtered_df[filtered_df['price'].astype(int) <= max_price]
            
            # Do semantic search on filtered set
            if not filtered_df.empty:
                query_emb = enricher.get_text_embedding(query_text)
                if query_emb is not None:
                    similarities = []
                    for idx in filtered_df.index:
                        row = filtered_df.loc[idx]
                        product_id = f"{row.get('name', idx)}_{idx}"
                        emb_key = f"{product_id}_text"
                        
                        if emb_key in embeddings_dict:
                            product_emb = np.array(embeddings_dict[emb_key])
                            similarity = np.dot(query_emb, product_emb) / (
                                np.linalg.norm(query_emb) * np.linalg.norm(product_emb)
                            )
                            similarities.append((idx, similarity))
                    
                    if similarities:
                        similarities.sort(key=lambda x: x[1], reverse=True)
                        semantic_indices = [idx for idx, _ in similarities[:top_k]]
                        results_df = filtered_df.loc[semantic_indices]
        else:
            # No filters applied, do semantic search on all products
            query_emb = enricher.get_text_embedding(query_text)
            if query_emb is not None:
                similarities = []
                for idx, row in products_df.iterrows():
                    product_id = f"{row.get('name', idx)}_{idx}"
                    emb_key = f"{product_id}_text"
                    
                    if emb_key in embeddings_dict:
                        product_emb = np.array(embeddings_dict[emb_key])
                        similarity = np.dot(query_emb, product_emb) / (
                            np.linalg.norm(query_emb) * np.linalg.norm(product_emb)
                        )
                        similarities.append((idx, similarity))
                
                if similarities:
                    similarities.sort(key=lambda x: x[1], reverse=True)
                    semantic_indices = [idx for idx, _ in similarities[:top_k]]
                    results_df = products_df.loc[semantic_indices]
    
    # Limit results
    before_limit = len(results_df)
    results_df = results_df.head(top_k)
    if before_limit > top_k:
        print(f"   ✂️  Limited results from {before_limit} to {len(results_df)} (top_k={top_k})")
    
    # Final verification: if color filter was applied, verify all results match
    if color_filters and len(color_filters) == 1:
        color = color_filters[0]
        def verify_primary_color(colors_str, target_color):
            if pd.isna(colors_str) or not colors_str:
                return False
            colors_list = [c.strip().lower() for c in str(colors_str).split(',')]
            if len(colors_list) == 0:
                return False
            first_color = colors_list[0].strip()
            return first_color == target_color.lower() or (len(colors_list) == 1 and first_color == target_color.lower())
        
        mismatches = []
        for idx, row in results_df.iterrows():
            colors_str = str(row.get('colors', ''))
            if not verify_primary_color(colors_str, color):
                mismatches.append(f"{row.get('name', 'N/A')}: {colors_str}")
        if mismatches:
            print(f"   ⚠️  WARNING: Found {len(mismatches)} products that don't match strict color filter:")
            for mismatch in mismatches[:5]:
                print(f"      - {mismatch}")
        else:
            print(f"   ✅ Verification passed: All {len(results_df)} results have '{color}' as primary color")
    
    # If we have tagged products and this is a "pair well" query, exclude tagged products from results
    if tagged_products and any(pattern in query_lower for pattern in ['pair well', 'pair with', 'wear with', 'goes with']):
        tagged_indices = {p.get('index') for p in tagged_products if p.get('index') is not None}
        if tagged_indices:
            initial_count = len(results_df)
            results_df = results_df[~results_df.index.isin(tagged_indices)]
            print(f"   Excluded {len(tagged_indices)} tagged product(s) from 'pair well' results: {initial_count} -> {len(results_df)}")
    
    # Remove duplicates by index before converting to dict
    results_df = results_df[~results_df.index.duplicated(keep='first')]
    
    # Replace NaN with None for JSON serialization and convert to dict
    results_dict = []
    seen_indices = set()
    for idx, row in results_df.iterrows():
        # Skip if we've already seen this index (extra safety check)
        if idx in seen_indices:
            continue
        seen_indices.add(idx)
        
        product_dict = row.replace({np.nan: None}).to_dict()
        product_dict['index'] = int(idx)
        results_dict.append(product_dict)
    
    # Final safety check: remove any tagged products from results_dict
    if tagged_products:
        tagged_indices = {p.get('index') for p in tagged_products if p.get('index') is not None}
        if tagged_indices:
            results_dict = [r for r in results_dict if r.get('index') not in tagged_indices]
    
    return jsonify({
        'query': query_text,
        'results': results_dict,
        'count': len(results_dict)
    })

@app.route('/api/color-matches', methods=['GET'])
def get_color_matches():
    """Get color matching suggestions for a product."""
    product_id = request.args.get('product_id')
    product_name = request.args.get('name')
    
    if not product_id and not product_name:
        return jsonify({'error': 'product_id or name required'}), 400
    
    # Find product
    if product_id:
        product_series = products_df.iloc[int(product_id)]
    else:
        product_series = products_df[products_df['name'] == product_name].iloc[0]
    
    # Replace NaN with None for JSON serialization
    product = product_series.where(pd.notna(product_series), None).to_dict()
    
    colors = product.get('colors', '')
    if not colors:
        return jsonify({
            'complementary': [],
            'neutral': [],
            'monochrome': []
        })
    
    color_list = [c.strip() for c in str(colors).split(',') if c.strip()]
    color_matches = enricher.get_color_matches(color_list)
    
    return jsonify(color_matches)

if __name__ == '__main__':
    print("🚀 Starting Shopping Assistant API...")
    load_data()
    
    # Use port 5001 by default (5000 is often used by macOS AirPlay)
    port = int(os.getenv('PORT', 5001))
    print(f"📡 Server will run on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)

