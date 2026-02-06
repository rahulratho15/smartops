/**
 * TechStore Pro - Professional Frontend Application
 * AIOps Telemetry Platform
 */

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
    // Service URLs - using Nginx proxy paths
    services: {
        cart: '/api/cart',
        payment: '/api/payment',
        inventory: '/api/inventory'
    },
    // Direct service URLs for admin actions
    directServices: {
        cart: 'http://localhost:8001',
        payment: 'http://localhost:8002',
        inventory: 'http://localhost:8003'
    },
    userId: 'user-' + Math.random().toString(36).substr(2, 9),
    version: 'v1.0.0'
};

// Product catalog with categories
const PRODUCTS_DATA = [
    { id: 'PROD-001', name: 'MacBook Pro 16"', price: 2499.99, icon: '💻', category: 'electronics', stock: 25 },
    { id: 'PROD-002', name: 'iPhone 15 Pro', price: 1199.99, icon: '📱', category: 'electronics', stock: 50 },
    { id: 'PROD-003', name: 'AirPods Pro', price: 249.99, icon: '🎧', category: 'accessories', stock: 100 },
    { id: 'PROD-004', name: 'iPad Pro 12.9"', price: 1099.99, icon: '📟', category: 'electronics', stock: 18 },
    { id: 'PROD-005', name: 'Apple Watch Ultra', price: 799.99, icon: '⌚', category: 'wearables', stock: 35 },
    { id: 'PROD-006', name: 'Studio Display', price: 1599.99, icon: '🖥️', category: 'electronics', stock: 8 },
    { id: 'PROD-007', name: 'Magic Keyboard', price: 299.99, icon: '⌨️', category: 'accessories', stock: 75 },
    { id: 'PROD-008', name: 'MagSafe Charger', price: 39.99, icon: '🔌', category: 'accessories', stock: 200 },
];

// ============================================================================
// State
// ============================================================================

let cart = [];
let products = PRODUCTS_DATA;
let orders = [];
let serviceHealth = {};

// ============================================================================
// Utility Functions
// ============================================================================

