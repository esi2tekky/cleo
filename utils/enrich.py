#!/usr/bin/env python3
"""
Enrichment module for COS product data.
Adds visual embeddings and style attributes for style-related queries.

Methods:
1. Visual embeddings using Fashion CLIP (fashion-specific model) or OpenAI CLIP
2. Text-based style extraction from descriptions
3. Hybrid features combining visual + text
"""
import os
import re
import json
import pickle
import requests
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
from PIL import Image
from io import BytesIO
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# Try to import PyTorch
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("⚠️  PyTorch not available. Install with: pip install torch torchvision")

# Try to import Fashion CLIP from Hugging Face (preferred for fashion)
try:
    from transformers import AutoModel, AutoProcessor
    FASHION_CLIP_AVAILABLE = True
except ImportError:
    FASHION_CLIP_AVAILABLE = False
    print("⚠️  Transformers not available. Install with: pip install transformers")

# Try to import OpenAI CLIP (fallback)
try:
    if TORCH_AVAILABLE:
        import clip
        OPENAI_CLIP_AVAILABLE = True
    else:
        OPENAI_CLIP_AVAILABLE = False
except ImportError:
    OPENAI_CLIP_AVAILABLE = False
    if TORCH_AVAILABLE:
        print("⚠️  OpenAI CLIP not available. Install with: pip install git+https://github.com/openai/CLIP.git")

