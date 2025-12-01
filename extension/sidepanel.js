// Chrome Extension Side Panel - Shopping Assistant Chat

const API_BASE_URL = 'http://localhost:5001/api';

// Generate or retrieve session ID
let sessionId = localStorage.getItem('cleo_session_id');
if (!sessionId) {
    sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('cleo_session_id', sessionId);
}

// Store image embedding if uploaded
let currentImageEmbedding = null;

// Tagged products state management
let taggedProducts = [];
const TAGGED_PRODUCTS_KEY = 'cleo_tagged_products';

// Gender preference state management
let selectedGender = localStorage.getItem('cleo_gender_preference') || 'all';
const GENDER_PREFERENCE_KEY = 'cleo_gender_preference';

// Load tagged products from localStorage
function loadTaggedProducts() {
    const stored = localStorage.getItem(TAGGED_PRODUCTS_KEY);
    if (stored) {
        try {
            taggedProducts = JSON.parse(stored);
        } catch (e) {
            taggedProducts = [];
        }
    }
}

// Save tagged products to localStorage
function saveTaggedProducts() {
    localStorage.setItem(TAGGED_PRODUCTS_KEY, JSON.stringify(taggedProducts));
}

// Initialize tagged products on load
loadTaggedProducts();

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const queryInput = document.getElementById('query-input');
    const sendButton = document.getElementById('send-button');
    const messagesContainer = document.getElementById('messages');
    const loadingIndicator = document.getElementById('loading');
    const imageInput = document.getElementById('image-input');
    const imagePreview = document.getElementById('image-preview');
    const imageUploadBtn = document.getElementById('image-upload-btn');
    
    // Gender toggle buttons
    const genderMenBtn = document.getElementById('gender-men');
    const genderWomenBtn = document.getElementById('gender-women');
    const genderAllBtn = document.getElementById('gender-all');
    
    // Setup gender toggle
    function updateGenderToggle(gender) {
        selectedGender = gender;
        localStorage.setItem(GENDER_PREFERENCE_KEY, gender);
        
        // Update button states (support both old and new class names)
        if (genderMenBtn && genderWomenBtn && genderAllBtn) {
            genderMenBtn.classList.remove('active');
            genderWomenBtn.classList.remove('active');
            genderAllBtn.classList.remove('active');
            
            if (gender === 'men') {
                genderMenBtn.classList.add('active');
            } else if (gender === 'women') {
                genderWomenBtn.classList.add('active');
            } else {
                genderAllBtn.classList.add('active');
            }
        }
    }
    
    // Initialize gender toggle state
    updateGenderToggle(selectedGender);
    
    // Gender toggle click handlers
    genderMenBtn.addEventListener('click', () => updateGenderToggle('men'));
    genderWomenBtn.addEventListener('click', () => updateGenderToggle('women'));
    genderAllBtn.addEventListener('click', () => updateGenderToggle('all'));
    
    // Setup suggestion chip click handlers
    const suggestionChips = document.querySelectorAll('.chip[data-suggestion]');
    suggestionChips.forEach(chip => {
        chip.addEventListener('click', function() {
            const suggestion = this.getAttribute('data-suggestion');
            if (suggestion && queryInput && sendButton) {
                queryInput.value = suggestion;
                sendButton.click();
            }
        });
    });
    
    // Clear image button handler
    const clearImageBtn = document.getElementById('clear-image');
    if (clearImageBtn) {
        clearImageBtn.addEventListener('click', () => {
            currentImageEmbedding = null;
            const previewContainer = document.getElementById('image-preview-container');
            if (previewContainer) {
                previewContainer.style.display = 'none';
            }
            if (imagePreview) {
                imagePreview.src = '';
            }
            const sendBtn = document.querySelector('.send-button-modern');
            if (sendBtn) {
                sendBtn.classList.remove('has-image');
                sendBtn.title = 'Send';
            }
            addMessage('Image removed.', 'bot');
        });
    }
    
    // Setup image upload (if elements exist)
    if (imageInput && imageUploadBtn) {
        imageUploadBtn.addEventListener('click', () => {
            imageInput.click();
        });
        
        imageInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            // Validate image
            if (!file.type.startsWith('image/')) {
                addMessage('Please upload an image file.', 'bot');
                return;
            }
            
            // Show preview
            const reader = new FileReader();
            reader.onload = (event) => {
                if (imagePreview) {
                    imagePreview.src = event.target.result;
                    const previewContainer = document.getElementById('image-preview-container');
                    if (previewContainer) {
                        previewContainer.style.display = 'block';
                    }
                }
            };
            reader.readAsDataURL(file);
            
            // Show loading state with typing indicator
            showTypingIndicator();
            
            // Convert to base64 and send to backend
            const base64 = await fileToBase64(file);
            
            try {
                const response = await fetch(`${API_BASE_URL}/upload-image`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        image: base64,
                        session_id: sessionId
                    })
                });
                
                const data = await response.json();
                if (data.status === 'success') {
                    currentImageEmbedding = data.embedding;
                    // Hide typing indicator and add success message
                    hideTypingIndicator();
                    addMessage('✅ Image ready! Type a description or press Send to find similar items.', 'bot');
                    
                    // Add visual indicator to send button
                    const sendBtn = document.querySelector('.send-button-modern');
                    if (sendBtn) {
                        sendBtn.classList.add('has-image');
                        sendBtn.title = 'Send with image';
                    }
                } else {
                    throw new Error(data.error || 'Upload failed');
                }
            } catch (error) {
                console.error('Image upload error:', error);
                // Hide typing indicator
                hideTypingIndicator();
                addMessage('❌ Failed to process image. Please try again.', 'bot');
                // Hide preview on error
                const previewContainer = document.getElementById('image-preview-container');
                if (previewContainer) {
                    previewContainer.style.display = 'none';
                }
                if (imagePreview) {
                    imagePreview.src = '';
                }
            }
        });
    }
    
    function fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    // Send message on button click
    sendButton.addEventListener('click', handleSend);
    
    // Send message on Enter key
    queryInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleSend();
        }
    });

    async function handleSend() {
        const query = queryInput.value.trim();
        const hasImage = currentImageEmbedding !== null;
        const imagePreview = document.getElementById('image-preview');
        
        if (!query && !hasImage) return;

        // Check if query references a tagged product
        function hasTaggedProductReference(queryText, taggedProductsList) {
            if (!queryText || !taggedProductsList || taggedProductsList.length === 0) {
                return false;
            }
            const queryLower = queryText.toLowerCase();
            
            // Check for @ symbol in query
            if (queryText.includes('@')) {
                return true;
            }
            
            // Check for pronouns that reference products
            const pronounPatterns = ['this', 'it', 'that', 'this one', 'that one'];
            if (pronounPatterns.some(pronoun => queryLower.includes(pronoun))) {
                return true;
            }
            // Check if query mentions a tagged product by name
            for (const taggedProduct of taggedProductsList) {
                const productName = (taggedProduct.name || '').toLowerCase();
                if (productName && queryLower.includes(productName)) {
                    return true;
                }
            }
            return false;
        }
        
        const hasTaggedReference = hasTaggedProductReference(query, taggedProducts);
        // Clean @ symbol from display query while keeping it for processing
        const displayQuery = query.replace(/\s*@\s*/g, ' ').trim();

        // Add user message to chat with image indicator if present
        if (displayQuery || hasImage) {
            const messageText = hasImage ? `${displayQuery || 'Image search'} 📷` : displayQuery;
            addMessage(messageText, 'user');
        }
        
        // Clear input and reset image
        queryInput.value = '';
        if (hasImage) {
            const previewContainer = document.getElementById('image-preview-container');
            if (previewContainer) {
                previewContainer.style.display = 'none';
            }
            if (imagePreview) {
                imagePreview.src = '';
            }
            // Remove visual indicator from send button
            const sendBtn = document.querySelector('.send-button-modern');
            if (sendBtn) {
                sendBtn.classList.remove('has-image');
                sendBtn.title = 'Send';
            }
        }
        showLoading(true);
        showTypingIndicator();
        
        // Disable send button while processing
        sendButton.disabled = true;

        try {
            console.log('Sending query:', query, 'Has tagged reference:', hasTaggedReference, 'Tagged products:', taggedProducts);
            
            // Validate tagged products before sending
            if (hasTaggedReference && taggedProducts.length > 0) {
                const invalidProducts = taggedProducts.filter(p => p.index === null || p.index === undefined);
                if (invalidProducts.length > 0) {
                    console.warn('⚠️  Some tagged products have invalid indices and will be filtered out:', invalidProducts);
                }
            }
            
            // Check if this is a compatibility query
            const compatibilityPatterns = ['goes with', 'matches', 'compatible with', 'what goes with'];
            const isCompatibilityQuery = compatibilityPatterns.some(pattern => 
                query.toLowerCase().includes(pattern)
            );
            
            if (isCompatibilityQuery) {
                // Extract product name from query
                const productMatch = query.match(/(?:goes with|matches|compatible with)\s+(.+)/i);
                if (productMatch) {
                    const productName = productMatch[1].trim();
                    // Call compatibility endpoint
                    const response = await fetch(`${API_BASE_URL}/compatibility`, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            product_id: productName,
                            type: 'style',
                            top_k: 5
                        })
                    });
                    
                    const data = await response.json();
                    showLoading(false);
                    
                    if (data.compatible_products && data.compatible_products.length > 0) {
                        displayResults(data.compatible_products, query);
                        addMessage(`These products go well with "${data.reference_product.name}":`, 'bot');
                    } else {
                        addMessage("I couldn't find compatible products. Try specifying a product name.", 'bot');
                    }
                    return;
                }
            }
            
            // Send query to backend with session ID and optional image
            const response = await fetch(`${API_BASE_URL}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query || '',
                    top_k: 10,
                    session_id: sessionId,
                    use_visual: hasImage,
                    image_embedding: currentImageEmbedding,
                    gender: selectedGender,  // Send gender preference
                    tagged_products: hasTaggedReference ? taggedProducts
                        .filter(p => p.index !== null && p.index !== undefined) // Filter out invalid indices
                        .map(p => ({
                            index: p.index,
                            name: p.name,
                            category: p.category,
                            gender: p.gender
                        })) : []
                })
            });

            // Check response status first
            if (!response.ok) {
                throw new Error(`Server error: ${response.status} ${response.statusText}`);
            }
            
            // Check if response is JSON
            const contentType = response.headers.get("content-type");
            if (!contentType || !contentType.includes("application/json")) {
                const text = await response.text();
                console.error("Non-JSON response:", text);
                throw new Error("Server returned non-JSON response. Make sure the backend is running properly.");
            }
            
            const data = await response.json();
            showLoading(false);
            hideTypingIndicator();
            sendButton.disabled = false;

            if (data.results && data.results.length > 0) {
                // Add index to each product if not present (for tagging)
                const resultsWithIndex = data.results.map((product, idx) => {
                    if (product.index === undefined) {
                        // Try to infer index from product data or use array index
                        // This is a fallback - ideally backend should include index
                        return { ...product, index: product.index || idx };
                    }
                    return product;
                });
                
                // Check for personalized message
                if (data.personalized_message) {
                    addMessage(data.personalized_message, 'bot');
                }
                
                // Display results
                displayResults(resultsWithIndex, query);
                
                // Clear image embedding after successful search
                if (hasImage) {
                    currentImageEmbedding = null;
                    addMessage("Image search completed. Upload a new image for another visual search.", 'bot');
                }
                
                // Store user preferences if available
                if (data.user_preferences) {
                    localStorage.setItem('cleo_user_preferences', JSON.stringify(data.user_preferences));
                }
            } else {
                addMessage("I couldn't find any products matching that query. Try rephrasing or asking about colors, materials, or styles.", 'bot');
                // Clear image embedding even if no results
                if (hasImage) {
                    currentImageEmbedding = null;
                }
            }
        } catch (error) {
            showLoading(false);
            hideTypingIndicator();
            sendButton.disabled = false;
            console.error('Error:', error);
            console.error('Error details:', error.message, error.stack);
            let errorMsg = `Sorry, I'm having trouble connecting to the server. Make sure the backend is running on ${API_BASE_URL.replace('/api', '')}`;
            if (error.message) {
                errorMsg += `\n\nError: ${error.message}`;
            }
            addMessage(errorMsg, 'bot');
        }
    }

    function addMessage(text, sender) {
        if (sender === 'bot') {
            // Create wrapper with avatar for bot messages
            const messageWrapper = document.createElement('div');
            messageWrapper.style.display = 'flex';
            messageWrapper.style.gap = '12px';
            messageWrapper.style.alignItems = 'flex-start';
            
            const avatar = document.createElement('div');
            avatar.className = 'bot-avatar';
            avatar.textContent = 'cleo';
            messageWrapper.appendChild(avatar);
            
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}-message`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.textContent = text;
            
            messageDiv.appendChild(contentDiv);
            messageWrapper.appendChild(messageDiv);
            messagesContainer.appendChild(messageWrapper);
        } else {
            // User messages without avatar
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}-message`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.textContent = text;
            
            messageDiv.appendChild(contentDiv);
            messagesContainer.appendChild(messageDiv);
        }
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function displayResults(products, query) {
        // Add bot avatar and message container
        const messageWrapper = document.createElement('div');
        messageWrapper.className = 'message-with-avatar';
        messageWrapper.style.display = 'flex';
        messageWrapper.style.gap = '12px';
        messageWrapper.style.alignItems = 'flex-start';
        
        const avatar = document.createElement('div');
        avatar.className = 'bot-avatar';
        avatar.textContent = 'cleo';
        messageWrapper.appendChild(avatar);
        
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message';
        messageDiv.style.flex = '1';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const header = document.createElement('div');
        header.className = 'results-header';
        header.textContent = `Here ${products.length === 1 ? 'is' : 'are'} ${products.length} match${products.length !== 1 ? 'es' : ''} for '${query}':`;
        contentDiv.appendChild(header);

        // Create product cards
        const productsContainer = document.createElement('div');
        productsContainer.className = 'products-grid';

        products.forEach((product, index) => {
            // Try to get index from product object, fallback to array index
            const productIndex = product.index !== undefined ? product.index : index;
            const productCard = createProductCard(product, productIndex);
            productsContainer.appendChild(productCard);
        });

        contentDiv.appendChild(productsContainer);
        messageDiv.appendChild(contentDiv);
        messageWrapper.appendChild(messageDiv);
        messagesContainer.appendChild(messageWrapper);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function createProductCard(product, productIndex = null) {
        const card = document.createElement('div');
        card.className = 'product-card';
        
        // Use product index from product object if available, otherwise use provided index
        const idx = productIndex !== null ? productIndex : (product.index !== undefined ? product.index : null);
        if (idx !== null) {
            card.setAttribute('data-product-id', idx);
        }

        // Check if product is tagged
        const isTagged = idx !== null && taggedProducts.some(p => p.index === idx);
        if (isTagged) {
            card.classList.add('tagged');
        }

        // Tag button - positioned absolutely in top-right
        const tagButton = document.createElement('button');
        tagButton.className = 'product-tag-btn';
        if (isTagged) {
            tagButton.classList.add('tagged');
        }
        tagButton.innerHTML = '@';
        tagButton.title = isTagged ? 'Tagged product' : 'Tag product';
        tagButton.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleProductTag(product, idx, card, tagButton);
        });
        card.appendChild(tagButton);

        // Product image
        if (product.primary_image) {
            const img = document.createElement('img');
            img.src = product.primary_image;
            img.alt = product.name;
            img.className = 'product-image';
            card.appendChild(img);
        }

        // Product info
        const info = document.createElement('div');
        info.className = 'product-info';

        const name = document.createElement('h3');
        name.textContent = product.name;
        info.appendChild(name);

        const price = document.createElement('div');
        price.className = 'product-price';
        price.textContent = `$${product.price}`;
        info.appendChild(price);

        // Attributes - colors and materials excluded per user request
        // (Keeping color matches as they're useful for styling suggestions)

        // Color matches
        if (product.complementary_colors) {
            const matches = document.createElement('div');
            matches.className = 'color-matches';
            matches.innerHTML = `<strong>Pairs with:</strong> ${product.complementary_colors}`;
            info.appendChild(matches);
        }

        // Link button
        if (product.url) {
            const link = document.createElement('a');
            link.href = product.url;
            link.target = '_blank';
            link.className = 'product-link';
            link.textContent = 'View';
            info.appendChild(link);
        }

        card.appendChild(info);
        return card;
    }

    function toggleProductTag(product, productIndex, card, tagButton) {
        if (productIndex === null) {
            console.warn('Cannot tag product: no index available');
            return;
        }

        const existingIndex = taggedProducts.findIndex(p => p.index === productIndex);
        
        if (existingIndex >= 0) {
            // Untag
            taggedProducts.splice(existingIndex, 1);
            card.classList.remove('tagged');
            tagButton.classList.remove('tagged');
            tagButton.title = 'Tag product';
        } else {
            // Tag - IMPORTANT: Preserve all product attributes including gender
            const taggedProduct = {
                index: productIndex,
                name: product.name,
                category: product.category || '',
                gender: product.gender || selectedGender || '', // Include current gender filter if product doesn't have one
                url: product.url || '',
                primary_image: product.primary_image || '',
                price: product.price || '',
                timestamp: Date.now()
            };
            taggedProducts.push(taggedProduct);
            card.classList.add('tagged');
            tagButton.classList.add('tagged');
            tagButton.title = 'Tagged product';
        }
        
        saveTaggedProducts();
        
        // Visual feedback animation
        card.style.transform = 'scale(1.02)';
        setTimeout(() => {
            card.style.transform = '';
        }, 200);
    }

    function showLoading(show) {
        loadingIndicator.style.display = show ? 'flex' : 'none';
    }
    
    // Typing indicator functions
    const typingIndicator = document.getElementById('typing-indicator');
    
    function showTypingIndicator() {
        if (typingIndicator) {
            typingIndicator.style.display = 'flex';
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
    
    function hideTypingIndicator() {
        if (typingIndicator) {
            typingIndicator.style.display = 'none';
        }
    }

    // Function to show personalized welcome
    function showPersonalizedWelcome() {
        const storedPrefs = localStorage.getItem('cleo_user_preferences');
        if (storedPrefs) {
            try {
                const prefs = JSON.parse(storedPrefs);
                if (prefs.favorite_colors && prefs.favorite_colors.length > 0) {
                    setTimeout(() => {
                        addMessage(`Welcome back! I remember you like ${prefs.favorite_colors[0]} items. Want to see what's new?`, 'bot');
                    }, 1000);
                } else if (prefs.style_preferences && prefs.style_preferences.length > 0) {
                    setTimeout(() => {
                        addMessage(`Welcome back! Looking for more ${prefs.style_preferences[0]} styles today?`, 'bot');
                    }, 1000);
                }
            } catch (e) {
                console.error('Error parsing preferences:', e);
            }
        }
    }

    // Check API health on load
    fetch(`${API_BASE_URL}/health`)
        .then(res => {
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            }
            return res.json();
        })
        .then(data => {
            if (data.status === 'healthy') {
                console.log(`✅ Connected: ${data.products_loaded} products loaded`);
                // Show personalized welcome after connection
                showPersonalizedWelcome();
            }
        })
        .catch(err => {
            console.error('⚠️  Backend not available:', err);
            console.error('Error details:', err.message, err.stack);
            addMessage(`⚠️  Backend server not available. Error: ${err.message}\n\nMake sure the backend is running: python backend/app.py`, 'bot');
        });
});

