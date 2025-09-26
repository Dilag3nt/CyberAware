const debounce = (func, wait) => {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
};

const preserveScroll = (callback) => {
    const scrollY = window.scrollY;
    callback();
    window.scrollTo(0, scrollY);
};

const fetchWithRetry = async (url, options = {}, maxRetries = 3) => {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return response;
        } catch (error) {
            if (attempt === maxRetries) throw error;
            await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
        }
    }
};

const formatDate = (date) => {
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
};

const showToast = (message, duration = 3000) => {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
};

const showDismissibleMessage = (message) => {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'dismissible-message';
    msgDiv.innerHTML = `${message} <button class="close-btn">×</button>`;
    document.body.appendChild(msgDiv);
    msgDiv.querySelector('.close-btn').addEventListener('click', () => msgDiv.remove());
};

export { debounce, preserveScroll, fetchWithRetry, formatDate, showToast, showDismissibleMessage };