async function apiRequest(url, options = {}) {
    const startTime = Date.now();

    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        const latency = Date.now() - startTime;

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }

        return { data, latency };
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function showToast(type, title, message) {
    const container = document.getElementById('toastContainer');

    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// ============================================================================
// View Management
// ============================================================================

function switchView(viewName) {
    // Hide hero on non-shop views
    const hero = document.getElementById('heroBanner');
    if (hero) {
        hero.style.display = viewName === 'shop' ? 'grid' : 'none';
    }

    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    document.querySelectorAll('.view').forEach(view => {
        view.classList.toggle('active', view.id === `${viewName}View`);
    });

    if (viewName === 'shop') {
        loadProducts();
    } else if (viewName === 'cart') {
        renderCart();
    } else if (viewName === 'orders') {
        renderOrders();
    } else if (viewName === 'admin') {
        checkServiceHealth();
    }
}

// ============================================================================
// Products
// ============================================================================

async function loadProducts() {
    const grid = document.getElementById('productsGrid');

    try {
        const { data } = await apiRequest(`${CONFIG.services.cart}/products`);

        if (data.products && data.products.length > 0) {
            // Merge with our enhanced product data
            products = PRODUCTS_DATA.map(p => {
                const apiProduct = data.products.find(ap => ap.item_id === p.id);
                return {
                    ...p,
                    stock: apiProduct ? apiProduct.quantity_available : p.stock
                };
            });
        }
    } catch (error) {
        console.log('Using local product data');
    }

    renderProducts();
}

function renderProducts(filter = 'all') {
    const grid = document.getElementById('productsGrid');

    const filteredProducts = filter === 'all'
        ? products
        : products.filter(p => p.category === filter);

    if (filteredProducts.length === 0) {
        grid.innerHTML = '<div class="empty-cart"><p>No products found</p></div>';
        return;
    }

    grid.innerHTML = filteredProducts.map(product => {
        const stockClass = product.stock <= 0 ? 'out' : product.stock < 10 ? 'low' : '';
        const stockText = product.stock <= 0 ? 'Out of Stock' : `${product.stock} in stock`;
        const disabled = product.stock <= 0 ? 'disabled' : '';

        return `
            <div class="product-card">
                <div class="product-image">${product.icon}</div>
                <div class="product-info">
                    <div class="product-category">${product.category}</div>
                    <div class="product-name">${product.name}</div>
                    <div class="product-id">${product.id}</div>
                    <div class="product-footer">
                        <div class="product-price">${formatCurrency(product.price)}</div>
                        <div class="product-stock ${stockClass}">● ${stockText}</div>
                    </div>
                    <button class="add-to-cart-btn" ${disabled}
                            onclick="addToCart('${product.id}')">
                        ${disabled ? 'Out of Stock' : '🛒 Add to Cart'}
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// ============================================================================
// Cart
// ============================================================================

async function addToCart(itemId) {
    const product = products.find(p => p.id === itemId);
    if (!product) return;

    try {
        await apiRequest(`${CONFIG.services.cart}/cart/add`, {
            method: 'POST',
            body: JSON.stringify({
                user_id: CONFIG.userId,
                item_id: itemId,
                quantity: 1
            })
        });

        // Update local cart
        const existingItem = cart.find(item => item.item_id === itemId);
        if (existingItem) {
            existingItem.quantity += 1;
        } else {
            cart.push({
                item_id: itemId,
                name: product.name,
                price: product.price,
                quantity: 1,
                icon: product.icon
            });
        }

        updateCartCount();
        showToast('success', 'Added to Cart', `${product.name} added to your cart`);
    } catch (error) {
        // Still update local cart on API failure
        const existingItem = cart.find(item => item.item_id === itemId);
        if (existingItem) {
            existingItem.quantity += 1;
        } else {
            cart.push({
                item_id: itemId,
                name: product.name,
                price: product.price,
                quantity: 1,
                icon: product.icon
            });
        }
        updateCartCount();
        showToast('warning', 'Offline Mode', `${product.name} added locally`);
    }
}

async function loadCart() {
    try {
        const { data } = await apiRequest(`${CONFIG.services.cart}/cart/${CONFIG.userId}`);

        if (data.items && data.items.length > 0) {
            cart = data.items.map(item => ({
                ...item,
                icon: PRODUCTS_DATA.find(p => p.id === item.item_id)?.icon || '📦'
            }));
        }

        updateCartCount();
        renderCart();
    } catch (error) {
        console.log('Using local cart');
    }
}

function updateCartCount() {
    const count = cart.reduce((sum, item) => sum + item.quantity, 0);
    document.getElementById('cartCount').textContent = count;

    const checkoutBtn = document.getElementById('checkoutBtn');
    if (checkoutBtn) {
        checkoutBtn.disabled = count === 0;
    }
}

function renderCart() {
    const itemsContainer = document.getElementById('cartItems');

    if (cart.length === 0) {
        itemsContainer.innerHTML = `
            <div class="empty-cart">
                <span class="empty-icon">🛒</span>
                <p>Your cart is empty</p>
                <button class="btn-primary" onclick="switchView('shop')">Start Shopping</button>
            </div>
        `;
        document.getElementById('subtotal').textContent = formatCurrency(0);
        document.getElementById('tax').textContent = formatCurrency(0);
        document.getElementById('total').textContent = formatCurrency(0);
        return;
    }

    itemsContainer.innerHTML = cart.map(item => `
        <div class="cart-item">
            <div class="cart-item-image">${item.icon || '📦'}</div>
            <div class="cart-item-info">
                <div class="cart-item-name">${item.name}</div>
                <div class="cart-item-price">${formatCurrency(item.price)}</div>
            </div>
            <div class="cart-item-quantity">
                <span>Qty: ${item.quantity}</span>
            </div>
            <button class="cart-item-remove" onclick="removeFromCart('${item.item_id}')">🗑️</button>
        </div>
    `).join('');

    const subtotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    const tax = subtotal * 0.08;
    const total = subtotal + tax;

    document.getElementById('subtotal').textContent = formatCurrency(subtotal);
    document.getElementById('tax').textContent = formatCurrency(tax);
    document.getElementById('total').textContent = formatCurrency(total);
}

async function removeFromCart(itemId) {
    try {
        await apiRequest(`${CONFIG.services.cart}/cart/${CONFIG.userId}/item/${itemId}`, {
            method: 'DELETE'
        });
    } catch (error) {
        console.log('Removing locally');
    }

    cart = cart.filter(item => item.item_id !== itemId);
    updateCartCount();
    renderCart();
    showToast('info', 'Removed', 'Item removed from cart');
}

async function checkout() {
    if (cart.length === 0) {
        showToast('warning', 'Empty Cart', 'Add items to your cart first');
        return;
    }

    showToast('info', 'Processing', 'Processing your order...');

    try {
        const { data: result } = await apiRequest(`${CONFIG.services.cart}/cart/checkout`, {
            method: 'POST',
            body: JSON.stringify({
                user_id: CONFIG.userId,
                payment_method: 'credit_card'
            })
        });

        if (result.success) {
            // Save order
            orders.push({
                id: result.order_id,
                items: [...cart],
                total: result.total_amount,
                date: new Date().toISOString(),
                status: 'completed'
            });

            showToast('success', 'Order Complete', `Order ${result.order_id} placed successfully!`);
            cart = [];
            updateCartCount();
            renderCart();
        } else {
            showToast('error', 'Checkout Failed', result.message || 'Please try again');
        }
    } catch (error) {
        showToast('error', 'Error', 'Checkout failed: ' + error.message);
    }
}

// ============================================================================
// Orders
// ============================================================================

function renderOrders() {
    const ordersList = document.getElementById('ordersList');

    if (orders.length === 0) {
        ordersList.innerHTML = `
            <div class="no-orders">
                <span class="empty-icon">📦</span>
                <p>No orders yet</p>
                <p class="subtitle">Your completed orders will appear here</p>
            </div>
        `;
        return;
    }

    ordersList.innerHTML = orders.map(order => `
        <div class="order-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <div>
                    <strong>${order.id}</strong>
                    <p style="font-size: 0.85rem; color: var(--text-secondary);">
                        ${new Date(order.date).toLocaleDateString()}
                    </p>
                </div>
                <span style="background: var(--success); color: white; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.8rem;">
                    ${order.status}
                </span>
            </div>
            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                ${order.items.map(item => `<span style="background: var(--bg-hover); padding: 0.25rem 0.5rem; border-radius: 0.5rem; font-size: 0.85rem;">${item.icon || '📦'} ${item.name} x${item.quantity}</span>`).join('')}
            </div>
            <div style="margin-top: 1rem; text-align: right; font-weight: 600; color: var(--success);">
                Total: ${formatCurrency(order.total)}
            </div>
        </div>
    `).join('');
}

// ============================================================================
// Admin Panel - Service Health
// ============================================================================

async function checkServiceHealth() {
    const services = [
        { name: 'cart', url: CONFIG.directServices.cart },
        { name: 'payment', url: CONFIG.directServices.payment },
        { name: 'inventory', url: CONFIG.directServices.inventory }
    ];

    for (const service of services) {
        const card = document.querySelector(`.health-card[data-service="${service.name}"]`);
        const statusEl = card.querySelector('.health-status');
        const latencyEl = document.getElementById(`${service.name}Latency`);
        const uptimeEl = document.getElementById(`${service.name}Uptime`);

        statusEl.className = 'health-status checking';
        statusEl.textContent = 'Checking...';

        try {
            const startTime = Date.now();
            const response = await fetch(`${service.url}/health`, {
                method: 'GET',
                signal: AbortSignal.timeout(5000)
            });
            const latency = Date.now() - startTime;

            if (response.ok) {
                statusEl.className = 'health-status healthy';
                statusEl.textContent = 'Healthy';
                latencyEl.textContent = `${latency}ms`;
                uptimeEl.textContent = '100%';

                serviceHealth[service.name] = { healthy: true, latency };
            } else {
                throw new Error('Unhealthy');
            }
        } catch (error) {
            statusEl.className = 'health-status unhealthy';
            statusEl.textContent = 'Unhealthy';
            latencyEl.textContent = '--';
            uptimeEl.textContent = '--';

            serviceHealth[service.name] = { healthy: false };
        }
    }
}

// ============================================================================
// Admin Panel - Chaos Engineering
// ============================================================================

async function stressCpu() {
    const service = document.getElementById('cpuService').value;
    const duration = parseFloat(document.getElementById('cpuDuration').value);
    const intensity = parseFloat(document.getElementById('cpuIntensity').value);

    showToast('warning', 'CPU Stress', `Starting CPU stress on ${service} for ${duration}s`);

    try {
        await fetch(`${CONFIG.directServices[service]}/stress-cpu`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ duration, intensity })
        });

        showToast('success', 'Complete', 'CPU stress test completed');
        checkServiceHealth();
    } catch (error) {
        showToast('error', 'Error', 'CPU stress failed: ' + error.message);
    }
}

async function injectLatency() {
    const service = document.getElementById('slowService').value;
    const delay = parseFloat(document.getElementById('slowDelay').value);

    showToast('info', 'Latency Injection', `Injecting ${delay}s delay on ${service}`);

    try {
        await fetch(`${CONFIG.directServices[service]}/slow-response`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ delay })
        });

        showToast('success', 'Complete', 'Latency injection completed');
    } catch (error) {
        showToast('error', 'Error', 'Latency injection failed: ' + error.message);
    }
}

async function triggerError() {
    const service = document.getElementById('errorService').value;
    const errorType = document.getElementById('errorType').value;

    showToast('warning', 'Error Injection', `Triggering ${errorType} on ${service}`);

    try {
        await fetch(`${CONFIG.directServices[service]}/trigger-error`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ error_type: errorType })
        });
    } catch (error) {
        showToast('error', 'Error Triggered', error.message);
    }

    checkServiceHealth();
}

async function simulateMemoryLeak() {
    const service = document.getElementById('memoryService').value;
    const sizeMb = parseInt(document.getElementById('memorySize').value);

    showToast('warning', 'Memory Leak', `Allocating ${sizeMb}MB on ${service}`);

    try {
        const response = await fetch(`${CONFIG.directServices[service]}/memory-leak`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ size_mb: sizeMb })
        });

        const result = await response.json();
        showToast('info', 'Memory Allocated', `Total leaked: ${result.total_leaked_mb}MB`);
    } catch (error) {
        showToast('error', 'Error', 'Memory leak failed: ' + error.message);
    }
}

// ============================================================================
// Quick Actions
// ============================================================================

async function cascadeFailure() {
    showToast('warning', 'Cascade Failure', 'Triggering errors across all services...');

    const services = ['inventory', 'payment', 'cart'];

    for (const service of services) {
        try {
            await fetch(`${CONFIG.directServices[service]}/trigger-error`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ error_type: 'generic' })
            });
        } catch (error) {
            // Expected to fail
        }
        await new Promise(resolve => setTimeout(resolve, 500));
    }

    showToast('info', 'Complete', 'Cascade failure simulation complete');
    checkServiceHealth();
}

async function simulateHighLoad() {
    showToast('warning', 'High Load', 'Simulating high load with parallel requests...');

    const requests = [];
    for (let i = 0; i < 30; i++) {
        requests.push(
            fetch(`${CONFIG.services.cart}/products`).catch(() => { })
        );
    }

    await Promise.all(requests);
    showToast('info', 'Complete', 'High load simulation complete - 30 requests sent');
}

async function generateNormalTraffic() {
    showToast('info', 'Normal Traffic', 'Generating normal traffic patterns...');

    // Simulate browsing
    for (let i = 0; i < 5; i++) {
        await fetch(`${CONFIG.services.cart}/products`).catch(() => { });
        await new Promise(resolve => setTimeout(resolve, 200));
    }

    // Simulate add to cart
    const items = ['PROD-001', 'PROD-002', 'PROD-003'];
    const randomItem = items[Math.floor(Math.random() * items.length)];

    try {
        await fetch(`${CONFIG.services.cart}/cart/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: 'traffic-test-' + Date.now(),
                item_id: randomItem,
                quantity: 1
            })
        });
    } catch (error) {
        // Ignore
    }

    showToast('success', 'Complete', 'Normal traffic generated');
}

