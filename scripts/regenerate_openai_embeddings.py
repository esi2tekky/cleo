#!/usr/bin/env python3
"""
Regenerate product embeddings using OpenAI API with style-focused context.
Creates robust embeddings that include product descriptions and style information
for a fashion stylist assistant.
"""
import pandas as pd
import pickle
from pathlib import Path
import numpy as np
import os
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to load from .env or .env.local file if it exists
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent
    # Try .env.local first (common for local development)
    env_local_path = project_root / '.env.local'
    env_path = project_root / '.env'
    
    if env_local_path.exists():
        load_dotenv(env_local_path)
        print(f"✅ Loaded environment variables from .env.local")
    elif env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment variables from .env")
except ImportError:
    pass  # python-dotenv not installed, skip

from backend.openai_client import OpenAIEmbedder
from tqdm import tqdm

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
    
    # Add stylist context prefix
    parts.append("Fashion stylist product recommendation:")
    
    # Product name
    name = str(product_row.get('name', '')).strip()
    if name and name != 'nan':
        parts.append(f"Product: {name}")
    
    # Category
    category = str(product_row.get('category', '')).strip()
    if category and category != 'nan':
        parts.append(f"Category: {category}")
    
    # Description - this is crucial for style understanding
    description = str(product_row.get('description', '')).strip()
    if description and description != 'nan' and len(description) > 10:
        parts.append(f"Description: {description}")
    
    # Price (for budget-aware styling)
    price = product_row.get('price', '')
    if pd.notna(price) and price:
        parts.append(f"Price: ${price}")
    
    # Extract style-relevant information from description
    style_keywords = []
    desc_lower = description.lower() if description else ""
    
    # Material keywords
    materials = ['wool', 'cotton', 'cashmere', 'merino', 'silk', 'linen', 'mohair', 'alpaca', 'leather', 'denim']
    found_materials = [m for m in materials if m in desc_lower]
    if found_materials:
        style_keywords.extend(found_materials)
    
    # Style keywords
    style_terms = ['minimalist', 'classic', 'modern', 'casual', 'formal', 'elegant', 'sophisticated', 
                   'oversized', 'fitted', 'relaxed', 'tailored', 'versatile', 'timeless', 'chic', 
                   'polished', 'refined', 'laid-back', 'comfortable', 'stylish']
    found_styles = [s for s in style_terms if s in desc_lower]
    if found_styles:
        style_keywords.extend(found_styles)
    
    # Fit keywords
    fit_terms = ['straight-leg', 'tapered', 'wide-leg', 'slim', 'relaxed', 'oversized', 'fitted', 'loose']
    found_fits = [f for f in fit_terms if f in desc_lower]
    if found_fits:
        style_keywords.extend(found_fits)
    
    # Color keywords
    colors = ['black', 'white', 'navy', 'beige', 'brown', 'grey', 'gray', 'red', 'blue', 'green', 
              'yellow', 'pink', 'purple', 'orange', 'tan', 'camel', 'cream', 'ivory', 'charcoal', 'olive']
    found_colors = [c for c in colors if c in desc_lower]
    if found_colors:
        style_keywords.extend(found_colors)
    
    # Occasion keywords
    occasion_terms = ['evening', 'casual', 'formal', 'office', 'weekend', 'beach', 'winter', 'summer']
    found_occasions = [o for o in occasion_terms if o in desc_lower]
    if found_occasions:
        style_keywords.extend(found_occasions)
    
    # Add extracted style information
    if style_keywords:
        unique_keywords = list(dict.fromkeys(style_keywords))  # Preserve order, remove duplicates
        parts.append(f"Style attributes: {', '.join(unique_keywords[:15])}")  # Limit to 15 keywords
    
    # Add explicit styling context
    parts.append("This product is suitable for fashion styling recommendations, outfit coordination, and style matching.")
    
    # Combine all parts
    full_text = " ".join(parts)
    return full_text

