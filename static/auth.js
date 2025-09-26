import state from './state.js';
import { fetchWithRetry, preserveScroll } from './utils.js';

export function startGoogleLogin() {
    localStorage.setItem('preLoginState', JSON.stringify({
        currentSlide: state.currentSlide,
        slides: state.slides,
        currentQuestion: state.currentQuestion,
        questions: state.questions,
        answers: state.answers,
        refreshTimestamp: state.latestRefreshTimestamp,
        quizId: state.questions[0]?.id,
        pendingQuizSubmission: localStorage.getItem('quizSubmitted') === 'true' ? false : true
    }));
    const section = localStorage.getItem('currentSection') || 'home';
    localStorage.setItem('returnToSection', section);
    window.location.href = `/login/google?return_to=${section}`;
}

export function startMicrosoftLogin() {
    localStorage.setItem('preLoginState', JSON.stringify({
        currentSlide: state.currentSlide,
        slides: state.slides,
        currentQuestion: state.currentQuestion,
        questions: state.questions,
        answers: state.answers,
        refreshTimestamp: state.latestRefreshTimestamp,
        quizId: state.questions[0]?.id,
        pendingQuizSubmission: localStorage.getItem('quizSubmitted') === 'true' ? false : true
    }));
    const section = localStorage.getItem('currentSection') || 'home';
    localStorage.setItem('returnToSection', section);
    window.location.href = `/login/microsoft?return_to=${section}`;
}

export async function fetchUserTeamStatus() {
    const toggleTeam = document.getElementById('toggle-team');
    if (!toggleTeam) return;
    try {
        const res = await fetchWithRetry('/api/user_team_status', 3, 2000);
        const data = await res.json();
        if (data.has_team) {
            toggleTeam.style.display = 'inline-block';
            toggleTeam.textContent = `Team (${data.domain})`;
        } else {
            toggleTeam.style.display = 'none';
        }
    } catch (e) {
        console.error('Failed to fetch user team status:', e);
    }
}

export function clearUserState() {
    const keysToClear = [
        'educationState',
        'quizSubmitted',
        'quizSubmissionMessage',
        'quizCountUpdated',
        'lastSection',
        'returnToSection',
        'preLoginState'
    ];
    keysToClear.forEach(key => localStorage.removeItem(key));
    Object.keys(localStorage).forEach(key => {
        if (key.startsWith('quizTaken_')) {
            localStorage.removeItem(key);
        }
    });
}

export function logout() {
    clearUserState();
    window.location.href = '/logout';
}