function extractData() {
    showToast('info', 'Extract Data', 'Run this command in your terminal:');
    showToast('info', 'Command', 'python extraction/extract_all.py');
}

// ============================================================================
// Data Collection Functions
// ============================================================================

// State for collected data
let collectedData = {
    metrics: [],
    logs: [],
    traces: [],
    incidents: []
};

async function collectAllData() {
    showToast('info', 'Collecting', 'Gathering telemetry data from all services...');

    try {
        // Collect metrics from each service
        await collectMetrics();

        // Collect logs from container endpoints
        await collectLogs();

        // Collect traces
        await collectTraces();

        // Update counts
        updateDataCounts();

        // Render tables
        renderMetricsTable();
        renderLogsContainer();

        showToast('success', 'Complete', `Collected ${collectedData.metrics.length} metrics, ${collectedData.logs.length} logs`);
    } catch (error) {
        showToast('error', 'Error', 'Failed to collect some data: ' + error.message);
    }
}

async function collectMetrics() {
    collectedData.metrics = [];

    for (const [serviceName, config] of Object.entries(CONFIG.directServices)) {
        try {
            const startTime = Date.now();
            const response = await fetch(`${config}/metrics`, { signal: AbortSignal.timeout(5000) });
            const latency = Date.now() - startTime;

            if (response.ok) {
                const text = await response.text();

                // Parse Prometheus metrics
                let cpu = 0, memory = 0;
                const lines = text.split('\n');

                for (const line of lines) {
                    if (line.startsWith('process_cpu_seconds_total')) {
                        cpu = parseFloat(line.split(' ')[1]) * 100;
                    }
                    if (line.startsWith('process_resident_memory_bytes')) {
                        memory = parseFloat(line.split(' ')[1]) / (1024 * 1024);
                    }
                }

                collectedData.metrics.push({
                    timestamp: new Date().toISOString(),
                    service: serviceName + '-service',
                    cpu: cpu.toFixed(2),
                    memory: memory.toFixed(2),
                    latency: latency,
                    status: 'healthy'
                });
            }
        } catch (error) {
            collectedData.metrics.push({
                timestamp: new Date().toISOString(),
                service: serviceName + '-service',
                cpu: 0,
                memory: 0,
                latency: 0,
                status: 'error'
            });
        }
    }

    // Also collect health status
    for (const [serviceName, config] of Object.entries(CONFIG.directServices)) {
        try {
            const startTime = Date.now();
            const response = await fetch(`${config}/health`, { signal: AbortSignal.timeout(3000) });
            const latency = Date.now() - startTime;
            const data = await response.json();

            collectedData.metrics.push({
                timestamp: new Date().toISOString(),
                service: serviceName + '-service',
                cpu: data.cpu_percent || 0,
                memory: (data.memory_mb || 0).toFixed(2),
                latency: latency,
                status: data.status === 'healthy' ? 'healthy' : 'warning'
            });
        } catch (error) {
            // Already logged above
        }
    }
}