def regenerate_embeddings(use_pinecone: bool = True):
    """
    Regenerate all product embeddings with OpenAI and optionally upload to Pinecone.
    
    Args:
        use_pinecone: Whether to upload embeddings to Pinecone
    """
    data_dir = Path(__file__).parent.parent / "data" / "processed"
    csv_file = data_dir / "cos_all_products.csv"
    
    if not csv_file.exists():
        print(f"❌ File not found: {csv_file}")
        return
    
    # Load products
    df = pd.read_csv(csv_file)
    print(f"✅ Loaded {len(df)} products")
    
    # Initialize OpenAI embedder
    try:
        embedder = OpenAIEmbedder(model="text-embedding-3-small")
        print("✅ OpenAI embedder initialized")
    except Exception as e:
        print(f"❌ Failed to initialize OpenAI: {e}")
        return
    
    # Initialize Pinecone if requested
    pinecone_index = None
    if use_pinecone and os.getenv("PINECONE_API_KEY"):
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
                print(f"✅ Created Pinecone index: {index_name}")
            else:
                print(f"✅ Using existing Pinecone index: {index_name}")
            
            pinecone_index = pc.Index(index_name)
            print(f"✅ Pinecone index connected")
        except Exception as e:
            print(f"⚠️  Pinecone initialization failed: {e}")
            print("   Continuing with local storage only...")
            use_pinecone = False
    
    # Generate embeddings
    embeddings_dict = {}
    pinecone_vectors = []
    
    successful = 0
    failed = 0
    
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Generating embeddings"):
        product_id = f"{row.get('name', idx)}_{idx}"
        
        # Build style-focused text representation
        text = build_style_focused_text(row)
        
        if len(text) > 10:
            emb = embedder.get_embedding(text)
            if emb is not None:
                successful += 1
                embeddings_dict[f"{product_id}_text"] = emb.tolist()
                
                # Prepare Pinecone vector
                if use_pinecone and pinecone_index:
                    metadata = {
                        "product_id": int(idx),
                        "name": str(row.get('name', '')),
                        "category": str(row.get('category', '')),
                        "price": float(row.get('price', 0)) if pd.notna(row.get('price')) else 0.0,
                        "url": str(row.get('url', '')),
                        "primary_image": str(row.get('primary_image', '')),
                    }
                    
                    # Add optional fields if they exist
                    if 'description' in row and pd.notna(row['description']):
                        metadata["description"] = str(row['description'])[:1000]  # Limit length
                    if 'colors' in row and pd.notna(row['colors']):
                        metadata["colors"] = str(row['colors'])
                    if 'materials' in row and pd.notna(row['materials']):
                        metadata["materials"] = str(row['materials'])
                    
                    pinecone_vectors.append({
                        "id": f"product_{idx}_text",
                        "values": emb.tolist(),
                        "metadata": metadata
                    })
                    
                    # Batch upload to Pinecone (every 100 vectors)
                    if len(pinecone_vectors) >= 100:
                        try:
                            pinecone_index.upsert(vectors=pinecone_vectors)
                            pinecone_vectors = []
                        except Exception as e:
                            print(f"⚠️  Pinecone upload error: {e}")
            else:
                failed += 1
        else:
            failed += 1
    
    # Upload remaining vectors to Pinecone
    if use_pinecone and pinecone_index and pinecone_vectors:
        try:
            pinecone_index.upsert(vectors=pinecone_vectors)
            print(f"✅ Uploaded final batch to Pinecone")
        except Exception as e:
            print(f"⚠️  Final Pinecone upload error: {e}")
    
    # Save local backup
    embeddings_file = data_dir / "embeddings_openai.pkl"
    with open(embeddings_file, 'wb') as f:
        pickle.dump(embeddings_dict, f)
    
    print(f"\n{'='*60}")
    print("EMBEDDING GENERATION SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Successful: {successful}/{len(df)}")
    print(f"❌ Failed: {failed}/{len(df)}")
    print(f"💾 Local backup saved to: {embeddings_file}")
    if use_pinecone and pinecone_index:
        print(f"☁️  Pinecone index: {os.getenv('PINECONE_INDEX_NAME', 'cos-products')}")
        try:
            stats = pinecone_index.describe_index_stats()
            print(f"   Total vectors: {stats.get('total_vector_count', 'unknown')}")
        except:
            pass
    print(f"{'='*60}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Regenerate OpenAI embeddings for products")
    parser.add_argument("--no-pinecone", action="store_true", help="Skip Pinecone upload")
    args = parser.parse_args()
    
    regenerate_embeddings(use_pinecone=not args.no_pinecone)

