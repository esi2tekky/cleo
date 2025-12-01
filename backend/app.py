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
import base64
from io import BytesIO
from PIL import Image

# Import enrichment utilities
import sys
sys.path.append(str(Path(__file__).parent.parent))
from utils.enrich import StyleEnricher, load_embeddings

# Try to load from .env.local or .env file if it exists
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent
    env_local_path = project_root / '.env.local'
    env_path = project_root / '.env'
    
    if env_local_path.exists():
        load_dotenv(env_local_path)
    elif env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, skip

# Import new modules
from backend.openai_client import OpenAIEmbedder
from backend.conversation import ConversationManager
from backend.query_parser import QueryParser
from backend.style_embeddings import get_style_embedding_query, extract_style_context

app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome extension

# Global variables for loaded data
products_df = None
embeddings_dict = None
enricher = None
openai_embedder = None
conversation_manager = ConversationManager()
fashion_clip_enricher = None
query_parser = QueryParser()
pinecone_index = None

def load_data():
    """Load enriched data and embeddings."""
    global products_df, embeddings_dict, enricher, openai_embedder, fashion_clip_enricher, pinecone_index
    
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
    
    # Initialize OpenAI embedder
    if os.getenv("OPENAI_API_KEY"):
        try:
            openai_embedder = OpenAIEmbedder(model="text-embedding-3-small")
            print("✅ OpenAI embedder initialized")
        except Exception as e:
            print(f"⚠️  OpenAI not available: {e}")
            openai_embedder = None
    else:
        print("⚠️  OPENAI_API_KEY not set, using sentence-transformers")
        openai_embedder = None
    
    # Initialize Fashion CLIP for visual embeddings
    try:
        fashion_clip_enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)
        print("✅ Fashion CLIP initialized for visual embeddings")
    except Exception as e:
        print(f"⚠️  Fashion CLIP not available: {e}")
        fashion_clip_enricher = None
    
    # Initialize Pinecone (optional)
    if os.getenv("PINECONE_API_KEY"):
        try:
            from pinecone import Pinecone, ServerlessSpec
            
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            index_name = os.getenv("PINECONE_INDEX_NAME", "cos-products")
            
            # Check if index exists, create if not
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            if index_name not in existing_indexes:
                print(f"Creating Pinecone index: {index_name}")
                pc.create_index(
                    name=index_name,
                    dimension=1536,  # OpenAI text-embedding-3-small dimension
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
                    )
                )
            
            pinecone_index = pc.Index(index_name)
            print(f"✅ Pinecone index '{index_name}' connected")
            embeddings_dict = {}  # Don't load local embeddings if using Pinecone
        except Exception as e:
            print(f"⚠️  Pinecone not available: {e}")
            pinecone_index = None
    else:
        print("⚠️  PINECONE_API_KEY not set, using local embeddings")
        pinecone_index = None
    
    # Load local embeddings (if not using Pinecone)
    if pinecone_index is None:
        embeddings_file = data_dir / "embeddings_openai.pkl"
        if not embeddings_file.exists():
            embeddings_file = data_dir / "embeddings.pkl"
        
        if embeddings_file.exists():
            embeddings_dict = load_embeddings(embeddings_file)
            print(f"✅ Loaded {len(embeddings_dict)} embeddings from {embeddings_file.name}")
        else:
            print(f"⚠️  No embeddings found at {embeddings_file}")
            embeddings_dict = {}
    
    # Initialize enricher (fallback for query encoding if OpenAI unavailable)
    enricher = StyleEnricher(use_clip=False)  # Don't need CLIP for text
    print("✅ Text enricher initialized (fallback)")

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'products_loaded': len(products_df) if products_df is not None else 0,
        'embeddings_loaded': len(embeddings_dict) if embeddings_dict else 0,
        'openai_available': openai_embedder is not None,
        'fashion_clip_available': fashion_clip_enricher is not None,
        'pinecone_available': pinecone_index is not None,
        'conversation_sessions': len(conversation_manager.conversations)
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

