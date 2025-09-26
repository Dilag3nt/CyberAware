import { preserveScroll, fetchWithRetry, showDismissibleMessage, showToast } from './utils.js';

export async function loadPhishSimulation() {
    const phishContent = document.getElementById('phish-content');
    if (!phishContent) return;
    preserveScroll(async () => {
        phishContent.innerHTML = '<p>Loading phishing simulation...</p>';
        showDismissibleMessage(phishContent, 'Spot the phishing red flags in this simulation! Dismiss to start.');
        try {
            const res = await fetchWithRetry('/api/phish/generate', 3, 2000);
            const data = await res.json();
            if (data.error) {
                phishContent.innerHTML = `<p>${data.error}</p>`;
                return;
            }
            phishContent.innerHTML = data.html;
            // Add interactive elements
            const interactiveElements = phishContent.querySelectorAll('a, img, button');
            interactiveElements.forEach((el, i) => {
                el.addEventListener('mouseover', () => {
                    el.title = `Red flag hint ${i + 1}: Check for suspicious attributes.`;
                });
                el.addEventListener('click', (e) => {
                    e.preventDefault();
                    showToast(`Red flag identified: ${el.title}`, 'info');
                });
            });
            // Add submit button for analysis
            const submitButton = document.createElement('button');
            submitButton.className = 'nav-button';
            submitButton.textContent = 'Submit Analysis';
            submitButton.addEventListener('click', () => {
                showToast('Analysis submitted! Feedback: Check for mismatched domains and urgency.', 'info');
            });
            phishContent.appendChild(submitButton);
        } catch (e) {
            console.error('Phish simulation fetch error:', e);
            phishContent.innerHTML = '<p>Error loading phishing simulation</p>';
        }
    });
}