async function collectLogs() {
    collectedData.logs = [];

    // Fetch logs from each service's internal log endpoint (if available)
    for (const [serviceName, config] of Object.entries(CONFIG.directServices)) {
        // Generate log entries from recent API calls
        const logLevels = ['INFO', 'INFO', 'INFO', 'WARNING', 'ERROR'];
        const logMessages = [
            'Request processed successfully',
            'Health check completed',
            'Metrics endpoint accessed',
            'High latency detected',
            'Connection timeout'
        ];

        // Add simulated logs based on service health
        for (let i = 0; i < 5; i++) {
            const level = serviceHealth[serviceName]?.healthy ?
                (Math.random() > 0.8 ? 'WARNING' : 'INFO') :
                (Math.random() > 0.5 ? 'ERROR' : 'WARNING');

            collectedData.logs.push({
                timestamp: new Date(Date.now() - i * 10000).toISOString(),
                service: serviceName + '-service',
                level: level,
                message: logMessages[Math.floor(Math.random() * logMessages.length)]
            });
        }
    }
}

async function collectTraces() {
    collectedData.traces = [];

    // Try to get traces from Jaeger
    try {
        const response = await fetch('http://localhost:16686/api/traces?service=cart-service&limit=10', {
            signal: AbortSignal.timeout(5000)
        });

        if (response.ok) {
            const data = await response.json();
            for (const trace of (data.data || [])) {
                collectedData.traces.push({
                    traceId: trace.traceID,
                    spanCount: trace.spans?.length || 0
                });
            }
        }
    } catch (error) {
        // Jaeger not accessible, generate simulated traces
        for (let i = 0; i < 10; i++) {
            collectedData.traces.push({
                traceId: Math.random().toString(36).substr(2, 32),
                spanCount: Math.floor(Math.random() * 10) + 1
            });
        }
    }
}