def handle_variants_query(referenced_product: Dict, query_text: str, top_k: int = 10) -> pd.DataFrame:
    """
    Handle variants query - find products with same base but different attributes.
    
    Args:
        referenced_product: The product being referenced
        query_text: User query text
        top_k: Number of results to return
        
    Returns:
        DataFrame with variant products
    """
    global products_df, openai_embedder, embeddings_dict, pinecone_index
    
    if products_df is None or products_df.empty:
        return pd.DataFrame()
    
    ref_idx = referenced_product.get('index')
    if ref_idx is None:
        print(f"⚠️  Variants query: Product index not found in reference")
        return pd.DataFrame()
    
    # Validate and convert index
    try:
        ref_idx = int(ref_idx)
    except (ValueError, TypeError) as e:
        print(f"⚠️  Variants query: Invalid product index '{ref_idx}': {e}")
        return pd.DataFrame()
    
    # Check bounds
    if ref_idx < 0 or ref_idx >= len(products_df):
        print(f"⚠️  Variants query: Product index {ref_idx} out of bounds (0-{len(products_df)-1})")
        return pd.DataFrame()
    
    try:
        ref_product = products_df.iloc[ref_idx]
    except (IndexError, KeyError) as e:
        print(f"⚠️  Variants query: Error accessing product at index {ref_idx}: {e}")
        return pd.DataFrame()
    
    # Extract variant criteria from query
    query_lower = query_text.lower()
    variant_type = None
    if 'color' in query_lower:
        variant_type = 'color'
    elif 'size' in query_lower:
        variant_type = 'size'
    elif 'material' in query_lower or 'fabric' in query_lower:
        variant_type = 'material'
    
    # Start with products in same category
    results_df = products_df[products_df['category'] == ref_product.get('category', '')].copy()
    
    # IMPORTANT: Maintain gender filter from referenced product
    # If the referenced product has gender, use it; otherwise check if it was passed in the product data
    ref_gender = ref_product.get('gender') if pd.notna(ref_product.get('gender')) else referenced_product.get('gender')
    if ref_gender:
        results_df = results_df[results_df['gender'] == ref_gender]
        print(f"✅ Maintained gender filter from referenced product: {ref_gender}")
    
    # Exclude the reference product
    results_df = results_df[results_df.index != ref_idx]
    
    # If looking for color variants, try to find products with similar name base
    if variant_type == 'color':
        # Extract base name (remove color words)
        ref_name = str(ref_product.get('name', '')).lower()
        # Try to find products with similar names but different colors
        # Use semantic search to find similar products
        if openai_embedder:
            ref_desc = str(ref_product.get('description', '') or ref_product.get('name', ''))
            ref_emb = openai_embedder.get_embedding(ref_desc)
            
            if ref_emb is not None and not results_df.empty:
                # Find similar products using embeddings
                similarities = []
                for idx, row in results_df.iterrows():
                    product_desc = str(row.get('description', '') or row.get('name', ''))
                    if product_desc:
                        product_emb = openai_embedder.get_embedding(product_desc)
                        if product_emb is not None:
                            similarity = np.dot(ref_emb, product_emb) / (
                                np.linalg.norm(ref_emb) * np.linalg.norm(product_emb)
                            )
                            similarities.append((idx, similarity))
                
                if similarities:
                    similarities.sort(key=lambda x: x[1], reverse=True)
                    sorted_indices = [idx for idx, _ in similarities[:top_k]]
                    results_df = products_df.loc[sorted_indices]
    
    return results_df.head(top_k)


def handle_similar_products_query(referenced_product: Dict, query_text: str, top_k: int = 10) -> pd.DataFrame:
    """
    Handle similar products query - find products similar to referenced product.
    
    Args:
        referenced_product: The product being referenced
        query_text: User query text
        top_k: Number of results to return
        
    Returns:
        DataFrame with similar products
    """
    global products_df, openai_embedder, embeddings_dict, pinecone_index
    
    if products_df is None or products_df.empty:
        return pd.DataFrame()
    
    ref_idx = referenced_product.get('index')
    if ref_idx is None:
        print(f"⚠️  Similar products query: Product index not found in reference")
        return pd.DataFrame()
    
    # Validate and convert index
    try:
        ref_idx = int(ref_idx)
    except (ValueError, TypeError) as e:
        print(f"⚠️  Similar products query: Invalid product index '{ref_idx}': {e}")
        return pd.DataFrame()
    
    # Check bounds
    if ref_idx < 0 or ref_idx >= len(products_df):
        print(f"⚠️  Similar products query: Product index {ref_idx} out of bounds (0-{len(products_df)-1})")
        return pd.DataFrame()
    
    try:
        ref_product = products_df.iloc[ref_idx]
    except (IndexError, KeyError) as e:
        print(f"⚠️  Similar products query: Error accessing product at index {ref_idx}: {e}")
        return pd.DataFrame()
    
    # IMPORTANT: Get gender from referenced product to maintain context
    ref_gender = ref_product.get('gender') if pd.notna(ref_product.get('gender')) else referenced_product.get('gender')
    
    # Get reference product embedding
    ref_emb = None
    if openai_embedder:
        description = str(ref_product.get('description', '') or ref_product.get('name', ''))
        if description:
            ref_emb = openai_embedder.get_embedding(description)
    
    if ref_emb is None:
        # Fallback to stored embeddings
        ref_id = f"{ref_product.get('name', ref_idx)}_{ref_idx}"
        ref_emb_key = f"{ref_id}_text"
        if ref_emb_key in embeddings_dict:
            ref_emb = np.array(embeddings_dict[ref_emb_key])
    
    if ref_emb is None:
        return pd.DataFrame()
    
    # Extract product type from query if specified
    query_lower = query_text.lower()
    product_type_filter = None
    parsed = query_parser.parse_situational_query(query_text)
    if parsed.get('product_type'):
        product_type_filter = parsed['product_type']
    
    # Filter by product type if specified
    results_df = products_df.copy()
    if product_type_filter:
        type_mask = results_df['category'].astype(str).str.lower().str.contains(product_type_filter, na=False) | \
                   results_df['name'].astype(str).str.lower().str.contains(product_type_filter, na=False)
        results_df = results_df[type_mask]
    
    # IMPORTANT: Apply gender filter from referenced product
    if ref_gender:
        results_df = results_df[results_df['gender'] == ref_gender]
        print(f"✅ Maintained gender filter from referenced product: {ref_gender}")
    
    # Exclude reference product
    results_df = results_df[results_df.index != ref_idx]
    
    if results_df.empty:
        return pd.DataFrame()
    
    # Find similar products using semantic search
    if pinecone_index:
        try:
            filter_dict = {"product_id": {"$ne": int(ref_idx)}}
            if product_type_filter:
                # Could add category filter here if needed
                pass
            
            results = pinecone_index.query(
                vector=ref_emb.tolist(),
                top_k=top_k + 1,
                include_metadata=True,
                filter=filter_dict
            )
            
            similar_indices = []
            for match in results.matches:
                product_id = match.metadata.get('product_id')
                if product_id and product_id != ref_idx:
                    try:
                        if int(product_id) in results_df.index:
                            similar_indices.append(int(product_id))
                    except (ValueError, IndexError):
                        continue
            
            if similar_indices:
                return products_df.loc[similar_indices].head(top_k)
        except Exception as e:
            print(f"⚠️  Pinecone similar search error: {e}, falling back to local")
    
    # Fallback to local search
    similarities = []
    for idx, row in results_df.iterrows():
        product_id_str = f"{row.get('name', idx)}_{idx}"
        emb_key = f"{product_id_str}_text"
        
        if emb_key in embeddings_dict:
            product_emb = np.array(embeddings_dict[emb_key])
            similarity = np.dot(ref_emb, product_emb) / (
                np.linalg.norm(ref_emb) * np.linalg.norm(product_emb)
            )
            similarities.append((idx, similarity))
    
    if similarities:
        similarities.sort(key=lambda x: x[1], reverse=True)
        sorted_indices = [idx for idx, _ in similarities[:top_k]]
        return products_df.loc[sorted_indices].head(top_k)
    
    return pd.DataFrame()


