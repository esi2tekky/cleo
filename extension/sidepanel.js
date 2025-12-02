// Chrome Extension Side Panel - Shopping Assistant Chat

const API_BASE_URL = 'http://localhost:5001/api';

// Tagged products state management
let taggedProducts = [];
const TAGGED_PRODUCTS_KEY = 'cleo_tagged_products';

// Last displayed products (for "show me more like this" without tagging)
let lastDisplayedProducts = [];

// Gender filter state
let selectedGender = 'all'; // 'men', 'women', or 'all'

// Load tagged products from localStorage
function loadTaggedProducts() {
    const stored = localStorage.getItem(TAGGED_PRODUCTS_KEY);
    if (stored) {
        try {
            const parsed = JSON.parse(stored);
            // Validate tagged products - only keep those with valid index
            taggedProducts = parsed.filter(p => p.index !== null && p.index !== undefined);
            // If validation removed products, save the cleaned list
            if (taggedProducts.length !== parsed.length) {
                saveTaggedProducts();
            }
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

// Function to update tagged indicator
function updateTaggedIndicator() {
    const indicator = document.getElementById('tagged-indicator');
    const countText = document.getElementById('tagged-count-text');
    if (!indicator || !countText) return;
    
    // Only show indicator if there are tagged products AND products are currently displayed
    // This prevents showing "1 product tagged" when no products are visible
    const count = taggedProducts.length;
    const hasDisplayedProducts = lastDisplayedProducts.length > 0;
    
    if (count === 0 || !hasDisplayedProducts) {
        indicator.style.display = 'none';
    } else {
        indicator.style.display = 'flex';
        if (count === 1) {
            countText.textContent = '1 product tagged';
        } else {
            countText.textContent = `${count} products tagged`;
        }
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const queryInput = document.getElementById('query-input');
    const sendButton = document.getElementById('send-button');
    const messagesContainer = document.getElementById('messages');
    const loadingIndicator = document.getElementById('loading');
    
    // Initialize tagged indicator
    updateTaggedIndicator();

    // Gender filter buttons
    const genderMenBtn = document.getElementById('gender-men');
    const genderWomenBtn = document.getElementById('gender-women');
    const genderAllBtn = document.getElementById('gender-all');
    
    // Gender button click handlers
    genderMenBtn.addEventListener('click', () => {
        selectedGender = 'men';
        genderMenBtn.classList.add('active');
        genderWomenBtn.classList.remove('active');
        genderAllBtn.classList.remove('active');
    });
    
    genderWomenBtn.addEventListener('click', () => {
        selectedGender = 'women';
        genderWomenBtn.classList.add('active');
        genderMenBtn.classList.remove('active');
        genderAllBtn.classList.remove('active');
    });
    
    genderAllBtn.addEventListener('click', () => {
        selectedGender = 'all';
        genderAllBtn.classList.add('active');
        genderMenBtn.classList.remove('active');
        genderWomenBtn.classList.remove('active');
    });
    
    // Suggestion chip click handlers
    const suggestionChips = document.querySelectorAll('.chip');
    suggestionChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const suggestion = chip.getAttribute('data-suggestion');
            if (suggestion) {
                // Set the query input value
                queryInput.value = suggestion;
                // Trigger the send handler
                handleSend();
            }
        });
    });
    
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
        if (!query) return;

        // Check if query references a product (e.g., "show me more like this")
        const queryLower = query.toLowerCase();
        const pronounPatterns = ['this', 'that', 'it', 'this one', 'that one'];
        const similarPatterns = ['more like', 'similar', 'like this', 'like that'];
        const hasReference = pronounPatterns.some(p => queryLower.includes(p)) || 
                           similarPatterns.some(p => queryLower.includes(p));
        
        // Determine which products to send as tagged products
        let productsToSend = [];
        if (hasReference) {
            // If we have tagged products, use those
            if (taggedProducts.length > 0) {
                productsToSend = taggedProducts.filter(p => p.index !== null && p.index !== undefined);
            } 
            // Otherwise, use the last displayed product (most recent)
            else if (lastDisplayedProducts.length > 0) {
                const lastProduct = lastDisplayedProducts[lastDisplayedProducts.length - 1];
                if (lastProduct && lastProduct.index !== undefined) {
                    productsToSend = [{
                        index: lastProduct.index,
                        name: lastProduct.name || '',
                        category: lastProduct.category || ''
                    }];
                    console.log(`Using last displayed product (index ${lastProduct.index}) for reference query`);
                }
            }
        }

        // Add user message to chat
        addMessage(query, 'user');
        queryInput.value = '';
        showLoading(true);

        // Clear tagged products after sending query (reset for next query)
        if (taggedProducts.length > 0) {
            taggedProducts = [];
            saveTaggedProducts();
            updateTaggedIndicator();
        }

        try {
            // Send query to backend
            const response = await fetch(`${API_BASE_URL}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query,
                    top_k: 10,
                    tagged_products: productsToSend,  // Send tagged products before clearing
                    last_displayed_products: lastDisplayedProducts,  // Send last displayed products for "which of these" queries
                    gender: selectedGender  // Send selected gender filter
                })
            });

            const data = await response.json();
            showLoading(false);

            if (data.results && data.results.length > 0) {
                // Display results
                displayResults(data.results, query);
            } else {
                addMessage("I couldn't find any products matching that query. Try rephrasing or asking about colors, materials, or styles.", 'bot');
            }
        } catch (error) {
            showLoading(false);
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
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = text;
        
        messageDiv.appendChild(contentDiv);
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function displayResults(products, query) {
        // Store last displayed products for reference queries (store full product data)
        lastDisplayedProducts = products.map(p => ({
            index: p.index,
            name: p.name || '',
            category: p.category || '',
            description: p.description || '',  // Include description for feature checking
            url: p.url || '',
            price: p.price || '',
            primary_image: p.primary_image || ''  // Include image for display
        }));
        
        // Add bot message with results
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const header = document.createElement('div');
        header.className = 'results-header';
        header.textContent = `Found ${products.length} product${products.length !== 1 ? 's' : ''}:`;
        contentDiv.appendChild(header);

        // Create product cards
        const productsContainer = document.createElement('div');
        productsContainer.className = 'products-grid';

        products.forEach((product, index) => {
            const productCard = createProductCard(product, product.index !== undefined ? product.index : index);
            productsContainer.appendChild(productCard);
        });

        contentDiv.appendChild(productsContainer);
        messageDiv.appendChild(contentDiv);
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        // Update tagged indicator after displaying products (so it shows if products are tagged)
        updateTaggedIndicator();
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

        // Product image (always create container, with fallback for missing/failed images)
        const imgContainer = document.createElement('div');
        imgContainer.className = 'product-image-container';
        
        if (product.primary_image && product.primary_image.trim() !== '') {
            const img = document.createElement('img');
            img.src = product.primary_image;
            img.alt = product.name || 'Product image';
            img.className = 'product-image';
            
            // Handle image load errors
            img.onerror = function() {
                // Replace with placeholder on error
                imgContainer.innerHTML = '';
                const placeholder = document.createElement('div');
                placeholder.className = 'product-image-placeholder';
                placeholder.innerHTML = '📦';
                placeholder.title = 'Image not available';
                imgContainer.appendChild(placeholder);
            };
            
            imgContainer.appendChild(img);
        } else {
            // No image URL provided - show placeholder
            const placeholder = document.createElement('div');
            placeholder.className = 'product-image-placeholder';
            placeholder.innerHTML = '📦';
            placeholder.title = 'No image available';
            imgContainer.appendChild(placeholder);
        }
        
        card.appendChild(imgContainer);

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
            // Limit to first 3 colors
            const colorsList = product.complementary_colors.split(',').map(c => c.trim()).slice(0, 3);
            const limitedColors = colorsList.join(', ');
            matches.innerHTML = `<strong>Pairs with:</strong> ${limitedColors}`;
            info.appendChild(matches);
        }

        // Link button
        if (product.url) {
            const link = document.createElement('a');
            link.href = product.url;
            link.target = '_blank';
            link.className = 'product-link';
            link.textContent = 'View Product →';
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
            // Tag
            const taggedProduct = {
                index: productIndex,
                name: product.name,
                category: product.category || '',
                url: product.url || '',
                primary_image: product.primary_image || '',
                price: product.price || ''
            };
            taggedProducts.push(taggedProduct);
            card.classList.add('tagged');
            tagButton.classList.add('tagged');
            tagButton.title = 'Tagged product';
        }
        
        saveTaggedProducts();
        
        // Update tagged indicator near input field
        updateTaggedIndicator();
        
        // Visual feedback animation
        card.style.transform = 'scale(1.02)';
        setTimeout(() => {
            card.style.transform = '';
        }, 200);
    }

    function showLoading(show) {
        loadingIndicator.style.display = show ? 'flex' : 'none';
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
            }
        })
        .catch(err => {
            console.error('⚠️  Backend not available:', err);
            console.error('Error details:', err.message, err.stack);
            addMessage(`⚠️  Backend server not available. Error: ${err.message}\n\nMake sure the backend is running: python backend/app.py`, 'bot');
        });
});

