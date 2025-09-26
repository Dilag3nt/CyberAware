function startGoogleLogin() {
    localStorage.setItem('preLoginState', JSON.stringify({
        currentSlide,
        slides,
        currentQuestion,
        questions,
        answers,
        refreshTimestamp: latestRefreshTimestamp,
        quizId: questions[0]?.id,
        pendingQuizSubmission: localStorage.getItem('quizSubmitted') === 'true' ? false : true
    }));
    const section = localStorage.getItem('currentSection') || 'home';
    localStorage.setItem('returnToSection', section);
    window.location.href = `/login/google?return_to=${section}`;
}

function startMicrosoftLogin() {
    localStorage.setItem('preLoginState', JSON.stringify({
        currentSlide,
        slides,
        currentQuestion,
        questions,
        answers,
        refreshTimestamp: latestRefreshTimestamp,
        quizId: questions[0]?.id,
        pendingQuizSubmission: localStorage.getItem('quizSubmitted') === 'true' ? false : true
    }));
    const section = localStorage.getItem('currentSection') || 'home';
    localStorage.setItem('returnToSection', section);
    window.location.href = `/login/microsoft?return_to=${section}`;
}

async function fetchUserTeamStatus() {
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

function clearUserState() {
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

function logout() {
    clearUserState();
    window.location.href = '/logout';
}