@app.route('/api/query', methods=['POST'])
def handle_query():
    """
    Handle natural language queries about products.
    Combines semantic search with attribute filtering, conversation memory, and style embeddings.
    
    Request body:
    {
        "query": "show me wool sweaters under $200",
        "top_k": 10,
        "session_id": "session_123",
        "use_visual": false,
        "image_embedding": null
    }
    """
    global products_df, embeddings_dict, openai_embedder, enricher, conversation_manager
    global query_parser, pinecone_index
    
    if products_df is None or products_df.empty:
        return jsonify({'error': 'No products loaded'}), 404
    
    data = request.get_json()
    query_text = data.get('query', '')
    top_k = data.get('top_k', 10)
    session_id = data.get('session_id', 'default')
    use_visual = data.get('use_visual', False)
    image_embedding = data.get('image_embedding')
    tagged_products_data = data.get('tagged_products', [])
    ui_gender = data.get('gender', 'all')  # From UI toggle
    
    # Store tagged products in conversation manager
    if tagged_products_data:
        for product_data in tagged_products_data:
            conversation_manager.add_tagged_product(session_id, product_data)
    
    if not query_text and not image_embedding:
        return jsonify({'error': 'Query text or image required'}), 400
    
    # Get tagged products from conversation manager
    tagged_products = conversation_manager.get_tagged_products(session_id)
    
    # Check for product references in query
    product_reference = None
    if query_text:
        product_reference = query_parser.detect_product_reference(query_text, tagged_products)
    
    # Parse query for situational components (including gender)
    parsed_components = {}
    if query_text:
        parsed_components = query_parser.parse_situational_query(query_text)
    
    # Determine gender filter: prefer query text gender over UI toggle
    gender_filter = None
    if parsed_components.get('gender'):
        gender_filter = parsed_components['gender']  # Query text gender takes priority
    elif ui_gender and ui_gender != 'all':
        gender_filter = ui_gender  # Fallback to UI toggle
    
    # Apply gender filter EARLY, before semantic search
    results_df = products_df.copy()
    if gender_filter and 'gender' in results_df.columns:
        results_df = results_df[results_df['gender'] == gender_filter]
        print(f"✅ Applied gender filter: {gender_filter} ({len(results_df)} products)")
    
    # If product reference found, classify intent and handle accordingly
    if product_reference:
        referenced_product = product_reference['referenced_product']
        query_intent = query_parser.classify_product_query_intent(query_text, has_product_reference=True)
        
        if query_intent['intent'] == 'variants':
            # Handle variants query
            results_df = handle_variants_query(referenced_product, query_text, top_k)
            # Include index in results
            results_dict = []
            if not results_df.empty:
                for idx, row in results_df.iterrows():
                    product_dict = row.replace({np.nan: None}).to_dict()
                    product_dict['index'] = int(idx)  # Add index for frontend tagging
                    results_dict.append(product_dict)
            
            conversation_manager.add_message(session_id, "user", query_text)
            conversation_manager.add_message(
                session_id,
                "assistant",
                f"Found {len(results_dict)} variant products",
                metadata={"result_count": len(results_dict), "intent": "variants"}
            )
            
            return jsonify({
                'query': query_text,
                'results': results_dict,
                'count': len(results_dict),
                'session_id': session_id,
                'intent': 'variants',
                'referenced_product': referenced_product
            })
        
        elif query_intent['intent'] == 'similar':
            # Handle similar products query
            results_df = handle_similar_products_query(referenced_product, query_text, top_k)
            # Include index in results
            results_dict = []
            if not results_df.empty:
                for idx, row in results_df.iterrows():
                    product_dict = row.replace({np.nan: None}).to_dict()
                    product_dict['index'] = int(idx)  # Add index for frontend tagging
                    results_dict.append(product_dict)
            
            conversation_manager.add_message(session_id, "user", query_text)
            conversation_manager.add_message(
                session_id,
                "assistant",
                f"Found {len(results_dict)} similar products",
                metadata={"result_count": len(results_dict), "intent": "similar"}
            )
            
            return jsonify({
                'query': query_text,
                'results': results_dict,
                'count': len(results_dict),
                'session_id': session_id,
                'intent': 'similar',
                'referenced_product': referenced_product
            })
        
        elif query_intent['intent'] == 'compatibility':
            # Handle compatibility query
            ref_idx = referenced_product.get('index')
            if ref_idx is None:
                return jsonify({'error': 'Product index not found in reference'}), 400
            
            # Validate and convert index
            try:
                ref_idx = int(ref_idx)
            except (ValueError, TypeError) as e:
                return jsonify({'error': f'Invalid product index: {ref_idx}'}), 400
            
            # Check bounds
            if ref_idx < 0 or ref_idx >= len(products_df):
                return jsonify({'error': f'Product index {ref_idx} out of bounds'}), 404
            
            try:
                # Extract compatible product type from query
                parsed = query_parser.parse_situational_query(query_text)
                compatible_type = parsed.get('product_type')
                
                # Get reference product
                ref_product = products_df.iloc[ref_idx]
                
                # Get reference product embedding
                ref_emb = None
                if openai_embedder:
                    description = str(ref_product.get('description', '') or ref_product.get('name', ''))
                    if description:
                        ref_emb = openai_embedder.get_embedding(description)
                
                if ref_emb is None:
                    ref_id = f"{ref_product.get('name', ref_idx)}_{ref_idx}"
                    ref_emb_key = f"{ref_id}_text"
                    if ref_emb_key in embeddings_dict:
                        ref_emb = np.array(embeddings_dict[ref_emb_key])
                
                if ref_emb is None:
                    # Fall through to normal query
                    pass
                else:
                    # Find compatible products
                    compatible_products = []
                    
                    if pinecone_index:
                        try:
                            filter_dict = {"product_id": {"$ne": int(ref_idx)}}
                            results = pinecone_index.query(
                                vector=ref_emb.tolist(),
                                top_k=top_k + 1,
                                include_metadata=True,
                                filter=filter_dict
                            )
                            
                            for match in results.matches:
                                product_id = match.metadata.get('product_id')
                                if product_id and product_id != ref_idx:
                                    try:
                                        product_row = products_df.iloc[int(product_id)]
                                        # Filter by gender from referenced product
                                        ref_gender = ref_product.get('gender')
                                        if ref_gender and pd.notna(ref_gender):
                                            if product_row.get('gender') != ref_gender:
                                                continue
                                        # Filter by compatible product type if specified
                                        if compatible_type:
                                            category = str(product_row.get('category', '')).lower()
                                            name = str(product_row.get('name', '')).lower()
                                            if compatible_type not in category and compatible_type not in name:
                                                continue
                                        compatible_products.append(product_row.replace({np.nan: None}).to_dict())
                                    except (IndexError, KeyError):
                                        continue
                        except Exception as e:
                            print(f"⚠️  Pinecone compatibility search error: {e}, falling back to local")
                    
                    # Fallback to local search
                    if not compatible_products:
                        similarities = []
                        for idx, row in products_df.iterrows():
                            if idx == ref_idx:
                                continue
                            
                            # Filter by gender from referenced product
                            ref_gender = ref_product.get('gender')
                            if ref_gender and pd.notna(ref_gender):
                                if row.get('gender') != ref_gender:
                                    continue
                            
                            # Filter by compatible product type if specified
                            if compatible_type:
                                category = str(row.get('category', '')).lower()
                                name = str(row.get('name', '')).lower()
                                if compatible_type not in category and compatible_type not in name:
                                    continue
                            
                            product_id_str = f"{row.get('name', idx)}_{idx}"
                            emb_key = f"{product_id_str}_text"
                            
                            if emb_key in embeddings_dict:
                                product_emb = np.array(embeddings_dict[emb_key])
                                similarity = np.dot(ref_emb, product_emb) / (
                                    np.linalg.norm(ref_emb) * np.linalg.norm(product_emb)
                                )
                                similarities.append((idx, similarity, row))
                        
                        if similarities:
                            similarities.sort(key=lambda x: x[1], reverse=True)
                            compatible_products = [
                                row.replace({np.nan: None}).to_dict()
                                for _, _, row in similarities[:top_k]
                            ]
                    
                    conversation_manager.add_message(session_id, "user", query_text)
                    conversation_manager.add_message(
                        session_id,
                        "assistant",
                        f"Found {len(compatible_products)} compatible products",
                        metadata={"result_count": len(compatible_products), "intent": "compatibility"}
                    )
                    
                    return jsonify({
                        'query': query_text,
                        'results': compatible_products[:top_k],
                        'count': len(compatible_products[:top_k]),
                        'session_id': session_id,
                        'intent': 'compatibility',
                        'referenced_product': referenced_product
                    })
            except Exception as e:
                print(f"⚠️  Compatibility query error: {e}")
                import traceback
                traceback.print_exc()
                # Return proper error response instead of falling through
                return jsonify({
                    'error': f'Error processing compatibility query: {str(e)}',
                    'query': query_text,
                    'session_id': session_id
                }), 500
    
    # Get conversation context and user preferences
    context = conversation_manager.get_context(session_id, max_messages=5)
    recent_queries = conversation_manager.get_recent_queries(session_id, n=3)
    last_query_context = conversation_manager.get_last_query_context(session_id)
    user_preferences = conversation_manager.infer_preferences_from_history(session_id)
    
    # Detect if current query is a correction or refinement
    is_correction = False
    query_intent = 'new'
    if query_text and last_query_context:
        is_correction = conversation_manager.is_correction_query(query_text)
        if is_correction:
            query_intent = 'correction'
        else:
            # Check for other intents
            intent_result = query_parser.detect_query_intent(query_text, last_query_context)
            query_intent = intent_result.get('intent', 'new')
    
    # Merge contexts if it's a follow-up or correction
    if is_correction and last_query_context:
        # Use merge_query_context to combine contexts
        merged_context = query_parser.merge_query_context(query_text, last_query_context, query_intent)
        print(f"🔄 Merged context for correction: {merged_context}")
        # Use merged context for search
        query_text_for_search = merged_context.get('query_text', query_text)
        parsed_components_for_search = merged_context.get('parsed_components', {})
        gender_filter_for_search = merged_context.get('applied_filters', {}).get('gender', gender_filter)
    else:
        query_text_for_search = query_text
        parsed_components_for_search = parsed_components
        gender_filter_for_search = gender_filter
    
    # Check if this is a gender-only query
    query_lower_search = query_text_for_search.lower() if query_text_for_search else ""
    is_gender_only_query = query_lower_search in ['for men', 'for women', 'men', 'women', 'mens', 'womens']
    
    # Detect follow-up queries (only if we have query text)
    follow_up_words = ['that', 'this', 'it', 'more', 'similar', 'like', 'those', 'them', 'for men', 'for women', 'in men', 'in women']
    is_follow_up = query_text_for_search and any(word in query_text_for_search.lower() for word in follow_up_words) and context
    
    # Enhance query with context if follow-up or gender-only query
    if (is_follow_up or is_gender_only_query) and context and last_query_context:
        # For gender-only queries, reconstruct the query with context
        if is_gender_only_query:
            last_query_text = last_query_context.get('query_text', '')
            # Remove any gender from the last query and add the new gender
            enhanced_query = f"{last_query_text} {query_text_for_search}"
        else:
            enhanced_query = f"Context: {context}\n\nUser query: {query_text_for_search}"
    else:
        enhanced_query = query_text_for_search or ""
    
    # Parse query for situational components (only if we have query text) - use merged if available
    if not parsed_components_for_search and query_text_for_search:
        parsed_components_for_search = query_parser.parse_situational_query(enhanced_query)
    
    # Update gender filter if merged context has it
    if parsed_components_for_search.get('gender') and not gender_filter_for_search:
        gender_filter_for_search = parsed_components_for_search['gender']
        # Re-apply gender filter
        if gender_filter_for_search and 'gender' in results_df.columns:
            results_df = results_df[results_df['gender'] == gender_filter_for_search]
            print(f"✅ Applied gender filter from merged context: {gender_filter_for_search} ({len(results_df)} products)")
    
    # Get text embedding (with style enhancement) - use merged components if available
    text_emb = None
    if query_text_for_search:
        if openai_embedder:
            # Use style-enhanced embedding with parsed components (merged if correction)
            text_emb = get_style_embedding_query(enhanced_query, openai_embedder, parsed_components_for_search)
        else:
            # Fallback to sentence-transformers
            text_emb = enricher.get_text_embedding(enhanced_query)
    
    # Get visual embedding (if provided)
    visual_emb = None
    if image_embedding:
        visual_emb = np.array(image_embedding)
    elif use_visual:
        # Could retrieve from session if stored
        pass
    
    # Determine which embedding to use for search
    query_emb = None
    if text_emb is not None and visual_emb is not None:
        # Hybrid: prefer text for now (could combine)
        query_emb = text_emb
    elif visual_emb is not None:
        query_emb = visual_emb
    elif text_emb is not None:
        query_emb = text_emb
    else:
        return jsonify({'error': 'Failed to generate query embedding'}), 500
    
    # Helper function for semantic search (Pinecone or local)
    def perform_semantic_search(query_embedding, product_indices=None, top_k=10):
        """
        Perform semantic search using Pinecone or local embeddings.
        
        Args:
            query_embedding: Query embedding vector
            product_indices: Optional list of product indices to search (for filtering)
            top_k: Number of results to return
            
        Returns:
            List of (index, similarity) tuples sorted by similarity
        """
        if pinecone_index and query_embedding is not None:
            try:
                # Use Pinecone for search
                filter_dict = None
                if product_indices:
                    # Filter by product IDs in Pinecone
                    filter_dict = {"product_id": {"$in": [int(idx) for idx in product_indices]}}
                
                results = pinecone_index.query(
                    vector=query_embedding.tolist(),
                    top_k=min(top_k * 2, 100),  # Get more results for filtering
                    include_metadata=True,
                    filter=filter_dict
                )
                
                # Map Pinecone results back to DataFrame indices
                similarities = []
                for match in results.matches:
                    product_id = match.metadata.get('product_id')
                    if product_id is not None:
                        idx = int(product_id)
                        if product_indices is None or idx in product_indices:
                            similarities.append((idx, float(match.score)))
                
                return similarities
            except Exception as e:
                print(f"⚠️  Pinecone search error: {e}, falling back to local search")
        
        # Fallback to local search
        if query_embedding is None or (not embeddings_dict and not pinecone_index):
            return []
        
        similarities = []
        search_indices = product_indices if product_indices else products_df.index
        
        for idx in search_indices:
            if idx not in products_df.index:
                continue
            row = products_df.loc[idx]
            product_id = f"{row.get('name', idx)}_{idx}"
            emb_key = f"{product_id}_text"
            
            if emb_key in embeddings_dict:
                product_emb = np.array(embeddings_dict[emb_key])
                similarity = np.dot(query_embedding, product_emb) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(product_emb)
                )
                similarities.append((idx, similarity))
        
        return similarities
    
    # Simple keyword-based filtering (can be enhanced with NLP)
    query_lower = query_text.lower() if query_text else ""
    
    # Check if this is a gender-only query (using original query text)
    is_gender_only_query_check = query_lower in ['for men', 'for women', 'men', 'women', 'mens', 'womens']
    
    # Early check: Does this query imply a product search?
    # If not, return empty results immediately
    product_action_words = ['show', 'find', 'search', 'look', 'get', 'buy', 'want', 'need',
                           'see', 'display', 'list', 'recommend', 'suggest', 'give me',
                           'i want', 'i need', 'i\'m looking for', 'looking for', 'what',
                           'which', 'where can i', 'for men', 'for women']
    
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
    # Also allow style/situational queries (e.g., "night out in paris") even without explicit product type
    has_style_context = parsed_components_for_search and (
        parsed_components_for_search.get('location') or 
        parsed_components_for_search.get('occasion') or 
        parsed_components_for_search.get('weather') or 
        parsed_components_for_search.get('season') or
        parsed_components_for_search.get('style_keywords')
    )
    
    implies_product_search = (
        has_product_type or  # Has a product type
        (has_action_word and (has_attribute or has_price)) or  # Action + attribute/price
        (has_attribute and has_price) or  # Attribute + price
        has_attribute or  # Just attributes (e.g., "black wool", "minimalist classic")
        has_style_context or  # Has style/situational context (e.g., "night out in paris")
        (len([x for x in [has_action_word, has_product_type, has_attribute, has_price] if x]) >= 2) or
        (is_gender_only_query_check and context)  # Gender-only queries with context
    )
    
    # If query doesn't imply product search, return empty immediately
    if not implies_product_search:
        return jsonify({
            'query': query_text,
            'results': [],
            'count': 0,
            'session_id': session_id,
            'used_style_context': False,
            'parsed_components': parsed_components
        })
    
    # Start with all products (or filtered by gender if already applied)
    # Use gender_filter_for_search which may have been updated by merged context
    if gender_filter_for_search and 'gender' in products_df.columns:
        results_df = products_df[products_df['gender'] == gender_filter_for_search].copy()
        print(f"✅ Applied gender filter: {gender_filter_for_search} ({len(results_df)} products)")
    else:
        results_df = products_df.copy()
    
    # Detect "only" keyword - this enforces strict filtering
    query_lower = query_text_for_search.lower() if query_text_for_search else ""
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
    
    # Helper function for semantic search (Pinecone or local)
    def perform_semantic_search(query_embedding, product_indices=None, top_k=10):
        """
        Perform semantic search using Pinecone or local embeddings.
        
        Args:
            query_embedding: Query embedding vector
            product_indices: Optional list of product indices to search (for filtering)
            top_k: Number of results to return
            
        Returns:
            List of (index, similarity) tuples sorted by similarity
        """
        if pinecone_index and query_embedding is not None:
            try:
                # Use Pinecone for search
                filter_dict = None
                if product_indices:
                    # Filter by product IDs in Pinecone
                    filter_dict = {"product_id": {"$in": [int(idx) for idx in product_indices]}}
                
                results = pinecone_index.query(
                    vector=query_embedding.tolist(),
                    top_k=min(top_k * 2, 100),  # Get more results for filtering
                    include_metadata=True,
                    filter=filter_dict
                )
                
                # Map Pinecone results back to DataFrame indices
                similarities = []
                for match in results.matches:
                    product_id = match.metadata.get('product_id')
                    if product_id is not None:
                        idx = int(product_id)
                        if product_indices is None or idx in product_indices:
                            similarities.append((idx, float(match.score)))
                
                return similarities
            except Exception as e:
                print(f"⚠️  Pinecone search error: {e}, falling back to local search")
        
        # Fallback to local search
        if query_embedding is None or (not embeddings_dict and not pinecone_index):
            return []
        
        similarities = []
        search_indices = product_indices if product_indices else products_df.index
        
        for idx in search_indices:
            if idx not in products_df.index:
                continue
            row = products_df.loc[idx]
            product_id = f"{row.get('name', idx)}_{idx}"
            emb_key = f"{product_id}_text"
            
            if emb_key in embeddings_dict:
                product_emb = np.array(embeddings_dict[emb_key])
                similarity = np.dot(query_emb, product_emb) / (
                    np.linalg.norm(query_emb) * np.linalg.norm(product_emb)
                )
                similarities.append((idx, similarity))
        
        return similarities
    
    # If we have embeddings and filtered results, do semantic search ONLY on filtered results
    if query_emb is not None and not results_df.empty:
        similarities = perform_semantic_search(query_emb, product_indices=results_df.index.tolist(), top_k=top_k)
        
        # Sort by similarity and reorder results
        if similarities:
            similarities.sort(key=lambda x: x[1], reverse=True)
            sorted_indices = [idx for idx, _ in similarities[:top_k]]
            # Reorder results_df by similarity
            results_df = results_df.loc[sorted_indices] if sorted_indices else results_df.head(top_k)
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
        if not filtered_df.empty and query_emb is not None:
            similarities = perform_semantic_search(query_emb, product_indices=filtered_df.index.tolist(), top_k=top_k)
            
            if similarities:
                similarities.sort(key=lambda x: x[1], reverse=True)
                semantic_indices = [idx for idx, _ in similarities[:top_k]]
                results_df = filtered_df.loc[semantic_indices] if semantic_indices else filtered_df.head(top_k)
            else:
                # No embeddings found, just use filtered results
                results_df = filtered_df.head(top_k)
        elif not filtered_df.empty:
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
    
    # Replace NaN with None for JSON serialization and include index
    results_dict = []
    for idx, row in results_df.iterrows():
        product_dict = row.replace({np.nan: None}).to_dict()
        product_dict['index'] = int(idx)  # Add index for frontend tagging
        results_dict.append(product_dict)
    
    # Store in conversation with full context (use merged context if correction)
    conversation_manager.add_message(
        session_id, 
        "user", 
        query_text,
        metadata={
            "parsed_components": parsed_components_for_search,
            "applied_filters": {
                "gender": gender_filter_for_search,
                "product_type": parsed_components_for_search.get('product_type'),
                "color": None,  # Could extract from query
                "material": None,  # Could extract from query
                "price_max": None  # Could extract from query
            },
            "result_count": len(results_dict),
            "is_correction": is_correction,
            "query_intent": query_intent
        }
    )
    conversation_manager.add_message(
        session_id, 
        "assistant", 
        f"Found {len(results_df)} products",
        metadata={"result_count": len(results_df)}
    )
    
    # Add personalized recommendations if no query but preferences exist
    personalized_message = None
    if not query_text and user_preferences and not results_dict:
        # Generate personalized recommendations
        if user_preferences.get('favorite_colors'):
            color = user_preferences['favorite_colors'][0]
            personalized_message = f"Based on your style, you might like these {color} items:"
        elif user_preferences.get('preferred_categories'):
            category = user_preferences['preferred_categories'][0]
            personalized_message = f"Here are some new {category} you might enjoy:"
    
    return jsonify({
        'query': query_text,
        'results': results_dict,
        'count': len(results_df),
        'session_id': session_id,
        'used_style_context': extract_style_context(query_text) is not None if query_text else False,
        'parsed_components': parsed_components,
        'user_preferences': user_preferences,
        'personalized_message': personalized_message
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

@app.route('/api/compatibility', methods=['POST'])
def get_compatible_products():
    """Find products that go well with a given product."""
    global products_df, embeddings_dict, openai_embedder, pinecone_index
    
    data = request.get_json()
    product_id = data.get('product_id')  # Index or name
    compatibility_type = data.get('type', 'style')  # 'style', 'color', 'hybrid'
    top_k = data.get('top_k', 5)
    
    if products_df is None or products_df.empty:
        return jsonify({'error': 'No products loaded'}), 404
    
    # Get reference product
    try:
        if isinstance(product_id, int) or (isinstance(product_id, str) and product_id.isdigit()):
            ref_product = products_df.iloc[int(product_id)]
            ref_idx = int(product_id)
        else:
            ref_product = products_df[products_df['name'] == product_id].iloc[0]
            ref_idx = ref_product.name
    except (IndexError, KeyError):
        return jsonify({'error': 'Product not found'}), 404
    
    # Get reference product embedding
    ref_emb = None
    
    # Try OpenAI text embedding first
    if openai_embedder:
        description = str(ref_product.get('description', '') or ref_product.get('name', ''))
        if description and len(description) > 10:
            ref_emb = openai_embedder.get_embedding(description)
    
    # Fallback to stored embeddings
    if ref_emb is None:
        ref_id = f"{ref_product.get('name', ref_idx)}_{ref_idx}"
        ref_emb_key = f"{ref_id}_text"
        if ref_emb_key in embeddings_dict:
            ref_emb = np.array(embeddings_dict[ref_emb_key])
        else:
            ref_emb_key = f"{ref_id}_visual"
            if ref_emb_key in embeddings_dict:
                ref_emb = np.array(embeddings_dict[ref_emb_key])
    
    if ref_emb is None:
        return jsonify({'error': 'Product embedding not found'}), 404
    
    # Find similar products using Pinecone or local search
    if pinecone_index:
        try:
            results = pinecone_index.query(
                vector=ref_emb.tolist(),
                top_k=top_k + 1,  # +1 to exclude the reference product
                include_metadata=True,
                filter={"product_id": {"$ne": int(ref_idx)}}  # Exclude reference
            )
            
            compatible_products = []
            for match in results.matches:
                product_id_from_meta = match.metadata.get('product_id')
                if product_id_from_meta and product_id_from_meta != ref_idx:
                    try:
                        product_row = products_df.iloc[int(product_id_from_meta)]
                        # Filter by gender from reference product
                        ref_gender = ref_product.get('gender')
                        if ref_gender and pd.notna(ref_gender):
                            if product_row.get('gender') != ref_gender:
                                continue
                        compatible_products.append(product_row.replace({np.nan: None}).to_dict())
                    except (IndexError, KeyError):
                        continue
            
            return jsonify({
                'reference_product': ref_product.replace({np.nan: None}).to_dict(),
                'compatible_products': compatible_products[:top_k],
                'type': compatibility_type
            })
        except Exception as e:
            print(f"⚠️  Pinecone compatibility search error: {e}, falling back to local")
    
    # Fallback to local search
    similarities = []
    for idx, row in products_df.iterrows():
        if idx == ref_idx:
            continue
        
        product_id_str = f"{row.get('name', idx)}_{idx}"
        
        # Try text embedding
        product_emb = None
        emb_key = f"{product_id_str}_text"
        if emb_key in embeddings_dict:
            product_emb = np.array(embeddings_dict[emb_key])
        else:
            emb_key = f"{product_id_str}_visual"
            if emb_key in embeddings_dict:
                product_emb = np.array(embeddings_dict[emb_key])
        
        if product_emb is not None:
            similarity = np.dot(ref_emb, product_emb) / (
                np.linalg.norm(ref_emb) * np.linalg.norm(product_emb)
            )
            similarities.append((idx, similarity, row))
    
    # Sort and return
    similarities.sort(key=lambda x: x[1], reverse=True)
    results = []
    ref_gender = ref_product.get('gender')
    for _, _, row in similarities:
        # Filter by gender from reference product
        if ref_gender and pd.notna(ref_gender):
            if row.get('gender') != ref_gender:
                continue
        results.append(row.replace({np.nan: None}).to_dict())
        if len(results) >= top_k:
            break
    
    return jsonify({
        'reference_product': ref_product.replace({np.nan: None}).to_dict(),
        'compatible_products': results,
        'type': compatibility_type
    })

@app.route('/api/preferences/<session_id>', methods=['GET'])
def get_preferences(session_id: str):
    """Get user preferences for personalized recommendations."""
    preferences = conversation_manager.infer_preferences_from_history(session_id)
    stored_prefs = conversation_manager.get_user_preferences(session_id)
    
    # Merge inferred and stored preferences
    all_preferences = {**preferences, **stored_prefs}
    
    return jsonify({
        'session_id': session_id,
        'preferences': all_preferences,
        'tagged_products_count': len(conversation_manager.get_tagged_products(session_id)),
        'conversation_length': len(conversation_manager.conversations.get(session_id, []))
    })

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Handle image upload from user for visual search."""
    global fashion_clip_enricher
    
    try:
        data = request.get_json()
        image_data = data.get('image')  # Base64 encoded image
        session_id = data.get('session_id', 'default')
        
        if not image_data:
            return jsonify({'error': 'No image data provided'}), 400
        
        if not fashion_clip_enricher:
            return jsonify({'error': 'Fashion CLIP not available'}), 503
        
        # Decode base64 image
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
        image = Image.open(BytesIO(image_bytes))
        
        # Convert to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Process image with Fashion CLIP
        import torch
        processed = fashion_clip_enricher.fashion_clip_processor(
            images=[image],
            padding='max_length',
            return_tensors="pt"
        )
        pixel_values = processed['pixel_values'].to(fashion_clip_enricher.device)
        
        with torch.no_grad():
            image_features = fashion_clip_enricher.fashion_clip_model.get_image_features(
                pixel_values,
                normalize=True
            )
            query_emb = image_features.cpu().numpy().flatten()
        
        return jsonify({
            'status': 'success',
            'embedding_dim': len(query_emb),
            'embedding': query_emb.tolist(),  # Return embedding for client to use
            'message': 'Image processed successfully'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Starting Shopping Assistant API...")
    load_data()
    
    # Use port 5001 by default (5000 is often used by macOS AirPlay)
    port = int(os.getenv('PORT', 5001))
    print(f"📡 Server will run on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)