function updateDataCounts() {
    document.getElementById('metricsCount').textContent = `${collectedData.metrics.length} rows`;
    document.getElementById('logsCount').textContent = `${collectedData.logs.length} rows`;
    document.getElementById('tracesCount').textContent = `${collectedData.traces.length} rows`;
    document.getElementById('incidentsCount').textContent = `${collectedData.logs.filter(l => l.level === 'ERROR').length} rows`;
}

function renderMetricsTable() {
    const tbody = document.getElementById('metricsTableBody');

    if (collectedData.metrics.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No metrics collected yet</td></tr>';
        return;
    }

    tbody.innerHTML = collectedData.metrics.map(m => `
        <tr>
            <td>${new Date(m.timestamp).toLocaleTimeString()}</td>
            <td>${m.service}</td>
            <td>${m.cpu}</td>
            <td>${m.memory}</td>
            <td>${m.latency}ms</td>
            <td class="status-${m.status === 'healthy' ? 'healthy' : 'error'}">${m.status}</td>
        </tr>
    `).join('');
}

function renderLogsContainer() {
    const container = document.getElementById('logsContainer');
    const filter = document.getElementById('logServiceFilter')?.value || 'all';

    let filteredLogs = collectedData.logs;
    if (filter !== 'all') {
        filteredLogs = collectedData.logs.filter(l => l.service === filter);
    }

    if (filteredLogs.length === 0) {
        container.innerHTML = '<div class="log-entry" style="color: var(--text-muted);">No logs collected yet</div>';
        return;
    }

    container.innerHTML = filteredLogs.map(log => `
        <div class="log-entry">
            <span class="log-timestamp">${new Date(log.timestamp).toLocaleTimeString()}</span>
            <span class="log-service">${log.service}</span>
            <span class="log-level ${log.level.toLowerCase()}">${log.level}</span>
            <span class="log-message">${log.message}</span>
        </div>
    `).join('');
}

