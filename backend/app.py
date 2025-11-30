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

# Import enrichment utilities
import sys
sys.path.append(str(Path(__file__).parent.parent))
from utils.enrich import StyleEnricher, load_embeddings

app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome extension

# Global variables for loaded data
products_df = None
embeddings_dict = None
enricher = None

def load_data():
    """Load enriched data and embeddings."""
    global products_df, embeddings_dict, enricher
    
    data_dir = Path(__file__).parent.parent / "data" / "processed"
    
    # Load products - try enriched first, then fallback to cos_all_products
    csv_file = data_dir / "enriched_cos_mens_knitwear.csv"
    if not csv_file.exists():
        csv_file = data_dir / "cos_all_products.csv"
    
    if csv_file.exists():
        products_df = pd.read_csv(csv_file)
        print(f"✅ Loaded {len(products_df)} products from {csv_file.name}")
    else:
        print(f"⚠️  No product data found. Tried:")
        print(f"   - {data_dir / 'enriched_cos_mens_knitwear.csv'}")
        print(f"   - {data_dir / 'cos_all_products.csv'}")
        products_df = pd.DataFrame()
    
    # Load embeddings
    embeddings_file = data_dir / "embeddings.pkl"
    if embeddings_file.exists():
        embeddings_dict = load_embeddings(embeddings_file)
        print(f"✅ Loaded {len(embeddings_dict)} embeddings")
    else:
        print(f"⚠️  No embeddings found at {embeddings_file}")
        embeddings_dict = {}
    
    # Initialize enricher (for query encoding)
    enricher = StyleEnricher(use_clip=False)  # Don't need CLIP for query encoding
    print("✅ Enricher initialized")

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
        "top_k": 10
    }
    """
    if products_df is None or products_df.empty:
        return jsonify({'error': 'No products loaded'}), 404
    
    data = request.get_json()
    query_text = data.get('query', '')
    top_k = data.get('top_k', 10)
    
    if not query_text:
        return jsonify({'error': 'Query text required'}), 400
    
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
                         'hoodie', 'cardigan', 'jumper']
    
    product_attribute_words = ['black', 'white', 'navy', 'beige', 'brown', 'grey', 'gray',
                              'wool', 'cotton', 'cashmere', 'merino', 'silk', 'mohair',
                              'minimalist', 'classic', 'modern', 'casual', 'formal', 'oversized',
                              'fitted', 'relaxed', 'elegant']
    
    price_words = ['price', 'dollar', 'cost', 'under', 'over', 'below', 'above', 'cheap',
                  'expensive', 'affordable', '$']
    
    has_action_word = any(action in query_lower for action in product_action_words)
    has_product_type = any(ptype in query_lower for ptype in product_type_words)
    has_attribute = any(attr in query_lower for attr in product_attribute_words)
    has_price = any(price_word in query_lower for price_word in price_words)
    
    # Query implies product search if it has product-related content
    # Allow queries with just attributes (e.g., "black wool") as they're clearly product searches
    implies_product_search = (
        has_product_type or  # Has a product type
        (has_action_word and (has_attribute or has_price)) or  # Action + attribute/price
        (has_attribute and has_price) or  # Attribute + price
        has_attribute or  # Just attributes (e.g., "black wool", "minimalist classic")
        (len([x for x in [has_action_word, has_product_type, has_attribute, has_price] if x]) >= 2)
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
    
    # Detect "only" keyword - this enforces strict filtering
    strict_mode = 'only' in query_lower or 'just' in query_lower
    
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
            'keywords': ['shirt', 'shirts', 'blouse', 'blouses'],
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
    }
    
    detected_product_types = []
    for product_type, type_info in product_types.items():
        for keyword in type_info['keywords']:
            if keyword in query_lower:
                detected_product_types.append(product_type)
                break
    
    # Apply product type filter (including related types)
    if detected_product_types:
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
    
    # Also check for category names in query (e.g., "knitwear", "accessories")
    # Common category names
    category_keywords = ['knitwear', 'accessories', 'outerwear', 'bottoms', 'tops', 
                        'footwear', 'bags', 'jewelry', 'underwear']
    detected_categories = []
    for category_keyword in category_keywords:
        if category_keyword in query_lower:
            detected_categories.append(category_keyword)
    
    # Filter by category if detected
    if detected_categories:
        category_mask = pd.Series([False] * len(results_df), index=results_df.index)
        for category_keyword in detected_categories:
            category_mask |= results_df['category'].astype(str).str.lower().str.contains(
                category_keyword, na=False
            )
        results_df = results_df[category_mask]
    
    # Filter by material (apply before color to avoid empty sets)
    materials = ['wool', 'cotton', 'cashmere', 'merino', 'silk', 'mohair', 'alpaca']
    material_filters = []
    for material in materials:
        if material in query_lower:
            material_filters.append(material)
            break  # Only take first material found
    
    if material_filters:
        material = material_filters[0]
        # Check if 'materials' column exists, otherwise search in description and name
        if 'materials' in results_df.columns:
            results_df = results_df[
                results_df['materials'].astype(str).str.lower().str.contains(material, na=False)
            ]
        else:
            # Fallback: search in description and name
            material_mask = pd.Series([False] * len(results_df), index=results_df.index)
            if 'description' in results_df.columns:
                material_mask |= results_df['description'].astype(str).str.lower().str.contains(material, na=False)
            if 'name' in results_df.columns:
                material_mask |= results_df['name'].astype(str).str.lower().str.contains(material, na=False)
            results_df = results_df[material_mask]
    
    # Filter by color - check ALL colors in query
    colors = ['black', 'white', 'navy', 'beige', 'brown', 'grey', 'gray', 'red', 'blue', 
              'green', 'yellow', 'pink', 'purple', 'orange', 'tan', 'camel', 'cream', 
              'ivory', 'charcoal', 'olive']
    color_filters = []
    for color in colors:
        if color in query_lower:
            color_filters.append(color)
    
    # Apply color filters (must match at least one)
    if color_filters:
        color_mask = pd.Series([False] * len(results_df), index=results_df.index)
        for color in color_filters:
            # Check if 'colors' column exists, otherwise search in description and name
            if 'colors' in results_df.columns:
                color_mask |= results_df['colors'].astype(str).str.lower().str.contains(color, na=False)
            else:
                # Fallback: search in description and name
                desc_col = 'description' if 'description' in results_df.columns else ''
                name_col = 'name' if 'name' in results_df.columns else ''
                if desc_col:
                    color_mask |= results_df[desc_col].astype(str).str.lower().str.contains(color, na=False)
                if name_col:
                    color_mask |= results_df[name_col].astype(str).str.lower().str.contains(color, na=False)
        results_df = results_df[color_mask]
    
    # Filter by price (apply last, as it's often optional)
    if 'under' in query_lower or '$' in query_lower or 'dollar' in query_lower:
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
    
    # Filter by style - check ALL styles in query
    styles = ['minimalist', 'classic', 'modern', 'casual', 'formal', 'oversized', 'fitted', 
              'relaxed', 'elegant', 'sophisticated', 'versatile']
    style_filters = []
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
                # Check if 'style_keywords' column exists, otherwise search in description and name
                if 'style_keywords' in results_df.columns:
                    style_mask |= results_df['style_keywords'].astype(str).str.lower().str.contains(style, na=False)
                else:
                    # Fallback: search in description and name
                    desc_col = 'description' if 'description' in results_df.columns else ''
                    name_col = 'name' if 'name' in results_df.columns else ''
                    if desc_col:
                        style_mask |= results_df[desc_col].astype(str).str.lower().str.contains(style, na=False)
                    if name_col:
                        style_mask |= results_df[name_col].astype(str).str.lower().str.contains(style, na=False)
            results_df = results_df[style_mask]
        # In non-strict mode, style filters are used for semantic ranking later
    
    # Handle negative filters (exclusions) - generalized approach
    # Detect "no X", "without X", "no Xs" patterns
    import re
    
    # Common product types to ignore when extracting exclusions
    product_types = ['sweater', 'sweaters', 'cardigan', 'cardigans', 'hoodie', 'hoodies',
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
                        if m and m.lower() not in product_types:
                            excluded_features.append(m)
                else:
                    if match and match.lower() not in product_types:
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
    if 'sleeveless' in query_lower:
        name_desc = (
            results_df['name'].astype(str).str.lower() + ' ' + 
            results_df['description'].astype(str).str.lower()
        )
        # Keep only items that mention "sleeveless"
        results_df = results_df[name_desc.str.contains('sleeveless', na=False, regex=False)]
    
    # "solid" can mean no pattern
    if 'solid' in query_lower and 'pattern' not in normalized_excluded:
        # "solid" means no pattern
        pattern_mask = (
            results_df['patterns'].isna() | 
            (results_df['patterns'].astype(str).str.lower() == 'nan') |
            (results_df['patterns'].astype(str).str.strip() == '') |
            (results_df['patterns'].astype(str).str.lower().str.contains('solid', na=False))
        )
        results_df = results_df[pattern_mask]
    
    # Track which filters were applied (so we don't lose them)
    filters_applied = {
        'product_type': len(detected_product_types) > 0,
        'category': len(detected_categories) > 0,
        'color': len(color_filters) > 0,
        'material': any(material in query_lower for material in materials),
        'style': len(style_filters) > 0 and strict_mode,  # Style only enforced in strict mode
        'price': 'under' in query_lower or '$' in query_lower or 'dollar' in query_lower or 'below' in query_lower,
        'exclusions': len(normalized_excluded) > 0,
        'strict': strict_mode
    }
    
    # If we have embeddings and filtered results, do semantic search ONLY on filtered results
    if embeddings_dict and enricher and not results_df.empty:
        query_emb = enricher.get_text_embedding(query_text)
        if query_emb is not None:
            # Compute semantic similarities ONLY for filtered products
            similarities = []
            for idx in results_df.index:
                row = results_df.loc[idx]
                product_id = f"{row.get('name', idx)}_{idx}"
                emb_key = f"{product_id}_text"
                
                if emb_key in embeddings_dict:
                    product_emb = np.array(embeddings_dict[emb_key])
                    similarity = np.dot(query_emb, product_emb) / (
                        np.linalg.norm(query_emb) * np.linalg.norm(product_emb)
                    )
                    similarities.append((idx, similarity))
            
            # Sort by similarity and reorder results
            if similarities:
                similarities.sort(key=lambda x: x[1], reverse=True)
                sorted_indices = [idx for idx, _ in similarities]
                # Reorder results_df by similarity
                results_df = results_df.loc[sorted_indices]
            # If no similarities found, keep the filtered results as-is (they're already filtered correctly)
    
    # If results are empty BUT filters were applied, reapply filters and use semantic search on filtered set
    elif embeddings_dict and enricher and results_df.empty and any(filters_applied.values()):
        # Rebuild the filtered set (respecting all filters)
        filtered_df = products_df.copy()
        
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
        
        # Reapply color filter if it was applied
        if filters_applied['color']:
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
    results_df = results_df.head(top_k)
    
    # Replace NaN with None for JSON serialization
    results_dict = results_df.replace({np.nan: None}).to_dict('records')
    
    return jsonify({
        'query': query_text,
        'results': results_dict,
        'count': len(results_df)
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

