// Chrome Extension Side Panel - Shopping Assistant Chat

const API_BASE_URL = 'http://localhost:5001/api';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const queryInput = document.getElementById('query-input');
    const sendButton = document.getElementById('send-button');
    const messagesContainer = document.getElementById('messages');
    const loadingIndicator = document.getElementById('loading');

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

        // Add user message to chat
        addMessage(query, 'user');
        queryInput.value = '';
        showLoading(true);

        try {
            // Send query to backend
            const response = await fetch(`${API_BASE_URL}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query,
                    top_k: 10
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
            const productCard = createProductCard(product);
            productsContainer.appendChild(productCard);
        });

        contentDiv.appendChild(productsContainer);
        messageDiv.appendChild(contentDiv);
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function createProductCard(product) {
        const card = document.createElement('div');
        card.className = 'product-card';

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
            link.textContent = 'View Product →';
            info.appendChild(link);
        }

        card.appendChild(info);
        return card;
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

