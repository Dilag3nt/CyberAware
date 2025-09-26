let currentScope = 'weekly';
let latestRefreshTimestamp = 0;

function typeTitle(element, text) {
    if (!element) return;
    new Typed(`#${element.id}`, {
        strings: ['Defend', text],
        typeSpeed: 40,
        backSpeed: 50,
        backDelay: 1000,
        showCursor: true,
        cursorChar: '|',
        startDelay: 500,
        loop: false,
        onComplete: (self) => {
            const cursor = document.querySelector('.typed-cursor');
            if (cursor) {
                cursor.style.display = 'none';
            }
            element.classList.add('typed-complete');
        }
    });
}

function toggleMode() {
    const modeToggle = document.getElementById('mode-toggle');
    if (!modeToggle) return;
    const isLightMode = document.body.classList.toggle('light');
    modeToggle.innerHTML = isLightMode ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
    localStorage.setItem('theme', isLightMode ? 'light' : 'dark');
}

async function showSection(section, username = null) {
    const validSections = ['home', 'profile', 'leaderboard', 'results', 'phish'];
    if (!validSections.includes(section)) {
        section = 'home';
    }
    const leaderboardSection = document.getElementById('leaderboard-section');
    const profileSection = document.getElementById('profile-section');
    const educationSection = document.getElementById('education-section');
    const phishSection = document.getElementById('phish-section');
    if (!leaderboardSection || !profileSection || !educationSection || !phishSection) {
        console.error('One or more section elements not found');
        return;
    }
    preserveScroll(() => {
        if (educationSection.style.display === 'block' && section !== 'home' && section !== 'results') {
            localStorage.setItem('educationState', JSON.stringify({
                currentSlide,
                slides,
                currentQuestion,
                questions,
                answers,
                refreshTimestamp: latestRefreshTimestamp,
                quizId: questions[0]?.id,
                pendingQuizSubmission: questions.length > 0 && currentQuestion >= questions.length
            }));
            console.log('Saved educationState:', localStorage.getItem('educationState'));
        }
        leaderboardSection.style.display = 'none';
        profileSection.style.display = 'none';
        educationSection.style.display = 'none';
        phishSection.style.display = 'none';
        document.querySelectorAll('#nav a').forEach(link => link.classList.remove('active'));
        const activeLink = document.getElementById(`nav-${section}`) || document.getElementById('nav-home');
        if (activeLink) activeLink.classList.add('active');
        let urlPath = section === 'home' || section === 'results' ? '/' : `/${section}`;
        if (section === 'profile' && username) {
            urlPath = `/profile/${encodeURIComponent(username)}`;
        }
        localStorage.setItem('currentSection', section);
        history.pushState({ section, username }, '', urlPath);
        if (section === 'profile') {
            profileSection.style.display = 'block';
            loadProfile(username);
        } else if (section === 'leaderboard') {
            leaderboardSection.style.display = 'block';
            loadLeaderboard();
        } else if (section === 'phish') {
            phishSection.style.display = 'block';
            loadPhishSimulation();
        } else {
            educationSection.style.display = 'block';
            const educationContent = document.getElementById('education-content');
            const startEducationBtn = document.getElementById('start-education');
            const updateEducationDOM = async () => {
                if (educationContent) educationContent.innerHTML = '';
                if (startEducationBtn) startEducationBtn.style.display = 'none';
                const savedState = localStorage.getItem('educationState');
                const preLoginState = localStorage.getItem('preLoginState');
                console.log('Restoring educationState:', savedState, 'preLoginState:', preLoginState, 'latestRefreshTimestamp:', latestRefreshTimestamp);
                let state = null;
                let slidesTimestamp = 0;
                try {
                    const slidesRes = await fetchWithRetry('/api/slides', 3, 2000);
                    const slidesData = await slidesRes.json();
                    slidesTimestamp = slidesData.length > 0 ? Math.max(...slidesData.map(s => new Date(s.headline?.timestamp).getTime() || 0)) : 0;
                } catch (e) {
                    console.error('Failed to fetch slides for timestamp:', e);
                    slidesTimestamp = 0;
                }
                if (preLoginState) {
                    try {
                        state = JSON.parse(preLoginState);
                        console.log('Using preLoginState:', state);
                        localStorage.setItem('educationState', preLoginState);
                        localStorage.removeItem('preLoginState');
                    } catch (e) {
                        console.error('Error parsing preLoginState:', e);
                    }
                } else if (savedState) {
                    try {
                        state = JSON.parse(savedState);
                        console.log('Using educationState:', state);
                    } catch (e) {
                        console.error('Error parsing educationState:', e);
                    }
                }
                if (state && slidesTimestamp) {
                    const storedDate = new Date(state.refreshTimestamp).toDateString();
                    const currentDate = new Date(slidesTimestamp).toDateString();
                    if (storedDate === currentDate) {
                        slides = state.slides || [];
                        currentSlide = state.currentSlide || 0;
                        questions = state.questions || [];
                        currentQuestion = state.currentQuestion || 0;
                        answers = state.answers || [];
                        if (state.pendingQuizSubmission && questions.length > 0 && !localStorage.getItem('quizSubmitted')) {
                            try {
                                const quizId = state.quizId || questions[0]?.id;
                                if (!quizId) throw new Error('No valid quizId found');
                                console.log('Attempting to submit pending quiz score for quizId:', quizId);
                                const score = calculateScore();
                                const res = await fetchWithRetry(`/api/submit_quiz/${quizId}`, 3, 2000, {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ score })
                                });
                                const data = await res.json();
                                localStorage.setItem('quizSubmissionMessage', data.message);
                                if (data.saved) {
                                    localStorage.setItem('quizSubmitted', 'true');
                                }
                                localStorage.setItem('educationState', JSON.stringify({
                                    ...state,
                                    pendingQuizSubmission: false,
                                    quizId
                                }));
                                console.log('Pending quiz submitted, updated educationState:', localStorage.getItem('educationState'));
                                localStorage.setItem('currentSection', 'results');
                                showResults(false);
                                return;
                            } catch (e) {
                                console.error('Failed to submit pending quiz score:', e);
                                localStorage.setItem('quizSubmissionMessage', 'Error submitting score. Please try again.');
                                localStorage.setItem('currentSection', 'results');
                                showResults(false);
                                return;
                            }
                        }
                        if (section === 'results' || (questions.length > 0 && currentQuestion >= questions.length)) {
                            localStorage.setItem('currentSection', 'results');
                            showResults(false);
                        } else if (questions.length > 0 && currentQuestion < questions.length) {
                            showQuestion(currentQuestion);
                        } else if (slides.length > 0) {
                            showSlide(currentSlide);
                        } else {
                            educationContent.innerHTML = '';
                            startEducation();
                        }
                    } else {
                        console.log('Clearing educationState due to date mismatch:', storedDate, currentDate);
                        clearUserState();
                        educationContent.innerHTML = '';
                        startEducation();
                    }
                } else {
                    educationContent.innerHTML = '';
                    startEducation();
                }
            };
            requestAnimationFrame(updateEducationDOM);
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const educationContent = document.getElementById('education-content');
    const startEducationBtn = document.getElementById('start-education');
    const toggleWeekly = document.getElementById('toggle-weekly');
    const toggleAlltime = document.getElementById('toggle-alltime');
    const toggleTeam = document.getElementById('toggle-team');
    const modeToggle = document.getElementById('mode-toggle');
    const headerTitle = document.getElementById('header-title');
    // Apply theme immediately to prevent flicker
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light');
    }
    if (modeToggle) {
        modeToggle.innerHTML = savedTheme === 'light' ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
    }
    preserveScroll(() => {
        typeTitle(headerTitle, 'Cyber Awareness');
        if (educationContent) educationContent.innerHTML = '';
        if (startEducationBtn) startEducationBtn.style.display = 'none';
    });
    if (startEducationBtn) {
        startEducationBtn.addEventListener('click', () => {
            preserveScroll(() => startEducation());
        });
    }
    if (toggleWeekly) {
        toggleWeekly.addEventListener('click', () => {
            preserveScroll(() => {
                currentScope = 'weekly';
                toggleWeekly.classList.add('active');
                if (toggleAlltime) toggleAlltime.classList.remove('active');
                if (toggleTeam) toggleTeam.classList.remove('active');
                loadLeaderboard();
                localStorage.setItem('lastSection', 'leaderboard');
            });
        });
    }
    if (toggleAlltime) {
        toggleAlltime.addEventListener('click', () => {
            preserveScroll(() => {
                currentScope = 'alltime';
                toggleAlltime.classList.add('active');
                if (toggleWeekly) toggleWeekly.classList.remove('active');
                if (toggleTeam) toggleTeam.classList.remove('active');
                loadLeaderboard();
                localStorage.setItem('lastSection', 'leaderboard');
            });
        });
    }
    if (toggleTeam) {
        toggleTeam.addEventListener('click', () => {
            preserveScroll(() => {
                currentScope = 'team';
                toggleTeam.classList.add('active');
                if (toggleWeekly) toggleWeekly.classList.remove('active');
                if (toggleAlltime) toggleAlltime.classList.remove('active');
                loadLeaderboard();
                localStorage.setItem('lastSection', 'leaderboard');
            });
        });
    }
    if (modeToggle) {
        modeToggle.addEventListener('click', () => {
            preserveScroll(() => toggleMode());
        });
    }
    document.querySelectorAll('a[data-section]').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            preserveScroll(() => {
                const section = e.target.getAttribute('data-section');
                localStorage.setItem('lastSection', section);
                showSection(section);
            });
        });
    });
    document.querySelectorAll('.nav-signin').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            preserveScroll(() => {
                const section = localStorage.getItem('currentSection') || 'home';
                localStorage.setItem('returnToSection', section);
                if (link.id === 'login-google') {
                    startGoogleLogin();
                } else if (link.id === 'login-microsoft') {
                    startMicrosoftLogin();
                }
            });
        });
    });
});

