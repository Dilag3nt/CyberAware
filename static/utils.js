export const debounce = (func, wait) => {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
};

export const preserveScroll = (callback) => {
    const scrollY = window.scrollY;
    callback();
    window.scrollTo(0, scrollY);
};

export const fetchWithRetry = async (url, maxRetries = 3, delay = 2000, options = {}) => {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response;
        } catch (error) {
            if (attempt === maxRetries) throw error;
            await new Promise(resolve => setTimeout(resolve, delay * attempt));
        }
    }
};

export const formatDate = (dateStr) => {
    if (!dateStr) return 'Not Available';
    const normalizedDateStr = dateStr.replace(/\+00:00Z?$/, 'Z');
    const dateObj = new Date(normalizedDateStr);
    if (isNaN(dateObj.getTime())) return 'Unknown';
    return dateObj.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
};

export const showToast = (message, type = 'info', duration = 3000) => {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 100);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
};

export const showDismissibleMessage = (container, message) => {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'dismissible-message';
    msgDiv.innerHTML = `${message} <button class="close-btn">×</button>`;
    (container || document.body).appendChild(msgDiv);
    msgDiv.querySelector('.close-btn').addEventListener('click', () => msgDiv.remove());
};