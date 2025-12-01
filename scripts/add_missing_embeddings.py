#!/usr/bin/env python3
"""
Add embeddings for new products that don't have embeddings yet.
Compares CSV with existing embeddings and generates only for missing products.
"""
import pandas as pd
import pickle
from pathlib import Path
from tqdm import tqdm
import numpy as np
import os
import sys

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env.local or .env
from dotenv import load_dotenv
load_dotenv(dotenv_path=project_root / ".env.local")
load_dotenv(dotenv_path=project_root / ".env")

# Import after path is set
from backend.openai_client import OpenAIEmbedder

def build_style_focused_text(product_row: pd.Series) -> str:
    """
    Build comprehensive, style-focused text representation for a product.
    This tells the embedding model this is for a fashion stylist.
    
    Args:
        product_row: Product row from DataFrame
        
    Returns:
        Rich text representation optimized for style and fashion queries
    """
    parts = []
    
    # Start with a clear instruction for the embedding model
    parts.append("Fashion stylist product recommendation:")
    
    # Product name is crucial
    name = str(product_row.get('name', '')).strip()
    if name:
        parts.append(name)
    
    # Description provides rich context
    description = str(product_row.get('description', '')).strip()
    if description and description != 'nan':
        parts.append(description)
    
    # Add explicit style attributes if available
    style_attrs = []
    if 'colors' in product_row and str(product_row['colors']).strip() != 'nan':
        style_attrs.append(f"Colors: {product_row['colors']}")
    if 'materials' in product_row and str(product_row['materials']).strip() != 'nan':
        style_attrs.append(f"Materials: {product_row['materials']}")
    if 'patterns' in product_row and str(product_row['patterns']).strip() != 'nan':
        style_attrs.append(f"Patterns: {product_row['patterns']}")
    if 'style_keywords' in product_row and str(product_row['style_keywords']).strip() != 'nan':
        style_attrs.append(f"Style: {product_row['style_keywords']}")
    if 'occasion' in product_row and str(product_row['occasion']).strip() != 'nan':
        style_attrs.append(f"Occasion: {product_row['occasion']}")
    if 'fit' in product_row and str(product_row['fit']).strip() != 'nan':
        style_attrs.append(f"Fit: {product_row['fit']}")
    
    if style_attrs:
        parts.append(" ".join(style_attrs))
    
    # Add category and gender for context
    category = str(product_row.get('category', '')).strip()
    gender = str(product_row.get('gender', '')).strip()
    if category and category != 'nan':
        parts.append(f"Category: {category}")
    if gender and gender != 'nan':
        parts.append(f"Gender: {gender}")
    
    return ". ".join(filter(None, parts)).strip()