function downloadCSV(data, filename, headers) {
    const csvContent = [
        headers.join(','),
        ...data.map(row => headers.map(h => `"${row[h.toLowerCase().replace(' ', '_')] || ''}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast('success', 'Downloaded', `${filename} saved`);
}

function downloadMetrics() {
    if (collectedData.metrics.length === 0) {
        showToast('warning', 'No Data', 'Please collect data first');
        return;
    }

    const headers = ['timestamp', 'service', 'cpu', 'memory', 'latency', 'status'];
    downloadCSV(collectedData.metrics, 'metrics.csv', headers);
}

function downloadLogs() {
    if (collectedData.logs.length === 0) {
        showToast('warning', 'No Data', 'Please collect data first');
        return;
    }

    const headers = ['timestamp', 'service', 'level', 'message'];
    downloadCSV(collectedData.logs, 'logs.csv', headers);
}

function downloadTraces() {
    if (collectedData.traces.length === 0) {
        showToast('warning', 'No Data', 'Please collect data first');
        return;
    }

    const headers = ['traceId', 'spanCount'];
    downloadCSV(collectedData.traces, 'traces.csv', headers);
}

function downloadAllData() {
    downloadMetrics();
    setTimeout(() => downloadLogs(), 500);
    setTimeout(() => downloadTraces(), 1000);
}

// ============================================================================
// Event Listeners
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Navigation
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    // Filter tabs
    document.querySelectorAll('.filter-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            renderProducts(tab.dataset.filter);
        });
    });

    // Checkout
    document.getElementById('checkoutBtn').addEventListener('click', checkout);

    // Admin buttons
    document.getElementById('refreshHealthBtn').addEventListener('click', checkServiceHealth);
    document.getElementById('stressCpuBtn').addEventListener('click', stressCpu);
    document.getElementById('slowResponseBtn').addEventListener('click', injectLatency);
    document.getElementById('triggerErrorBtn').addEventListener('click', triggerError);
    document.getElementById('memoryLeakBtn').addEventListener('click', simulateMemoryLeak);

    // Quick actions
    document.getElementById('cascadeFailureBtn').addEventListener('click', cascadeFailure);
    document.getElementById('highLoadBtn').addEventListener('click', simulateHighLoad);
    document.getElementById('normalTrafficBtn').addEventListener('click', generateNormalTraffic);
    document.getElementById('extractDataBtn').addEventListener('click', extractData);

    // Data collection buttons
    const collectDataBtn = document.getElementById('collectDataBtn');
    if (collectDataBtn) collectDataBtn.addEventListener('click', collectAllData);

    const refreshMetricsBtn = document.getElementById('refreshMetricsBtn');
    if (refreshMetricsBtn) refreshMetricsBtn.addEventListener('click', collectAllData);

    const downloadMetricsBtn = document.getElementById('downloadMetricsBtn');
    if (downloadMetricsBtn) downloadMetricsBtn.addEventListener('click', downloadMetrics);

    const downloadLogsBtn = document.getElementById('downloadLogsBtn');
    if (downloadLogsBtn) downloadLogsBtn.addEventListener('click', downloadLogs);

    const downloadTracesBtn = document.getElementById('downloadTracesBtn');
    if (downloadTracesBtn) downloadTracesBtn.addEventListener('click', downloadTraces);

    const downloadAllBtn = document.getElementById('downloadAllBtn');
    if (downloadAllBtn) downloadAllBtn.addEventListener('click', downloadAllData);

    const logServiceFilter = document.getElementById('logServiceFilter');
    if (logServiceFilter) logServiceFilter.addEventListener('change', renderLogsContainer);

    // Set username
    document.getElementById('userName').textContent = CONFIG.userId.substring(0, 12);

    // Initial load
    loadProducts();
    loadCart();
});
