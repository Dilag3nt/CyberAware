function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function preserveScroll(callback) {
    const scrollY = window.scrollY || window.pageYOffset;
    requestAnimationFrame(() => {
        callback();
        window.scrollTo({ top: scrollY, behavior: 'auto' });
        console.log('Restored scroll to:', scrollY);
    });
}

async function fetchWithRetry(url, maxRetries = 3, delay = 2000, options = {}) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            const response = await fetch(url, { ...options, cache: 'no-store' });
            if (response.status === 429) {
                const retryAfter = response.headers.get('Retry-After') || delay;
                await new Promise(resolve => setTimeout(resolve, retryAfter * (i + 1)));
                continue;
            }
            return response;
        } catch (e) {
            if (i === maxRetries - 1) throw e;
            await new Promise(resolve => setTimeout(resolve, delay * (i + 1)));
        }
    }
    throw new Error('Max retries exceeded');
}

function formatDate(dateStr) {
    if (!dateStr) return 'Not Available';
    const normalizedDateStr = dateStr.replace(/\+00:00Z?$/, 'Z');
    const dateObj = new Date(normalizedDateStr);
    if (isNaN(dateObj.getTime())) return 'Unknown';
    const userTZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const options = {
        month: '2-digit',
        day: '2-digit',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: userTZ
    };
    return dateObj.toLocaleString('en-US', options);
}

function showToast(message, type = 'info') {
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('show');
    }, 100);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

function showDismissibleMessage(container, text) {
    if (localStorage.getItem('phishWelcomeDismissed') === 'true') return;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'welcome-message';
    messageDiv.innerHTML = `${text}<span class="dismiss-welcome" id="dismiss-phish-welcome"><i class="fa-solid fa-square-xmark"></i></span>`;
    container.prepend(messageDiv);
    const dismissButton = document.getElementById('dismiss-phish-welcome');
    if (dismissButton) {
        dismissButton.addEventListener('click', () => {
            preserveScroll(() => {
                localStorage.setItem('phishWelcomeDismissed', 'true');
                messageDiv.remove();
            });
        });
    }
}