# Text embeddings fallback
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class StyleEnricher:
    """
    Enriches product data with visual embeddings and style attributes.
    Supports Fashion CLIP (default, better for fashion) or OpenAI CLIP.
    """
    
    def __init__(self, 
                 use_clip: bool = True,
                 use_fashion_clip: bool = True,
                 clip_model: str = "ViT-B/32",
                 fashion_clip_model: str = "Marqo/marqo-fashionCLIP",
                 text_model: str = "all-MiniLM-L6-v2",
                 device: Optional[str] = None):
        """
        Initialize the enricher.
        
        Args:
            use_clip: Whether to use CLIP for visual embeddings
            use_fashion_clip: Whether to use Fashion CLIP (True) or OpenAI CLIP (False)
            clip_model: OpenAI CLIP model name (ViT-B/32, ViT-L/14, etc.) - only used if use_fashion_clip=False
            fashion_clip_model: Fashion CLIP model name from Hugging Face
            text_model: Sentence transformer model for text embeddings
            device: Device to use ('cuda', 'cpu', or None for auto)
        """
        self.use_fashion_clip = use_fashion_clip
        self.use_clip = use_clip and (FASHION_CLIP_AVAILABLE or OPENAI_CLIP_AVAILABLE)
        
        if TORCH_AVAILABLE:
            self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = "cpu"
        
        # Initialize Fashion CLIP (preferred for fashion products)
        if self.use_clip and use_fashion_clip and FASHION_CLIP_AVAILABLE:
            print(f"👗 Loading Fashion CLIP model: {fashion_clip_model} on {self.device}")
            try:
                # Workaround for meta tensor issue in open_clip
                # We need to patch the open_clip factory to handle meta tensors properly
                import open_clip.factory as factory_module
                original_set_device = factory_module._set_model_device_and_precision
                
                def patched_set_device(model, device, precision, is_timm_model):
                    """Patched version that handles meta tensors."""
                    try:
                        # Try original method first
                        return original_set_device(model, device, precision, is_timm_model)
                    except NotImplementedError as e:
                        if "meta tensor" in str(e).lower():
                            # If meta tensor error, use to_empty() method
                            if hasattr(model, 'to_empty'):
                                # Create empty model on target device
                                model = model.to_empty(device=device)
                                # Load state dict after moving
                                # Note: This is a workaround - the model should already have weights
                                pass
                            else:
                                # Fallback: just set eval mode, model should work on CPU
                                model.eval()
                        else:
                            raise
                    return model
                
                # Temporarily patch the function
                factory_module._set_model_device_and_precision = patched_set_device
                
                try:
                    # Load model with patch in place
                    self.fashion_clip_model = AutoModel.from_pretrained(
                        fashion_clip_model, 
                        trust_remote_code=True,
                        low_cpu_mem_usage=False
                    )
                    
                    # Load processor
                    self.fashion_clip_processor = AutoProcessor.from_pretrained(
                        fashion_clip_model, 
                        trust_remote_code=True
                    )
                    
                    # Restore original function
                    factory_module._set_model_device_and_precision = original_set_device
                    
                    # Ensure model is in eval mode
                    self.fashion_clip_model.eval()
                    self.clip_model = None
                    self.clip_preprocess = None
                    print("✅ Fashion CLIP loaded (fashion-optimized)")
                    
                except Exception as load_error:
                    # Restore original function even if loading fails
                    factory_module._set_model_device_and_precision = original_set_device
                    raise load_error
            except Exception as e:
                print(f"⚠️  Failed to load Fashion CLIP: {e}")
                print("   Falling back to OpenAI CLIP...")
                self.use_fashion_clip = False
                if OPENAI_CLIP_AVAILABLE:
                    self._init_openai_clip(clip_model)
                else:
                    print("   ⚠️  OpenAI CLIP also not available. Visual embeddings disabled.")
                    self.clip_model = None
                    self.clip_preprocess = None
                    self.fashion_clip_model = None
                    self.fashion_clip_processor = None
        
        # Initialize OpenAI CLIP (fallback or if explicitly requested)
        elif self.use_clip and not use_fashion_clip and OPENAI_CLIP_AVAILABLE:
            self._init_openai_clip(clip_model)
        
        else:
            self.clip_model = None
            self.clip_preprocess = None
            self.fashion_clip_model = None
            self.fashion_clip_processor = None
            if use_clip:
                print("⚠️  CLIP requested but not available. Using text-only embeddings.")
        
        # Initialize text model
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            print(f"📝 Loading text model: {text_model}")
            self.text_model = SentenceTransformer(text_model)
            print("✅ Text model loaded")
        else:
            self.text_model = None
            print("⚠️  Sentence transformers not available. Text embeddings disabled.")
    
    def _init_openai_clip(self, clip_model: str):
        """Initialize OpenAI CLIP model."""
        if not OPENAI_CLIP_AVAILABLE:
            return
        print(f"📸 Loading OpenAI CLIP model: {clip_model} on {self.device}")
        self.clip_model, self.clip_preprocess = clip.load(clip_model, device=self.device)
        self.clip_model.eval()
        self.fashion_clip_model = None
        self.fashion_clip_processor = None
        print("✅ OpenAI CLIP loaded")
    
    def download_image(self, url: str, timeout: int = 10) -> Optional[Image.Image]:
        """Download and load an image from URL."""
        try:
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            return img
        except Exception as e:
            print(f"  ⚠️  Failed to download {url[:60]}...: {e}")
            return None
    
    def get_visual_embedding(self, image_url: str) -> Optional[np.ndarray]:
        """
        Generate visual embedding from image URL using Fashion CLIP or OpenAI CLIP.
        
        Args:
            image_url: URL of the product image
            
        Returns:
            Embedding vector (512-dim typically) or None if failed
        """
        if not self.use_clip:
            return None
        
        # Check if any CLIP model is available
        has_fashion_clip = hasattr(self, 'fashion_clip_model') and self.fashion_clip_model is not None
        has_openai_clip = hasattr(self, 'clip_model') and self.clip_model is not None
        
        if not has_fashion_clip and not has_openai_clip:
            return None
        
        img = self.download_image(image_url)
        if img is None:
            return None
        
        try:
            # Use Fashion CLIP if available
            if self.use_fashion_clip and has_fashion_clip:
                # Process image with Fashion CLIP processor
                processed = self.fashion_clip_processor(
                    images=[img],
                    padding='max_length',
                    return_tensors="pt"
                )
                pixel_values = processed['pixel_values'].to(self.device)
                
                with torch.no_grad():
                    image_features = self.fashion_clip_model.get_image_features(
                        pixel_values, 
                        normalize=True
                    )
                    # Convert to numpy
                    embedding = image_features.cpu().numpy().flatten()
                
                return embedding
            
            # Fallback to OpenAI CLIP
            elif self.clip_model is not None and self.clip_preprocess is not None:
                # Preprocess and encode
                img_tensor = self.clip_preprocess(img).unsqueeze(0).to(self.device)
                
                with torch.no_grad():
                    image_features = self.clip_model.encode_image(img_tensor)
                    # Normalize
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                    # Convert to numpy
                    embedding = image_features.cpu().numpy().flatten()
                
                return embedding
            
            return None
            
        except Exception as e:
            print(f"  ⚠️  CLIP encoding error: {e}")
            return None
    
    def get_text_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Generate text embedding from description.
        
        Args:
            text: Product description text
            
        Returns:
            Embedding vector or None if failed
        """
        if not self.text_model or not text or len(text.strip()) < 10:
            return None
        
        try:
            embedding = self.text_model.encode(text, convert_to_numpy=True)
            return embedding
        except Exception as e:
            print(f"  ⚠️  Text encoding error: {e}")
            return None
    
    def extract_style_attributes_from_image(self, image_url: str, threshold: float = -0.05) -> Dict[str, any]:
        """
        Extract style attributes from product image using CLIP vision-language matching.
        
        Args:
            image_url: URL of the product image
            threshold: Similarity threshold for attribute detection (0-1)
            
        Returns:
            Dictionary of style attributes detected from image
        """
        attributes = {
            'colors': [],
            'materials': [],
            'patterns': [],
            'fit': None,
            'style_keywords': [],
            'occasion': []
        }
        
        if not self.use_clip:
            return attributes
        
        # Check if any CLIP model is available
        has_fashion_clip = hasattr(self, 'fashion_clip_model') and self.fashion_clip_model is not None
        has_openai_clip = hasattr(self, 'clip_model') and self.clip_model is not None
        
        if not has_fashion_clip and not has_openai_clip:
            return attributes
        
        img = self.download_image(image_url)
        if img is None:
            return attributes
        
        try:
            # Get image embedding
            if self.use_fashion_clip and has_fashion_clip:
                processed = self.fashion_clip_processor(
                    images=[img],
                    padding='max_length',
                    return_tensors="pt"
                )
                pixel_values = processed['pixel_values'].to(self.device)
                
                with torch.no_grad():
                    image_features = self.fashion_clip_model.get_image_features(
                        pixel_values, 
                        normalize=True
                    )
                
                # Test color queries - use more descriptive phrases for better CLIP matching
                color_queries = [
                    "black color", "white color", "navy blue", "beige color", "grey color", "gray color", 
                    "brown color", "tan color", "cream color", "ivory color", "red color", "blue color", 
                    "green color", "yellow color", "pink color", "purple color", "orange color", 
                    "camel color", "charcoal color", "olive green"
                ]
                
                # Test material queries - use descriptive phrases
                material_queries = [
                    "wool material", "cotton fabric", "cashmere material", "merino wool", "silk fabric", 
                    "linen material", "mohair blend", "alpaca wool", "leather material", "denim fabric", 
                    "jersey knit", "knitted fabric"
                ]
                
                # Test pattern queries - use descriptive phrases
                pattern_queries = [
                    "striped pattern", "solid color", "patterned design", "check pattern", "plaid pattern", 
                    "cable knit pattern", "ribbed texture", "textured surface", "plain design", 
                    "color block design", "space dyed pattern"
                ]
                
                # Test style queries - use descriptive phrases
                style_queries = [
                    "minimalist style", "classic design", "modern style", "casual wear", "formal attire", 
                    "elegant style", "oversized fit", "fitted cut", "relaxed fit", "sophisticated design"
                ]
                
                # Process text queries - Fashion CLIP processor expects list of strings
                all_queries = color_queries + material_queries + pattern_queries + style_queries
                text_inputs = self.fashion_clip_processor(
                    text=all_queries,
                    padding='max_length',
                    return_tensors="pt"
                )
                input_ids = text_inputs['input_ids'].to(self.device)
                
                with torch.no_grad():
                    text_features = self.fashion_clip_model.get_text_features(
                        input_ids,
                        normalize=True
                    )
                
                # Compute similarities
                similarities = (image_features @ text_features.T).cpu().numpy().flatten()
                
                # Extract colors - use top-k approach (increased to top 5)
                color_base = ["black", "white", "navy", "beige", "grey", "gray", "brown", "tan",
                             "cream", "ivory", "red", "blue", "green", "yellow", "pink", 
                             "purple", "orange", "camel", "charcoal", "olive"]
                color_similarities = similarities[:len(color_queries)]
                # Get top 5 colors
                top_color_indices = np.argsort(color_similarities)[-5:][::-1]
                for idx in top_color_indices:
                    if color_similarities[idx] > threshold:
                        attributes['colors'].append(color_base[idx])
                
                # Extract materials - use top-k approach (increased to top 5)
                material_base = ["wool", "cotton", "cashmere", "merino", "silk", "linen",
                                "mohair", "alpaca", "leather", "denim", "jersey", "knit"]
                material_start = len(color_queries)
                material_end = material_start + len(material_queries)
                material_similarities = similarities[material_start:material_end]
                # Get top 5 materials
                top_material_indices = np.argsort(material_similarities)[-5:][::-1]
                for idx in top_material_indices:
                    if material_similarities[idx] > threshold:
                        attributes['materials'].append(material_base[idx])
                
                # Extract patterns - use top-k approach (increased to top 4)
                pattern_base = ["striped", "solid", "patterned", "check", "plaid", "cable knit",
                               "ribbed", "textured", "plain", "color block", "space dyed"]
                pattern_start = material_end
                pattern_end = pattern_start + len(pattern_queries)
                pattern_similarities = similarities[pattern_start:pattern_end]
                # Get top 4 patterns
                top_pattern_indices = np.argsort(pattern_similarities)[-4:][::-1]
                for idx in top_pattern_indices:
                    if pattern_similarities[idx] > threshold:
                        attributes['patterns'].append(pattern_base[idx])
                
                # Extract style keywords - use top-k approach (increased to top 5)
                style_base = ["minimalist", "classic", "modern", "casual", "formal", "elegant",
                             "oversized", "fitted", "relaxed", "sophisticated"]
                style_start = pattern_end
                style_similarities = similarities[style_start:]
                # Get top 5 style keywords
                top_style_indices = np.argsort(style_similarities)[-5:][::-1]
                for idx in top_style_indices:
                    if style_similarities[idx] > threshold:
                        attributes['style_keywords'].append(style_base[idx])
                
            elif has_openai_clip:
                # Similar approach for OpenAI CLIP
                img_tensor = self.clip_preprocess(img).unsqueeze(0).to(self.device)
                
                with torch.no_grad():
                    image_features = self.clip_model.encode_image(img_tensor)
                    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                
                # Create text queries with descriptive phrases
                color_queries = ["black color", "white color", "navy blue", "beige color", "grey color", 
                                "brown color", "red color", "blue color", "green color", "tan color",
                                "cream color", "camel color", "charcoal color"]
                material_queries = ["wool material", "cotton fabric", "cashmere material", "merino wool", 
                                  "silk fabric", "leather material", "denim fabric", "mohair blend",
                                  "alpaca wool", "jersey knit", "knitted fabric"]
                pattern_queries = ["striped pattern", "solid color", "patterned design", "check pattern", 
                                  "ribbed texture", "cable knit pattern", "textured surface", "plain design"]
                style_queries = ["minimalist style", "classic design", "modern style", "casual wear", 
                                "oversized fit", "fitted cut", "relaxed fit", "elegant style"]
                
                queries = {
                    'colors': (color_queries, ["black", "white", "navy", "beige", "grey", "brown", 
                                               "red", "blue", "green", "tan", "cream", "camel", "charcoal"]),
                    'materials': (material_queries, ["wool", "cotton", "cashmere", "merino", "silk", 
                                                    "leather", "denim", "mohair", "alpaca", "jersey", "knit"]),
                    'patterns': (pattern_queries, ["striped", "solid", "patterned", "check", "ribbed", 
                                                 "cable knit", "textured", "plain"]),
                    'style_keywords': (style_queries, ["minimalist", "classic", "modern", "casual", 
                                                      "oversized", "fitted", "relaxed", "elegant"])
                }
                
                for attr_type, (attr_queries, attr_base) in queries.items():
                    text_tokens = clip.tokenize(attr_queries).to(self.device)
                    with torch.no_grad():
                        text_features = self.clip_model.encode_text(text_tokens)
                        text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                    
                    similarities = (image_features @ text_features.T).cpu().numpy().flatten()
                    
                    # Use top-k approach (top 5 for colors/materials/style, top 4 for patterns)
                    k = 5 if attr_type != 'patterns' else 4
                    top_indices = np.argsort(similarities)[-k:][::-1]
                    
                    for idx in top_indices:
                        if similarities[idx] > threshold:
                            if attr_type == 'colors':
                                attributes['colors'].append(attr_base[idx])
                            elif attr_type == 'materials':
                                attributes['materials'].append(attr_base[idx])
                            elif attr_type == 'patterns':
                                attributes['patterns'].append(attr_base[idx])
                            elif attr_type == 'style_keywords':
                                attributes['style_keywords'].append(attr_base[idx])
            
            return attributes
            
        except Exception as e:
            print(f"  ⚠️  Image-based attribute extraction error: {e}")
            return attributes
    
    def get_color_matches(self, colors: List[str]) -> Dict[str, List[str]]:
        """
        Get color matching/compatibility suggestions based on extracted colors.
        
        Args:
            colors: List of colors extracted from the product
            
        Returns:
            Dictionary with 'complementary', 'neutral', and 'monochrome' color suggestions
        """
        if not colors:
            return {
                'complementary': [],
                'neutral': [],
                'monochrome': []
            }
        
        # Normalize color names (handle variations like mélange, etc.)
        normalized_colors = []
        for color in colors:
            color_lower = color.lower().strip()
            # Map variations to standard names
            color_map = {
                'mélange': 'beige',
                'melange': 'beige',
                'dgrad': 'grey',
                'degrade': 'grey',
                'steel-blue': 'blue',
                'steel blue': 'blue',
                'dark-brown': 'brown',
                'dark brown': 'brown',
                'light-brown': 'tan',
                'light brown': 'tan'
            }
            normalized = color_map.get(color_lower, color_lower)
            normalized_colors.append(normalized)
        
        # Color compatibility rules (fashion-focused)
        color_wheel = {
            'red': ['green', 'blue', 'navy', 'white', 'black', 'beige', 'grey'],
            'blue': ['orange', 'red', 'white', 'navy', 'grey', 'beige', 'brown'],
            'green': ['red', 'pink', 'brown', 'beige', 'white', 'navy', 'tan'],
            'yellow': ['purple', 'navy', 'grey', 'white', 'black', 'brown'],
            'orange': ['blue', 'navy', 'brown', 'beige', 'white', 'grey'],
            'purple': ['yellow', 'green', 'grey', 'white', 'black', 'beige'],
            'pink': ['green', 'navy', 'grey', 'white', 'beige', 'brown'],
            'brown': ['blue', 'green', 'beige', 'cream', 'white', 'navy', 'tan', 'olive'],
            'beige': ['navy', 'brown', 'black', 'white', 'grey', 'olive', 'tan', 'camel'],
            'navy': ['beige', 'white', 'red', 'orange', 'yellow', 'grey', 'brown', 'tan'],
            'black': ['white', 'beige', 'red', 'navy', 'grey', 'any color', 'brown'],
            'white': ['black', 'navy', 'red', 'any color', 'grey', 'beige', 'brown'],
            'grey': ['black', 'white', 'navy', 'red', 'pink', 'any color', 'brown', 'beige'],
            'gray': ['black', 'white', 'navy', 'red', 'pink', 'any color', 'brown', 'beige'],
            'camel': ['navy', 'black', 'white', 'brown', 'beige', 'tan', 'olive'],
            'tan': ['navy', 'brown', 'beige', 'white', 'olive', 'camel', 'grey'],
            'cream': ['navy', 'brown', 'black', 'grey', 'olive', 'beige', 'tan'],
            'ivory': ['navy', 'black', 'brown', 'grey', 'any color', 'beige'],
            'charcoal': ['white', 'beige', 'navy', 'red', 'any color', 'grey'],
            'olive': ['brown', 'beige', 'cream', 'navy', 'white', 'tan', 'camel']
        }
        
        # Neutral colors that go with everything
        neutrals = ['black', 'white', 'navy', 'grey', 'gray', 'beige', 'cream', 'ivory', 'charcoal']
        
        complementary = []
        neutral = []
        monochrome = []
        
        for color in normalized_colors:
            color_lower = color.lower()
            
            # Get complementary colors
            if color_lower in color_wheel:
                complementary.extend(color_wheel[color_lower])
            
            # Add neutrals that work with this color
            neutral.extend(neutrals)
            
            # Monochrome: same color family variations
            if color_lower in ['black', 'charcoal', 'grey', 'gray']:
                monochrome.extend(['black', 'charcoal', 'grey', 'gray', 'white'])
            elif color_lower in ['brown', 'tan', 'camel', 'beige', 'cream']:
                monochrome.extend(['brown', 'tan', 'camel', 'beige', 'cream', 'ivory'])
            elif color_lower in ['navy', 'blue']:
                monochrome.extend(['navy', 'blue', 'white', 'grey', 'black'])
            elif color_lower in ['white', 'cream', 'ivory']:
                monochrome.extend(['white', 'cream', 'ivory', 'beige', 'grey', 'navy'])
            elif color_lower == 'red':
                monochrome.extend(['red', 'pink', 'burgundy', 'maroon', 'white', 'black'])
            elif color_lower == 'green':
                monochrome.extend(['green', 'olive', 'sage', 'forest', 'white', 'beige'])
        
        # Remove duplicates, remove "any color" placeholder, and limit
        complementary_clean = [c for c in set(complementary) if c != 'any color']
        neutral_clean = list(set(neutral))
        monochrome_clean = list(set(monochrome))
        
        return {
            'complementary': complementary_clean[:10],
            'neutral': neutral_clean[:8],
            'monochrome': monochrome_clean[:8]
        }
    
    def extract_style_attributes(self, description: str, name: str = "", url: str = "") -> Dict[str, any]:
        """
        Extract style-related attributes from text using pattern matching.
        
        Args:
            description: Product description
            name: Product name
            url: Product URL (may contain color info)
            
        Returns:
            Dictionary of style attributes
        """
        # Combine all text sources
        text = f"{name} {description} {url}".lower()
        
        # Normalize text: replace hyphens with spaces for better matching
        text_normalized = text.replace('-', ' ').replace('_', ' ')
        
        attributes = {
            'colors': [],
            'materials': [],
            'patterns': [],
            'fit': None,
            'style_keywords': [],
            'occasion': []
        }
        
        # Color extraction - expanded list
        colors = [
            'black', 'white', 'navy', 'beige', 'grey', 'gray', 'brown', 'tan',
            'cream', 'ivory', 'khaki', 'olive', 'burgundy', 'maroon', 'red',
            'blue', 'green', 'yellow', 'pink', 'purple', 'orange', 'camel',
            'sand', 'stone', 'charcoal', 'midnight', 'forest', 'sage', 'rust',
            'steel-blue', 'steel blue', 'dark-brown', 'dark brown', 'light-brown',
            'light brown', 'mid-brown', 'mid brown', 'mélange', 'melange'
        ]
        for color in colors:
            # Check both original and normalized text
            if color in text or color.replace('-', ' ') in text_normalized:
                # Clean up color name
                clean_color = color.replace('-', ' ').replace('_', ' ')
                if clean_color not in attributes['colors']:
                    attributes['colors'].append(clean_color)
        
        # Material extraction - expanded list including blends
        materials = [
            'cotton', 'wool', 'cashmere', 'merino', 'linen', 'silk', 'polyester',
            'nylon', 'elastane', 'viscose', 'modal', 'lyocell', 'tencel',
            'leather', 'suede', 'denim', 'canvas', 'jersey', 'knit', 'ribbed',
            'mohair', 'alpaca', 'yak', 'angora', 'bamboo', 'hemp', 'rayon'
        ]
        for material in materials:
            # Check for material in text (including hyphenated versions)
            if material in text_normalized:
                if material not in attributes['materials']:
                    attributes['materials'].append(material)
        
        # Also check for blend patterns (e.g., "mohair-blend" -> mohair)
        blend_pattern = r'(\w+)-?blend'
        blend_matches = re.findall(blend_pattern, text_normalized)
        for match in blend_matches:
            if match in materials and match not in attributes['materials']:
                attributes['materials'].append(match)
        
        # Pattern extraction - expanded list including hyphenated patterns
        patterns = [
            'striped', 'solid', 'patterned', 'printed', 'embroidered', 'jacquard',
            'check', 'checked', 'plaid', 'paisley', 'floral', 'geometric', 'abstract',
            'plain', 'textured', 'ribbed', 'cable', 'fair isle', 'fair-isle',
            'herringbone', 'color-block', 'color block', 'space-dyed', 'space dyed',
            'degradé', 'degrade', 'gradient', 'ombre', 'tie-dye', 'tie dye'
        ]
        for pattern in patterns:
            # Check both original and normalized text
            pattern_normalized = pattern.replace('-', ' ').replace('_', ' ')
            if pattern in text or pattern_normalized in text_normalized:
                clean_pattern = pattern.replace('-', ' ').replace('_', ' ')
                if clean_pattern not in attributes['patterns']:
                    attributes['patterns'].append(clean_pattern)
        
        # Fit extraction
        fit_keywords = {
            'relaxed': ['relaxed', 'loose', 'oversized', 'roomy'],
            'fitted': ['fitted', 'tailored', 'slim', 'close-fitting'],
            'regular': ['regular', 'standard', 'classic'],
            'slim': ['slim', 'slim-fit', 'narrow']
        }
        for fit_type, keywords in fit_keywords.items():
            if any(kw in text for kw in keywords):
                attributes['fit'] = fit_type
                break
        
        # Style keywords
        style_terms = [
            'minimalist', 'classic', 'modern', 'contemporary', 'timeless',
            'versatile', 'essential', 'casual', 'formal', 'smart', 'elegant',
            'sophisticated', 'refined', 'understated', 'structured', 'unstructured',
            'soft', 'crisp', 'fluid', 'draped', 'boxy', 'cropped', 'oversized'
        ]
        for term in style_terms:
            if term in text:
                attributes['style_keywords'].append(term)
        
        # Occasion
        occasions = {
            'work': ['work', 'office', 'professional', 'business'],
            'casual': ['casual', 'everyday', 'weekend', 'relaxed'],
            'formal': ['formal', 'evening', 'dress', 'occasion'],
            'sport': ['sport', 'athletic', 'active', 'performance']
        }
        for occasion, keywords in occasions.items():
            if any(kw in text for kw in keywords):
                attributes['occasion'].append(occasion)
        
        # Remove duplicates
        for key in ['colors', 'materials', 'patterns', 'style_keywords', 'occasion']:
            attributes[key] = list(set(attributes[key]))
        
        return attributes
    
    def enrich_product(self, product: Dict) -> Dict:
        """
        Enrich a single product with embeddings and style attributes.
        
        Args:
            product: Product dictionary with name, description, primary_image, etc.
            
        Returns:
            Enriched product dictionary
        """
        enriched = product.copy()
        
        # Visual embedding from primary image
        if product.get('primary_image'):
            visual_emb = self.get_visual_embedding(product['primary_image'])
            if visual_emb is not None:
                enriched['visual_embedding'] = visual_emb.tolist()
                enriched['has_visual_embedding'] = True
            else:
                enriched['has_visual_embedding'] = False
        else:
            enriched['has_visual_embedding'] = False
        
        # Text embedding from description
        description = product.get('description', '') or ''
        # Handle NaN/None from pandas
        if pd.isna(description):
            description = ''
        if description and len(str(description).strip()) > 0:
            text_emb = self.get_text_embedding(description)
            if text_emb is not None:
                enriched['text_embedding'] = text_emb.tolist()
                enriched['has_text_embedding'] = True
            else:
                enriched['has_text_embedding'] = False
        else:
            enriched['has_text_embedding'] = False
        
        # Style attributes - combine text-based and image-based extraction
        product_name = product.get('name', '') or ''
        if pd.isna(product_name):
            product_name = ''
        product_url = product.get('url', '') or ''
        if pd.isna(product_url):
            product_url = ''
        
        # Text-based extraction
        text_attrs = self.extract_style_attributes(
            str(description),
            str(product_name),
            str(product_url)
        )
        
        # Image-based extraction (especially useful when description is missing)
        # Use lower threshold when description is empty to get more attributes from image
        image_attrs = {}
        if product.get('primary_image'):
            # CLIP similarities can be negative, so use negative threshold
            # Lower threshold (more negative) when description is missing (be more permissive)
            threshold = -0.08 if not description or len(str(description).strip()) < 10 else -0.05
            image_attrs = self.extract_style_attributes_from_image(
                product['primary_image'],
                threshold=threshold
            )
        
        # Merge attributes (image-based adds to text-based, removes duplicates)
        style_attrs = {
            'colors': list(set(text_attrs['colors'] + image_attrs.get('colors', []))),
            'materials': list(set(text_attrs['materials'] + image_attrs.get('materials', []))),
            'patterns': list(set(text_attrs['patterns'] + image_attrs.get('patterns', []))),
            'fit': text_attrs['fit'] or image_attrs.get('fit'),
            'style_keywords': list(set(text_attrs['style_keywords'] + image_attrs.get('style_keywords', []))),
            'occasion': list(set(text_attrs['occasion'] + image_attrs.get('occasion', [])))
        }
        
        # Get color matching suggestions
        color_matches = self.get_color_matches(style_attrs['colors'])
        style_attrs['color_matches'] = color_matches
        
        enriched['style_attributes'] = style_attrs
        enriched['colors'] = ', '.join(style_attrs['colors']) if style_attrs['colors'] else None
        enriched['materials'] = ', '.join(style_attrs['materials']) if style_attrs['materials'] else None
        enriched['patterns'] = ', '.join(style_attrs['patterns']) if style_attrs['patterns'] else None
        enriched['fit'] = style_attrs['fit']
        enriched['style_keywords'] = ', '.join(style_attrs['style_keywords']) if style_attrs['style_keywords'] else None
        
        # Add color matching columns
        enriched['complementary_colors'] = ', '.join(color_matches['complementary']) if color_matches['complementary'] else None
        enriched['neutral_colors'] = ', '.join(color_matches['neutral']) if color_matches['neutral'] else None
        enriched['monochrome_colors'] = ', '.join(color_matches['monochrome']) if color_matches['monochrome'] else None
        
        return enriched
    
    def enrich_dataframe(self, df: pd.DataFrame, 
                        save_embeddings_separately: bool = True,
                        output_dir: Optional[Path] = None) -> pd.DataFrame:
        """
        Enrich an entire DataFrame of products.
        
        Args:
            df: DataFrame with product data
            save_embeddings_separately: Whether to save embeddings in separate pickle file
            output_dir: Directory to save embeddings file
            
        Returns:
            Enriched DataFrame (without embedding columns if save_embeddings_separately=True)
        """
        print(f"\n{'='*60}")
        print("ENRICHING PRODUCT DATA")
        print(f"{'='*60}\n")
        print(f"Products to enrich: {len(df)}")
        if self.use_clip:
            clip_type = "Fashion CLIP" if self.use_fashion_clip else "OpenAI CLIP"
            print(f"Using {clip_type}: {self.use_clip}")
        else:
            print(f"Using CLIP: {self.use_clip}")
        print(f"Using text embeddings: {self.text_model is not None}\n")
        
        enriched_products = []
        embeddings_dict = {}
        
        for idx, row in tqdm(df.iterrows(), total=len(df), desc="Enriching"):
            product = row.to_dict()
            enriched = self.enrich_product(product)
            
            # Store embeddings separately if requested
            if save_embeddings_separately:
                product_id = f"{row.get('name', idx)}_{idx}"
                if enriched.get('visual_embedding'):
                    embeddings_dict[f"{product_id}_visual"] = enriched.pop('visual_embedding')
                if enriched.get('text_embedding'):
                    embeddings_dict[f"{product_id}_text"] = enriched.pop('text_embedding')
            
            enriched_products.append(enriched)
        
        enriched_df = pd.DataFrame(enriched_products)
        
        # Save embeddings separately if requested
        if save_embeddings_separately and embeddings_dict and output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            embeddings_file = output_dir / "embeddings.pkl"
            with open(embeddings_file, 'wb') as f:
                pickle.dump(embeddings_dict, f)
            print(f"\n✅ Saved embeddings to: {embeddings_file}")
        
        # Summary
        print(f"\n{'='*60}")
        print("ENRICHMENT SUMMARY")
        print(f"{'='*60}")
        if 'has_visual_embedding' in enriched_df.columns:
            visual_count = enriched_df['has_visual_embedding'].sum()
            print(f"Visual embeddings: {visual_count}/{len(enriched_df)} ({visual_count/len(enriched_df)*100:.1f}%)")
        if 'has_text_embedding' in enriched_df.columns:
            text_count = enriched_df['has_text_embedding'].sum()
            print(f"Text embeddings: {text_count}/{len(enriched_df)} ({text_count/len(enriched_df)*100:.1f}%)")
        if 'style_attributes' in enriched_df.columns:
            has_style = enriched_df['style_attributes'].notna()
            print(f"Style attributes: {has_style.sum()}/{len(enriched_df)} ({has_style.sum()/len(enriched_df)*100:.1f}%)")
        
        return enriched_df


def load_embeddings(embeddings_file: Path) -> Dict:
    """Load embeddings from pickle file."""
    with open(embeddings_file, 'rb') as f:
        return pickle.load(f)


def find_similar_products(query_text: str, 
                         enricher: StyleEnricher,
                         products_df: pd.DataFrame,
                         embeddings_dict: Dict,
                         top_k: int = 5,
                         use_visual: bool = False) -> pd.DataFrame:
    """
    Find similar products using text or visual similarity.
    
    Args:
        query_text: Query text (e.g., "minimalist black sweater")
        enricher: StyleEnricher instance
        products_df: DataFrame with product data
        embeddings_dict: Dictionary of embeddings (from load_embeddings)
        top_k: Number of results to return
        use_visual: Whether to use visual embeddings (requires query image)
        
    Returns:
        DataFrame with top_k similar products
    """
    # Encode query
    if use_visual:
        # Would need query image URL
        query_emb = None  # TODO: implement visual query
    else:
        query_emb = enricher.get_text_embedding(query_text)
    
    if query_emb is None:
        return pd.DataFrame()
    
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
            similarities.append((idx, similarity))
    
    # Sort by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    # Get top_k products
    top_indices = [idx for idx, _ in similarities[:top_k]]
    return products_df.iloc[top_indices].copy()


def main():
    """Main function to enrich scraped data."""
    from pathlib import Path
    
    data_dir = Path("data")
    processed_dir = data_dir / "processed"
    
    # Find CSV files
    csv_files = list(processed_dir.glob("*.csv"))
    
    if not csv_files:
        print("❌ No CSV files found in data/processed/")
        print("   Run the scraper first to generate data.")
        return
    
    print(f"Found {len(csv_files)} CSV file(s):")
    for f in csv_files:
        print(f"  - {f.name}")
    
    # Use first CSV (or let user choose)
    input_file = csv_files[0]
    print(f"\n📂 Processing: {input_file.name}\n")
    
    # Load data
    df = pd.read_csv(input_file)
    print(f"Loaded {len(df)} products")
    
    # Initialize enricher (uses Fashion CLIP by default)
    enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)
    
    # Enrich
    enriched_df = enricher.enrich_dataframe(
        df,
        save_embeddings_separately=True,
        output_dir=processed_dir
    )
    
    # Save enriched data
    output_file = processed_dir / f"enriched_{input_file.stem}.csv"
    # Remove embedding columns for CSV (they're saved separately)
    cols_to_save = [c for c in enriched_df.columns if 'embedding' not in c.lower()]
    enriched_df[cols_to_save].to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✅ Saved enriched data to: {output_file}")
    
    # Also save JSON with all data
    json_file = processed_dir / f"enriched_{input_file.stem}.json"
    enriched_df[cols_to_save].to_json(json_file, orient='records', indent=2)
    print(f"✅ Saved JSON to: {json_file}")


if __name__ == "__main__":
    main()