window.addEventListener('popstate', (event) => {
    preserveScroll(() => {
        const path = window.location.pathname.replace(/^\/|\/$/g, '');
        const parts = path.split('/');
        let section = parts[0] || 'home';
        let username = null;
        if (section === 'profile' && parts[1]) {
            username = decodeURIComponent(parts[1]);
        }
        if (path === 'logout') {
            clearUserState();
            section = 'home';
        }
        localStorage.setItem('lastSection', section);
        localStorage.removeItem('returnToSection');
        showSection(section, username);
    });
});

(async () => {
    if (document.cookie.includes('clearLocalStorage=true')) {
        clearUserState();
        document.cookie = 'clearLocalStorage=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    }
    try {
        const refreshResponse = await fetchWithRetry('/api/latest_refresh', 3, 2000);
        const refreshData = await refreshResponse.json();
        const refreshTime = refreshData.timestamp ? new Date(refreshData.timestamp * 1000).toISOString() : null;
        latestRefreshTimestamp = (refreshData.timestamp || 0) * 1000;
        requestAnimationFrame(() => {
            const contentRefresh = document.getElementById('content-refresh');
            const currentYear = document.getElementById('current-year');
            if (contentRefresh && refreshTime && !isNaN(new Date(refreshTime).getTime())) {
                contentRefresh.innerHTML = formatDate(refreshTime);
            } else {
                contentRefresh.innerHTML = 'Unknown';
            }
            if (currentYear) currentYear.textContent = new Date().getFullYear();
            console.log('Content refresh styles:', contentRefresh ? window.getComputedStyle(contentRefresh).display : 'not found');
            console.log('Initial latestRefreshTimestamp:', latestRefreshTimestamp);
        });
        await fetchQuizCount();
    } catch (error) {
        console.error('Error fetching latest refresh:', error);
        requestAnimationFrame(() => {
            const contentRefresh = document.getElementById('content-refresh');
            const currentYear = document.getElementById('current-year');
            if (contentRefresh) contentRefresh.innerHTML = 'Unknown';
            if (currentYear) currentYear.textContent = new Date().getFullYear();
            console.log('Content refresh styles:', contentRefresh ? window.getComputedStyle(contentRefresh).display : 'not found');
            latestRefreshTimestamp = 0;
        });
    }
    const path = window.location.pathname.replace(/^\/|\/$/g, '');
    const parts = path.split('/');
    let section = parts[0] || 'home';
    let username = null;
    if (section === 'profile' && parts[1]) {
        username = decodeURIComponent(parts[1]);
    }
    if (path === 'logout') {
        clearUserState();
        section = 'home';
    }
    const savedSection = localStorage.getItem('lastSection');
    const validSections = ['home', 'profile', 'leaderboard', 'results'];
    if (savedSection && validSections.includes(savedSection) && path !== 'logout') {
        section = savedSection;
        if (savedSection === 'profile') {
            try {
                const res = await fetchWithRetry('/api/user_status', 3, 2000);
                const data = await res.json();
                if (data.user && data.user.username) {
                    username = data.user.username;
                } else {
                    section = 'home';
                }
            } catch (e) {
                console.error('Failed to fetch user status for saved section:', e);
                section = 'home';
            }
        }
    }
    localStorage.removeItem('returnToSection');
    await showSection(section, username);
    await fetchUserTeamStatus();
})();