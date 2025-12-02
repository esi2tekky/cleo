#!/usr/bin/env python3
"""
Advanced query parser for situational queries.
Extracts product type, weather, season, location, occasion from natural language queries.
"""
import re
from typing import Dict, Optional, List

class QueryParser:
    """Parse natural language queries to extract contextual components."""
    
    # Weather conditions and their style implications
    WEATHER_STYLES = {
        "cool": ["layered", "warm", "cozy", "comfortable", "moderate"],
        "warm": ["lightweight", "breathable", "airy", "summer", "comfortable"],
        "cold": ["insulated", "warm", "thick", "winter", "cozy", "layered"],
        "hot": ["lightweight", "breathable", "cool", "summer", "airy"],
        "mild": ["versatile", "comfortable", "moderate", "layered"],
        "chilly": ["warm", "cozy", "layered", "comfortable"],
        "freezing": ["insulated", "warm", "thick", "winter", "cozy"],
    }
    
    # Location styles
    LOCATION_STYLES = {
        "paris": ["elegant", "sophisticated", "classic", "chic", "refined", "timeless"],
        "california": ["casual", "relaxed", "beach", "laid-back", "comfortable", "easy"],
        "new york": ["urban", "modern", "sleek", "polished", "sophisticated"],
        "london": ["classic", "tailored", "sophisticated", "refined", "polished"],
        "los angeles": ["casual", "relaxed", "stylish", "modern", "laid-back"],
        "miami": ["casual", "beach", "tropical", "relaxed", "colorful"],
        "tokyo": ["modern", "sleek", "minimalist", "sophisticated"],
    }
    
    # Occasion styles
    OCCASION_STYLES = {
        "night out": ["dressy", "elegant", "stylish", "evening", "sophisticated", "chic"],
        "night in paris": ["elegant", "sophisticated", "refined", "classic", "timeless", "dressy", "evening", "chic", "polished"],
        "casual day": ["comfortable", "relaxed", "casual", "everyday", "versatile", "easy"],
        "office": ["professional", "polished", "tailored", "smart", "business", "formal", "corporate"],
        "weekend": ["casual", "relaxed", "comfortable", "easy", "laid-back"],
        "date night": ["elegant", "romantic", "dressy", "sophisticated", "chic", "refined"],
        "beach": ["lightweight", "breathable", "summer", "casual", "relaxed", "comfortable"],
        "formal event": ["formal", "elegant", "sophisticated", "polished", "refined", "dressy"],
    }
    
    # Season styles
    SEASON_STYLES = {
        "winter": ["warm", "cozy", "insulated", "layered", "thick", "comfortable"],
        "summer": ["lightweight", "breathable", "airy", "cool", "comfortable"],
        "spring": ["versatile", "lightweight", "comfortable", "moderate"],
        "fall": ["layered", "warm", "cozy", "comfortable", "versatile"],
        "autumn": ["layered", "warm", "cozy", "comfortable", "versatile"],
    }
    
    # Product types
    PRODUCT_TYPES = {
        "sweater": ["sweater", "sweaters", "jumper", "jumpers"],
        "cardigan": ["cardigan", "cardigans"],
        "hoodie": ["hoodie", "hoodies"],
        "shirt": ["shirt", "shirts", "blouse", "blouses"],
        "pants": ["pants", "trousers", "trouser"],
        "jacket": ["jacket", "jackets", "coat", "coats"],
        "dress": ["dress", "dresses"],
        "top": ["top", "tops"],
        "polo": ["polo", "polos"],
        "t-shirt": ["t-shirt", "t shirt", "tshirt", "tee", "tees"],
    }
    
    def parse_situational_query(self, query: str) -> Dict:
        """
        Parse query to extract structured components.
        
        Args:
            query: Natural language query
            
        Returns:
            Dictionary with extracted components:
            - product_type: str or None
            - weather: str or None
            - season: str or None
            - location: str or None
            - occasion: str or None
            - time: str or None
            - style_keywords: List[str]
        """
        query_lower = query.lower()
        
        result = {
            "product_type": None,
            "weather": None,
            "season": None,
            "location": None,
            "occasion": None,
            "time": None,
            "gender": None,
            "style_keywords": []
        }
        
        # Extract product type
        result["product_type"] = self.extract_product_type(query_lower)
        
        # Extract gender
        result["gender"] = self.extract_gender_context(query_lower)
        
        # Extract weather
        result["weather"] = self.extract_weather_context(query_lower)
        
        # Extract season
        result["season"] = self.extract_season_context(query_lower)
        
        # Extract location
        result["location"] = self.extract_location_context(query_lower)
        
        # Extract occasion
        result["occasion"] = self.extract_occasion_context(query_lower)
        
        # Extract time of day
        result["time"] = self.extract_time_context(query_lower)
        
        # Combine style keywords from all contexts
        result["style_keywords"] = self.combine_contexts(
            result["weather"],
            result["location"],
            result["occasion"],
            result["season"]
        )
        
        return result
    
    def extract_product_type(self, query: str) -> Optional[str]:
        """Extract product type from query."""
        for product_type, keywords in self.PRODUCT_TYPES.items():
            for keyword in keywords:
                if keyword in query:
                    return product_type
        return None
    
    def extract_weather_context(self, query: str) -> Optional[str]:
        """Extract weather condition from query."""
        weather_keywords = ["cool", "warm", "cold", "hot", "mild", "chilly", "freezing"]
        for weather in weather_keywords:
            if weather in query:
                return weather
        return None
    
    def extract_season_context(self, query: str) -> Optional[str]:
        """Extract season from query."""
        seasons = ["winter", "summer", "spring", "fall", "autumn"]
        for season in seasons:
            if season in query:
                return season
        return None
    
    def extract_location_context(self, query: str) -> Optional[str]:
        """Extract location from query."""
        locations = list(self.LOCATION_STYLES.keys())
        # Sort by length (longest first) to match "new york" before "york"
        locations_sorted = sorted(locations, key=len, reverse=True)
        for location in locations_sorted:
            if location in query:
                return location
        return None
    
    def extract_occasion_context(self, query: str) -> Optional[str]:
        """Extract occasion from query."""
        occasions = list(self.OCCASION_STYLES.keys())
        # Sort by length (longest first) to match "night in paris" before "night"
        occasions_sorted = sorted(occasions, key=len, reverse=True)
        for occasion in occasions_sorted:
            if occasion in query:
                return occasion
        return None
    
    def extract_time_context(self, query: str) -> Optional[str]:
        """Extract time of day from query."""
        time_keywords = ["night", "evening", "day", "morning", "afternoon"]
        for time_word in time_keywords:
            if time_word in query:
                return time_word
        return None
    
    def extract_gender_context(self, query: str) -> Optional[str]:
        """
        Extract gender context from query.
        
        Args:
            query: Lowercase query text
            
        Returns:
            "men" or "women" or None
        """
        # Patterns for men
        men_patterns = [
            r'\bfor\s+men\b',
            r'\bmen\'?s\b',
            r'\bmens\b',
            r'\bmale\b',
            r'\bmenswear\b',
        ]
        
        # Patterns for women
        women_patterns = [
            r'\bfor\s+women\b',
            r'\bwomen\'?s\b',
            r'\bwomens\b',
            r'\bfemale\b',
            r'\bwomenswear\b',
        ]
        
        # Check for men patterns first
        for pattern in men_patterns:
            if re.search(pattern, query):
                return "men"
        
        # Check for women patterns
        for pattern in women_patterns:
            if re.search(pattern, query):
                return "women"
        
        return None
    
    def combine_contexts(self, weather: Optional[str], location: Optional[str], 
                        occasion: Optional[str], season: Optional[str]) -> List[str]:
        """
        Combine style keywords from all contexts.
        
        Args:
            weather: Weather condition
            location: Location name
            occasion: Occasion type
            season: Season name
            
        Returns:
            Combined list of style keywords
        """
        keywords = []
        
        if weather and weather in self.WEATHER_STYLES:
            keywords.extend(self.WEATHER_STYLES[weather])
        
        if location and location in self.LOCATION_STYLES:
            keywords.extend(self.LOCATION_STYLES[location])
        
        if occasion and occasion in self.OCCASION_STYLES:
            keywords.extend(self.OCCASION_STYLES[occasion])
        
        if season and season in self.SEASON_STYLES:
            keywords.extend(self.SEASON_STYLES[season])
        
        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)
        
        return unique_keywords
    
    def build_enhanced_query(self, query: str, components: Dict) -> str:
        """
        Build enhanced query with all contextual information.
        
        Args:
            query: Original query
            components: Parsed components from parse_situational_query
            
        Returns:
            Enhanced query string with style keywords
        """
        parts = [query]
        
        if components.get("style_keywords"):
            style_text = " ".join(components["style_keywords"][:10])  # Limit to 10 keywords
            parts.append(style_text)
        
        return " ".join(parts).strip()
    
    def detect_product_reference(self, query: str, tagged_products: List[Dict] = None) -> Optional[Dict]:
        """
        Detect if query references a product (tagged product, pronoun, or named product).
        
        Args:
            query: User query text
            tagged_products: List of tagged products from conversation
            
        Returns:
            Dict with referenced_product and reference_type, or None
        """
        query_lower = query.lower()
        tagged_products = tagged_products or []
        
        # Check for @ symbol that references tagged products
        if '@' in query:
            if tagged_products:
                return {
                    'referenced_product': tagged_products[0],  # Most recently tagged product
                    'reference_type': 'tagged'
                }
        
        # Check for pronouns that reference products
        pronoun_patterns = [
            r'\b(it|this|that|this one|that one)\b',
            r'\b(the|this|that)\s+(\w+)',  # "the sweater", "this jacket"
        ]
        
        for pattern in pronoun_patterns:
            if re.search(pattern, query_lower):
                # If we have tagged products, return most recent
                if tagged_products:
                    return {
                        'referenced_product': tagged_products[0],
                        'reference_type': 'tagged'
                    }
                # Otherwise, try to extract product type from query
                product_type = self.extract_product_type(query_lower)
                if product_type:
                    return {
                        'referenced_product': {'product_type': product_type},
                        'reference_type': 'pronoun'
                    }
        
        # Check if query mentions a tagged product by name
        if tagged_products:
            for tagged_product in tagged_products:
                product_name = tagged_product.get('name', '').lower()
                if product_name and product_name in query_lower:
                    return {
                        'referenced_product': tagged_product,
                        'reference_type': 'named'
                    }
        
        return None
    
    def detect_query_intent(self, query: str, last_context: Optional[Dict] = None) -> Dict:
        """
        Detect the intent of a query (correction, refinement, narrowing, augment, switch, new).
        
        Args:
            query: Current query text
            last_context: Previous query context (if available)
            
        Returns:
            Dict with intent type and confidence
        """
        query_lower = query.lower()
        result = {
            'intent': 'new',
            'confidence': 0.0
        }
        
        if not last_context:
            return result
        
        # Correction patterns (highest priority)
        correction_patterns = [
            r'\bi\s+said\s+',
            r'\bi\s+meant\s+',
            r'\bcorrection',
            r'\bactually',
            r'\bi\s+meant\s+to\s+say',
        ]
        for pattern in correction_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'correction'
                result['confidence'] = 0.9
                return result
        
        # Refinement patterns (improved for gender/attribute changes)
        refinement_patterns = [
            r'\bmake\s+it\s+',
            r'\bchange\s+it\s+to',
            r'\bswitch\s+to',
            r'\binstead',
            r'\bfor\s+men\b',  # "for men" as refinement when previous query had different gender
            r'\bfor\s+women\b',  # "for women" as refinement
        ]
        for pattern in refinement_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'refinement'
                result['confidence'] = 0.8
                return result
        
        # Narrowing patterns
        narrowing_patterns = [
            r'\bonly\s+',
            r'\bjust\s+',
            r'\bspecifically\s+',
            r'\bnarrow\s+down',
        ]
        for pattern in narrowing_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'narrowing'
                result['confidence'] = 0.7
                return result
        
        # Switch patterns (explicit context switch)
        switch_patterns = [
            r'\bhow\s+about\b',  # "how about beach"
            r'\bwhat\s+about\b',  # "what about beach"
            r'\bhow\s+about\s+for\b',
            r'\binstead\s+of\b',
        ]
        for pattern in switch_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'switch'
                result['confidence'] = 0.8
                return result
                
        # Augment patterns (adding to context)
        augment_patterns = [
            r'\band\s+',
            r'\balso\s+',
            r'\bplus\s+',
            r'\badd\s+',
            r'\bwith\s+',
        ]
        for pattern in augment_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'augment'
                result['confidence'] = 0.7
                return result

        # Check for implicit switch via situational keywords (e.g., "a beach day")
        # If the query contains a new occasion, location, weather, or season, treat as switch
        current_parsed = self.parse_situational_query(query)
        if current_parsed['occasion'] or current_parsed['location'] or current_parsed['weather'] or current_parsed['season']:
            # If we found situational context but no explicit connecting words, it's likely a switch/override
            result['intent'] = 'switch'
            result['confidence'] = 0.75
            return result
        
        return result
    
    def merge_query_context(self, current_query: str, last_context: Dict, intent: str) -> Dict:
        """
        Merge current query with last query context based on intent.
        
        Args:
            current_query: Current user query
            last_context: Previous query context
            intent: Query intent ('correction', 'refinement', 'narrowing', 'augment', 'switch', 'new')
            
        Returns:
            Merged context dict with query_text, parsed_components, applied_filters
        """
        merged = {
            'query_text': current_query,
            'parsed_components': last_context.get('parsed_components', {}).copy(),
            'applied_filters': last_context.get('applied_filters', {}).copy()
        }
        
        # Parse current query
        current_parsed = self.parse_situational_query(current_query)
        
        if intent == 'correction':
            # Replace conflicting filters, keep others
            if current_parsed.get('gender'):
                merged['parsed_components']['gender'] = current_parsed['gender']
                merged['applied_filters']['gender'] = current_parsed['gender']
            if current_parsed.get('product_type'):
                merged['parsed_components']['product_type'] = current_parsed['product_type']
                merged['applied_filters']['product_type'] = current_parsed['product_type']
            # Keep other filters from last context
        
        elif intent == 'refinement':
            # Add/modify filters without removing others
            if current_parsed.get('gender'):
                merged['parsed_components']['gender'] = current_parsed['gender']
                merged['applied_filters']['gender'] = current_parsed['gender']
            if current_parsed.get('product_type'):
                merged['parsed_components']['product_type'] = current_parsed['product_type']
                merged['applied_filters']['product_type'] = current_parsed['product_type']
        
        elif intent == 'narrowing':
            # Add stricter filters
            if current_parsed.get('product_type'):
                merged['parsed_components']['product_type'] = current_parsed['product_type']
                merged['applied_filters']['product_type'] = current_parsed['product_type']
        
        elif intent == 'switch':
            # Override situational context (weather, season, location, occasion, time)
            # But preserve gender and product_type unless specified in new query
            
            # Clear previous situational fields
            for field in ['weather', 'season', 'location', 'occasion', 'time']:
                merged['parsed_components'][field] = None
                merged['applied_filters'][field] = None
            
            # Clear previous style keywords as they are derived from situation
            merged['parsed_components']['style_keywords'] = []
            merged['applied_filters']['style_keywords'] = []
            
            # Update with new context
            if current_parsed.get('gender'):
                merged['parsed_components']['gender'] = current_parsed['gender']
                merged['applied_filters']['gender'] = current_parsed['gender']
            
            if current_parsed.get('product_type'):
                merged['parsed_components']['product_type'] = current_parsed['product_type']
                merged['applied_filters']['product_type'] = current_parsed['product_type']
            
        elif intent == 'augment':
            # Add to context without clearing (e.g., "and a hat", "and red")
            if current_parsed.get('gender'):
                merged['parsed_components']['gender'] = current_parsed['gender']
                merged['applied_filters']['gender'] = current_parsed['gender']
            
            # If product type is specified, it might override or add. 
            # Usually "and a hat" means look for hats IN ADDITION to previous items? 
            # Or switch focus to hats within same context?
            # For search simplicity, we usually switch the target product type but keep the style context.
            if current_parsed.get('product_type'):
                merged['parsed_components']['product_type'] = current_parsed['product_type']
                merged['applied_filters']['product_type'] = current_parsed['product_type']

        # For all intents (including continuation/augment/switch/refinement), 
        # update situational fields from current query
        for field in ['weather', 'season', 'location', 'occasion', 'time']:
            if current_parsed.get(field):
                merged['parsed_components'][field] = current_parsed[field]
                merged['applied_filters'][field] = current_parsed[field]
                
        # Always update with current parsed components that aren't already set (filling gaps)
        for key, value in current_parsed.items():
            if key not in merged['parsed_components'] or merged['parsed_components'][key] is None:
                merged['parsed_components'][key] = value

        # REGENERATE style keywords from the final merged situational context
        # This ensures keywords match the new situation (e.g. if switched from Winter to Beach)
        merged['parsed_components']['style_keywords'] = self.combine_contexts(
            merged['parsed_components'].get('weather'),
            merged['parsed_components'].get('location'),
            merged['parsed_components'].get('occasion'),
            merged['parsed_components'].get('season')
        )
        merged['applied_filters']['style_keywords'] = merged['parsed_components']['style_keywords']
        
        return merged
    
    def classify_product_query_intent(self, query: str, has_product_reference: bool = False) -> Dict:
        """
        Classify the intent of a product-related query.
        
        Args:
            query: User query text
            has_product_reference: Whether query references a specific product
            
        Returns:
            Dict with intent type and extracted criteria
        """
        query_lower = query.lower()
        result = {
            'intent': None,
            'criteria': {}
        }
        
        if not has_product_reference:
            return result
        
        # Variants intent patterns
        variant_patterns = [
            r'another\s+color',
            r'different\s+color',
            r'other\s+color',
            r'variants?',
            r'alternatives?',
            r'other\s+options?',
            r'available\s+in',
        ]
        for pattern in variant_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'variants'
                # Extract variant criteria
                if 'color' in query_lower:
                    result['criteria']['variant_type'] = 'color'
                elif 'size' in query_lower:
                    result['criteria']['variant_type'] = 'size'
                elif 'material' in query_lower or 'fabric' in query_lower:
                    result['criteria']['variant_type'] = 'material'
                break
        
        # Similar intent patterns
        similar_patterns = [
            r'similar',
            r'like\s+this',
            r'same\s+style',
            r'comparable',
            r'equivalent',
            r'more\s+like',
        ]
        for pattern in similar_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'similar'
                # Extract product type if specified
                product_type = self.extract_product_type(query_lower)
                if product_type:
                    result['criteria']['product_type'] = product_type
                break
        
        # Compatibility intent patterns
        compatibility_patterns = [
            r'goes\s+with',
            r'matches',
            r'pairs?\s+with',
            r'compatible\s+with',
            r'that\s+could\s+go\s+with',
            r'what\s+goes\s+with',
        ]
        for pattern in compatibility_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'compatibility'
                # Extract product type for compatible items
                product_type = self.extract_product_type(query_lower)
                if product_type:
                    result['criteria']['compatible_type'] = product_type
                break
        
        # Details intent patterns
        details_patterns = [
            r'tell\s+me\s+about',
            r'what\s+is',
            r'describe',
            r'info\s+about',
        ]
        for pattern in details_patterns:
            if re.search(pattern, query_lower):
                result['intent'] = 'details'
                break
        
        return result

