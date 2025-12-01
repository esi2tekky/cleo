#!/usr/bin/env python3
"""
Conversation memory management for chat history.
Stores conversation context to enable follow-up queries.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

class ConversationManager:
    """Manages conversation history for chat sessions."""
    
    def __init__(self, ttl_hours: int = 24, max_messages: int = 50):
        """
        Initialize conversation manager with enhanced memory.
        
        Args:
            ttl_hours: Time-to-live for conversations (hours)
            max_messages: Maximum messages per conversation
        """
        self.conversations = defaultdict(list)  # {session_id: [messages]}
        self.session_timestamps = {}  # {session_id: last_activity}
        self.tagged_products = defaultdict(list)  # {session_id: [products]}
        self.user_preferences = defaultdict(dict)  # {session_id: {preferences}}
        self.ttl = timedelta(hours=ttl_hours)
        self.max_messages = max_messages
    
    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None):
        """
        Add message to conversation history.
        
        Args:
            session_id: Unique session identifier
            role: 'user' or 'assistant'
            content: Message content
            metadata: Optional metadata (e.g., query results count)
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.conversations[session_id].append(message)
        self.session_timestamps[session_id] = datetime.now()
        
        # Trim old messages if exceeds max
        if len(self.conversations[session_id]) > self.max_messages:
            self.conversations[session_id] = self.conversations[session_id][-self.max_messages:]
    
    def get_context(self, session_id: str, max_messages: int = 10) -> str:
        """
        Get recent conversation history as context string.
        
        Args:
            session_id: Session identifier
            max_messages: Maximum messages to include
            
        Returns:
            Formatted context string
        """
        if session_id not in self.conversations:
            return ""
        
        messages = self.conversations[session_id][-max_messages:]
        context_lines = []
        for msg in messages:
            role = msg['role'].capitalize()
            content = msg['content']
            context_lines.append(f"{role}: {content}")
        
        return "\n".join(context_lines)
    
    def get_recent_queries(self, session_id: str, n: int = 3) -> List[str]:
        """Get recent user queries for context."""
        if session_id not in self.conversations:
            return []
        
        user_messages = [
            msg['content'] 
            for msg in self.conversations[session_id] 
            if msg['role'] == 'user'
        ]
        return user_messages[-n:]
    
    def clear_session(self, session_id: str):
        """Clear conversation history for a session."""
        if session_id in self.conversations:
            del self.conversations[session_id]
        if session_id in self.session_timestamps:
            del self.session_timestamps[session_id]
        if session_id in self.tagged_products:
            del self.tagged_products[session_id]
        if session_id in self.user_preferences:
            del self.user_preferences[session_id]
    
    def cleanup_expired(self):
        """Remove expired conversations."""
        now = datetime.now()
        expired_sessions = [
            sid for sid, timestamp in self.session_timestamps.items()
            if now - timestamp > self.ttl
        ]
        for sid in expired_sessions:
            self.clear_session(sid)
    
    def get_session_summary(self, session_id: str) -> Dict:
        """Get summary of conversation session."""
        if session_id not in self.conversations:
            return {"message_count": 0, "last_activity": None}
        
        return {
            "message_count": len(self.conversations[session_id]),
            "last_activity": self.session_timestamps.get(session_id),
            "recent_queries": self.get_recent_queries(session_id, n=5)
        }
    
    def is_correction_query(self, query: str) -> bool:
        """
        Detect if query is a correction/refinement.
        
        Args:
            query: User query text
            
        Returns:
            True if correction detected
        """
        query_lower = query.lower()
        correction_patterns = [
            'i said',
            'i meant',
            'correction',
            'actually',
            'i meant to say',
            'i want',
            'make it',
            'change it to',
            'switch to',
            'instead'
        ]
        return any(pattern in query_lower for pattern in correction_patterns)
    
    def get_last_query_context(self, session_id: str) -> Optional[Dict]:
        """
        Get last user query context with parsed components and filters.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dict with query_text, parsed_components, applied_filters, results_count
            or None if no previous query
        """
        if session_id not in self.conversations:
            return None
        
        # Find last user message with metadata
        messages = self.conversations[session_id]
        for msg in reversed(messages):
            if msg['role'] == 'user':
                metadata = msg.get('metadata', {})
                return {
                    'query_text': msg['content'],
                    'parsed_components': metadata.get('parsed_components', {}),
                    'applied_filters': metadata.get('applied_filters', {}),
                    'results_count': metadata.get('result_count', 0),
                    'timestamp': msg.get('timestamp')
                }
        
        return None
    
    def add_tagged_product(self, session_id: str, product_data: Dict):
        """
        Add a tagged product to the session.
        
        Args:
            session_id: Session identifier
            product_data: Product data dict with index, name, category, etc.
        """
        # Remove existing product with same index if present
        self.tagged_products[session_id] = [
            p for p in self.tagged_products[session_id] 
            if p.get('index') != product_data.get('index')
        ]
        # Add new tagged product
        self.tagged_products[session_id].append(product_data)
        self.session_timestamps[session_id] = datetime.now()
    
    def get_tagged_products(self, session_id: str) -> List[Dict]:
        """
        Get all tagged products for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of tagged product dictionaries, most recent first
        """
        if session_id not in self.tagged_products:
            return []
        # Return most recent first
        return sorted(
            self.tagged_products[session_id],
            key=lambda p: p.get('timestamp', 0),
            reverse=True
        )
    
    def get_most_recent_tagged_product(self, session_id: str) -> Optional[Dict]:
        """
        Get the most recently tagged product for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Most recent tagged product or None
        """
        tagged = self.get_tagged_products(session_id)
        return tagged[0] if tagged else None
    
    def clear_tagged_products(self, session_id: str):
        """Clear all tagged products for a session."""
        if session_id in self.tagged_products:
            del self.tagged_products[session_id]
    
    def update_user_preferences(self, session_id: str, preferences: Dict):
        """
        Update user preferences based on interaction patterns.
        
        Args:
            session_id: Session identifier
            preferences: Dictionary of preferences to update
        """
        self.user_preferences[session_id].update(preferences)
        self.session_timestamps[session_id] = datetime.now()
    
    def get_user_preferences(self, session_id: str) -> Dict:
        """
        Get user preferences for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary of user preferences
        """
        return self.user_preferences.get(session_id, {})
    
    def infer_preferences_from_history(self, session_id: str) -> Dict:
        """
        Infer user preferences from conversation history and tagged products.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary of inferred preferences
        """
        preferences = {}
        
        # Analyze tagged products for patterns
        tagged = self.get_tagged_products(session_id)
        if tagged:
            # Color preferences
            colors = []
            materials = []
            categories = []
            price_ranges = []
            
            for product in tagged:
                if 'colors' in product:
                    colors.extend(product['colors'].split(',') if isinstance(product['colors'], str) else [])
                if 'materials' in product:
                    materials.extend(product['materials'].split(',') if isinstance(product['materials'], str) else [])
                if 'category' in product:
                    categories.append(product['category'])
                if 'price' in product:
                    try:
                        price_ranges.append(int(product['price']))
                    except (ValueError, TypeError):
                        pass
            
            # Find most common preferences
            if colors:
                from collections import Counter
                color_counts = Counter(c.strip().lower() for c in colors if c.strip())
                preferences['favorite_colors'] = [color for color, _ in color_counts.most_common(3)]
            
            if materials:
                material_counts = Counter(m.strip().lower() for m in materials if m.strip())
                preferences['preferred_materials'] = [mat for mat, _ in material_counts.most_common(2)]
            
            if categories:
                category_counts = Counter(categories)
                preferences['preferred_categories'] = [cat for cat, _ in category_counts.most_common(2)]
            
            if price_ranges:
                preferences['avg_price_range'] = sum(price_ranges) // len(price_ranges)
                preferences['max_price'] = max(price_ranges)
                preferences['min_price'] = min(price_ranges)
        
        # Analyze query history for patterns
        messages = self.conversations.get(session_id, [])
        query_keywords = []
        for msg in messages:
            if msg['role'] == 'user':
                # Extract keywords from queries
                content = msg['content'].lower()
                # Look for style keywords
                style_words = ['minimalist', 'classic', 'modern', 'casual', 'formal', 'elegant']
                for style in style_words:
                    if style in content:
                        query_keywords.append(style)
        
        if query_keywords:
            from collections import Counter
            style_counts = Counter(query_keywords)
            preferences['style_preferences'] = [style for style, _ in style_counts.most_common(2)]
        
        return preferences