def add_missing_embeddings(use_pinecone: bool = True):
    """Add embeddings only for products that don't have embeddings yet."""
    data_dir = Path(__file__).parent.parent / "data" / "processed"
    csv_file = data_dir / "cos_all_products.csv"
    
    if not csv_file.exists():
        print(f"❌ File not found: {csv_file}")
        return
    
    # Load products
    df = pd.read_csv(csv_file)
    print(f"✅ Loaded {len(df)} products from CSV")
    
    # Load existing embeddings
    embeddings_file = data_dir / "embeddings_openai.pkl"
    existing_embeddings = {}
    if embeddings_file.exists():
        with open(embeddings_file, 'rb') as f:
            existing_embeddings = pickle.load(f)
        print(f"✅ Loaded {len(existing_embeddings)} existing embeddings")
    else:
        print(f"⚠️  No existing embeddings file found, will create new one")
    
    # Find products without embeddings
    # Match by URL first (more stable), then by index
    # Check which products have embeddings by URL or index
    products_without_embeddings = []
    existing_urls_with_embeddings = set()
    
    # First, try to match existing embeddings by URL if metadata is available
    # Otherwise, match by index pattern
    for emb_key in existing_embeddings.keys():
        # Try to extract URL from existing embeddings if stored
        # For now, we'll match by index pattern: "{index}_text"
        if emb_key.endswith("_text"):
            try:
                idx_str = emb_key.replace("_text", "")
                idx = int(idx_str)
                if idx < len(df):
                    url = str(df.iloc[idx].get('url', ''))
                    if url:
                        existing_urls_with_embeddings.add(url)
            except:
                pass
    
    # Now check which products need embeddings
    for idx, row in df.iterrows():
        url = str(row.get('url', ''))
        emb_key = f"{idx}_text"
        
        # Check if we have embedding by index OR by URL
        has_embedding = (
            emb_key in existing_embeddings or 
            (url and url in existing_urls_with_embeddings)
        )
        
        if not has_embedding:
            products_without_embeddings.append((idx, row))
    
    # Initialize Pinecone if requested (needed for both new embeddings and checking existing)
    pinecone_index = None
    if os.getenv("PINECONE_API_KEY"):
        try:
            from pinecone import Pinecone, ServerlessSpec
            
            pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            index_name = os.getenv("PINECONE_INDEX_NAME", "cos-products")
            
            # Check if index exists
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            if index_name not in existing_indexes:
                print(f"❌ Pinecone index '{index_name}' does not exist. Creating it...")
                # Need embedder for dimension
                try:
                    embedder_temp = OpenAIEmbedder(model="text-embedding-3-small")
                    pc.create_index(
                        name=index_name,
                        dimension=embedder_temp.embedding_dim,
                        metric="cosine",
                        spec=ServerlessSpec(
                            cloud="aws",
                            region=os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
                        )
                    )
                    print(f"✅ Created Pinecone index: {index_name}")
                except Exception as e:
                    print(f"⚠️  Could not create index: {e}")
            else:
                print(f"✅ Pinecone index '{index_name}' exists")
            
            pinecone_index = pc.Index(index_name)
            print(f"✅ Pinecone index '{index_name}' connected")
        except Exception as e:
            print(f"⚠️  Pinecone not available: {e}")
            pinecone_index = None
    
    if not products_without_embeddings:
        print(f"✅ All products already have local embeddings!")
        # Still check if we need to upload to Pinecone
        if pinecone_index:
            print(f"Checking Pinecone for missing vectors...")
            vectors_to_upsert = []
            for idx, row in tqdm(df.iterrows(), total=len(df), desc="Checking Pinecone"):
                product_id = str(idx)
                try:
                    # Check if vector exists in Pinecone
                    fetch_response = pinecone_index.fetch(ids=[product_id])
                    if product_id not in fetch_response.vectors:
                        # Need to upload this one
                        emb_key = f"{product_id}_text"
                        if emb_key in existing_embeddings:
                            emb = existing_embeddings[emb_key]
                            metadata = row.to_dict()
                            # Ensure metadata values are Pinecone-compatible
                            for k, v in metadata.items():
                                if isinstance(v, (np.int64, np.float64)):
                                    metadata[k] = v.item()
                                elif pd.isna(v) or v is None:
                                    metadata[k] = ""  # Convert None/NaN to empty string
                            metadata['product_id'] = int(idx)
                            vectors_to_upsert.append({
                                "id": product_id,
                                "values": emb if isinstance(emb, list) else emb.tolist(),
                                "metadata": metadata
                            })
                except Exception as e:
                    # If fetch fails, assume we need to upload
                    emb_key = f"{product_id}_text"
                    if emb_key in existing_embeddings:
                        emb = existing_embeddings[emb_key]
                        metadata = row.to_dict()
                        for k, v in metadata.items():
                            if isinstance(v, (np.int64, np.float64)):
                                metadata[k] = v.item()
                            elif pd.isna(v) or v is None:
                                metadata[k] = ""
                        metadata['product_id'] = int(idx)
                        vectors_to_upsert.append({
                            "id": product_id,
                            "values": emb if isinstance(emb, list) else emb.tolist(),
                            "metadata": metadata
                        })
            
            if vectors_to_upsert:
                print(f"Uploading {len(vectors_to_upsert)} vectors to Pinecone...")
                batch_size = 100
                for i in tqdm(range(0, len(vectors_to_upsert), batch_size), desc="Uploading to Pinecone"):
                    batch = vectors_to_upsert[i:i + batch_size]
                    pinecone_index.upsert(vectors=batch)
                print(f"✅ Uploaded {len(vectors_to_upsert)} vectors to Pinecone")
            else:
                print(f"✅ All embeddings already in Pinecone!")
        return
    
    print(f"📝 Found {len(products_without_embeddings)} products without embeddings")
    
    # Initialize OpenAI embedder
    try:
        embedder = OpenAIEmbedder(model="text-embedding-3-small")
        print("✅ OpenAI embedder initialized")
    except Exception as e:
        print(f"❌ Failed to initialize OpenAI: {e}")
        return
    
    # Generate embeddings for missing products
    new_embeddings = {}
    vectors_to_upsert = []
    
    for idx, row in tqdm(products_without_embeddings, desc="Generating embeddings for new products"):
        product_id = str(idx)
        
        # Build style-focused text for embedding
        text_to_embed = build_style_focused_text(row)
        
        if len(text_to_embed) > 10:
            emb = embedder.get_embedding(text_to_embed)
            if emb is not None:
                new_embeddings[f"{product_id}_text"] = emb.tolist()
                
                # Prepare for Pinecone upsert
                if pinecone_index:
                    metadata = row.to_dict()
                    # Ensure metadata values are Pinecone-compatible
                    # Pinecone doesn't accept None/null values - convert to empty string
                    for k, v in metadata.items():
                        if isinstance(v, (np.int64, np.float64)):
                            metadata[k] = v.item()
                        elif pd.isna(v) or v is None:
                            metadata[k] = ""  # Convert None/NaN to empty string for Pinecone
                        elif isinstance(v, str) and len(v) == 0:
                            metadata[k] = ""  # Keep empty strings as is
                    metadata['product_id'] = int(idx)
                    
                    vectors_to_upsert.append({
                        "id": product_id,
                        "values": emb.tolist(),
                        "metadata": metadata
                    })
    
    # Merge with existing embeddings
    all_embeddings = {**existing_embeddings, **new_embeddings}
    
    # Save updated embeddings
    with open(embeddings_file, 'wb') as f:
        pickle.dump(all_embeddings, f)
    print(f"\n✅ Saved {len(all_embeddings)} total embeddings to {embeddings_file}")
    print(f"   (Added {len(new_embeddings)} new embeddings)")
    
    # Upsert to Pinecone
    if pinecone_index and vectors_to_upsert:
        print(f"Uploading {len(vectors_to_upsert)} new vectors to Pinecone...")
        batch_size = 100
        for i in tqdm(range(0, len(vectors_to_upsert), batch_size), desc="Uploading to Pinecone"):
            batch = vectors_to_upsert[i:i + batch_size]
            pinecone_index.upsert(vectors=batch)
        print(f"✅ Uploaded new vectors to Pinecone")
        
        # Get updated stats
        try:
            stats = pinecone_index.describe_index_stats()
            vector_count = stats.total_vector_count
            print(f"☁️  Pinecone index now has {vector_count} total vectors")
        except:
            pass
    
    print(f"\n{'='*60}")
    print("EMBEDDING UPDATE SUMMARY")
    print(f"{'='*60}")
    print(f"✅ New embeddings generated: {len(new_embeddings)}/{len(products_without_embeddings)}")
    print(f"✅ Total embeddings: {len(all_embeddings)}")
    print(f"💾 Local backup saved to: {embeddings_file}")
    if pinecone_index:
        print(f"☁️  Pinecone index: {pinecone_index.name}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    add_missing_embeddings()

