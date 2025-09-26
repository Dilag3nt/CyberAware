let slides = [];
let questions = [];
let currentSlide = 0;
let currentQuestion = 0;
let answers = [];

function calculateScore() {
    let score = 0;
    questions.forEach((q, i) => {
        if (answers[i] === q.correct) score += 20;
    });
    return score;
}

async function startEducation() {
    const startEducationBtn = document.getElementById('start-education');
    const educationContent = document.getElementById('education-content');
    if (!educationContent) return;
    preserveScroll(() => {
        if (startEducationBtn) startEducationBtn.style.display = 'none';
        educationContent.innerHTML = '<p>Loading slides... <span id="slide-progress">0%</span></p>';
        let startTime = performance.now();
        let animationId;
        function updateProgress(timestamp) {
            const elapsed = timestamp - startTime;
            const progress = Math.min((elapsed / 30000) * 100, 100);
            const progressElement = document.getElementById('slide-progress');
            if (progressElement) {
                progressElement.textContent = `${Math.round(progress)}%`;
            }
            if (progress < 100 && !document.hidden) {
                animationId = requestAnimationFrame(updateProgress);
            } else {
                cancelAnimationFrame(animationId);
            }
        }
        animationId = requestAnimationFrame(updateProgress);
        fetchWithRetry('/api/slides', 3, 2000).then(res => res.json()).then(data => {
            const slidesTimestamp = data.length > 0 ? Math.max(...data.map(s => new Date(s.headline?.timestamp).getTime() || 0)) : 0;
            console.log('Slides timestamp in startEducation:', slidesTimestamp);
            latestRefreshTimestamp = slidesTimestamp;
            educationContent.innerHTML = '';
            if (data.length === 0) {
                educationContent.innerHTML = '<p>No slides available. Retrying in 5 seconds...</p>';
                console.log('No slides available, retrying in 5 seconds');
                setTimeout(() => startEducation(), 5000);
            } else {
                slides = data.slice(0, 5);
                currentSlide = 0;
                questions = [];
                currentQuestion = 0;
                answers = [];
                showSlide(0);
                localStorage.setItem('educationState', JSON.stringify({
                    currentSlide,
                    slides,
                    currentQuestion,
                    questions,
                    answers,
                    refreshTimestamp: slidesTimestamp
                }));
                console.log('Saved educationState in startEducation:', localStorage.getItem('educationState'));
                console.log('Slides loaded:', slides);
            }
        }).catch(e => {
            educationContent.innerHTML = '<p>Error loading slides: ' + e.message + '. Retrying in 5 seconds...</p>';
            console.error('Slides fetch error:', e);
            setTimeout(() => startEducation(), 5000);
        });
    });
}

async function startQuiz() {
    const educationContent = document.getElementById('education-content');
    if (!educationContent) return;
    preserveScroll(() => {
        const quizId = questions[0]?.id || (fetchWithRetry('/api/quiz').then(res => res.json()).then(data => data[0]?.id));
        educationContent.innerHTML = '<p>Loading quiz... <span id="quiz-progress">0%</span></p>';
        let startTime = performance.now();
        let animationId;
        function updateProgress(timestamp) {
            const elapsed = timestamp - startTime;
            const progress = Math.min((elapsed / 30000) * 100, 100);
            const progressElement = document.getElementById('quiz-progress');
            if (progressElement) {
                progressElement.textContent = `${Math.round(progress)}%`;
            }
            if (progress < 100 && !document.hidden) {
                animationId = requestAnimationFrame(updateProgress);
            } else {
                cancelAnimationFrame(animationId);
            }
        }
        animationId = requestAnimationFrame(updateProgress);
        fetchWithRetry('/api/quiz', 3, 2000).then(res => res.json()).then(data => {
            if (!data || data.length === 0) {
                throw new Error('Empty quiz response');
            }
            educationContent.innerHTML = '';
            questions = data;
            currentQuestion = 0;
            answers = new Array(questions.length).fill(null);
            localStorage.removeItem('quizSubmitted');
            localStorage.removeItem('quizCountUpdated');
            showQuestion(0);
            localStorage.setItem('educationState', JSON.stringify({
                currentSlide,
                slides,
                currentQuestion,
                questions,
                answers,
                refreshTimestamp: latestRefreshTimestamp,
                quizId
            }));
            console.log('Saved educationState in startQuiz:', localStorage.getItem('educationState'));
        }).catch(e => {
            educationContent.innerHTML = '<p>Error loading quiz: ' + e.message + '. Retrying in 5 seconds...</p>';
            console.error('Quiz fetch error:', e);
            setTimeout(() => startQuiz(), 5000);
        });
    });
}

function showSlide(index) {
    if (index < 0 || index >= slides.length) {
        console.log('Invalid slide index:', index, 'slides length:', slides.length);
        return;
    }
    const educationContent = document.getElementById('education-content');
    if (!educationContent) return;
    preserveScroll(() => {
        const slide = slides[index];
        let html = '<div class="slide">';
        html += `<div class="slide-title">${slide.title}</div>`;
        if (index === 0 && localStorage.getItem('welcomeDismissed') !== 'true') {
            html += '<div class="welcome-message">Welcome to the Cyber Awareness Terminal. Explore frequently updated cyber threats and safety tips. Take a short quiz to test your knowledge. Optionally, sign in to save your score and join the leaderboard.<span class="dismiss-welcome" id="dismiss-welcome"><i class="fa-solid fa-square-xmark"></i></span></div>';
        }
        const sections = slide.content.split('\n');
        sections.forEach(section => {
            if (section.trim()) {
                html += `<div class="slide-section">${section.trim()}</div>`;
            }
        });
        if (slide.headline) {
            html += `<hr class="slide-reference"><div class="slide-reference">${slide.headline.description} <a href="${slide.headline.link}" target="_blank">read more</a><br><small>${slide.headline.source} - ${formatDate(slide.headline.published_date)}</small></div>`;
        }
        const progress = Array(slides.length).fill('-').map((_, i) => i === index ? '>' : '-').join('');
        html += `<p class="progress">[${progress}]</p>`;
        html += '<div class="nav-buttons">';
        if (index > 0) {
            html += `<button id="prev-slide-${index}" class="nav-button nav-button-left" title="Previous"><i class="fa-solid fa-square-caret-left"></i></button>`;
        }
        if (index < slides.length - 1) {
            html += `<button id="next-slide-${index}" class="nav-button nav-button-right" title="Next"><i class="fa-solid fa-square-caret-right"></i></button>`;
        } else {
            html += `<button id="next-slide-${index}" class="nav-button nav-button-right" title="Start Quiz"><i class="fa-solid fa-square-caret-right"></i></button>`;
        }
        html += '</div>';
        educationContent.innerHTML = html;
        if (index === 0 && localStorage.getItem('welcomeDismissed') !== 'true') {
            const dismissButton = document.getElementById('dismiss-welcome');
            if (dismissButton) {
                dismissButton.addEventListener('click', () => {
                    preserveScroll(() => {
                        localStorage.setItem('welcomeDismissed', 'true');
                        showSlide(index);
                    });
                });
            }
        }
        if (index > 0) {
            const prevButton = document.getElementById(`prev-slide-${index}`);
            if (prevButton) {
                prevButton.addEventListener('click', () => {
                    preserveScroll(() => {
                        currentSlide = index - 1;
                        showSlide(currentSlide);
                        localStorage.setItem('educationState', JSON.stringify({
                            currentSlide,
                            slides,
                            currentQuestion,
                            questions,
                            answers,
                            refreshTimestamp: latestRefreshTimestamp
                        }));
                        console.log('Saved educationState in showSlide (prev):', localStorage.getItem('educationState'));
                    });
                });
            }
        }
        if (index < slides.length - 1) {
            const nextButton = document.getElementById(`next-slide-${index}`);
            if (nextButton) {
                nextButton.addEventListener('click', () => {
                    preserveScroll(() => {
                        currentSlide = index + 1;
                        showSlide(currentSlide);
                        localStorage.setItem('educationState', JSON.stringify({
                            currentSlide,
                            slides,
                            currentQuestion,
                            questions,
                            answers,
                            refreshTimestamp: latestRefreshTimestamp
                        }));
                        console.log('Saved educationState in showSlide (next):', localStorage.getItem('educationState'));
                    });
                });
            }
        } else {
            const nextButton = document.getElementById(`next-slide-${index}`);
            if (nextButton) {
                nextButton.addEventListener('click', () => {
                    preserveScroll(() => startQuiz());
                });
            }
        }
        currentSlide = index;
    });
}

function showQuestion(index) {
    if (index >= questions.length) {
        showResults(true);
        return;
    }
    const educationContent = document.getElementById('education-content');
    if (!educationContent) return;
    preserveScroll(() => {
        const q = questions[index];
        console.log('Rendering question:', { question: q.question, options: q.options, correct: q.correct });
        const cleanOptions = q.options.map(opt => opt.replace(/^[A-D]\)\s*/, '').trim());
        const isTrueFalse = q.question.toLowerCase().startsWith('true or false') ||
                            (cleanOptions.length === 2 && cleanOptions.every(opt => ['true', 'false'].includes(opt.toLowerCase())));
        let displayOptions = cleanOptions;
        let correctIndex = q.correct;
        if (isTrueFalse) {
            displayOptions = ['True', 'False'];
            correctIndex = cleanOptions[q.correct]?.toLowerCase() === 'true' ? 0 : 1;
            q.question = q.question.replace(/\s*\(True\/False\)$/i, '').trim();
            console.log('Identified True/False question, corrected options:', displayOptions, 'correctIndex:', correctIndex, 'question:', q.question);
        } else {
            console.log('Non-True/False question, using original options:', cleanOptions);
        }
        const optionsWithIndices = displayOptions.map((opt, i) => ({ opt, index: i }));
        for (let i = optionsWithIndices.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [optionsWithIndices[i], optionsWithIndices[j]] = [optionsWithIndices[j], optionsWithIndices[i]];
        }
        const shuffledOptions = optionsWithIndices.map(item => item.opt);
        let html = '<div class="slide">';
        html += `<div class="slide-title">Question ${index + 1}</div>`;
        html += `<div class="slide-section">${q.question}</div><ul>`;
        shuffledOptions.forEach((opt, i) => {
            if (opt !== '') {
                html += `<li><button id="option-${index}-${i}" class="option-button">${String.fromCharCode(65 + i)}. ${opt}</button></li>`;
            }
        });
        html += '</ul>';
        const progress = Array(questions.length).fill('-').map((_, i) => i === index ? '>' : '-').join('');
        html += `<p class="progress">[${progress}]</p>`;
        html += '</div>';
        educationContent.innerHTML = html;
        for (let i = 0; i < shuffledOptions.length; i++) {
            if (shuffledOptions[i] !== '') {
                const optionButton = document.getElementById(`option-${index}-${i}`);
                if (optionButton) {
                    optionButton.addEventListener('click', () => {
                        preserveScroll(() => {
                            const originalIndex = optionsWithIndices[i].index;
                            selectAnswer(index, originalIndex);
                        });
                    });
                }
            }
        }
    });
}

function selectAnswer(index, ansIndex) {
    answers[index] = ansIndex;
    currentQuestion++;
    localStorage.setItem('educationState', JSON.stringify({
        currentSlide,
        slides,
        currentQuestion,
        questions,
        answers,
        refreshTimestamp: latestRefreshTimestamp
    }));
    console.log('Saved educationState in selectAnswer:', localStorage.getItem('educationState'));
    showQuestion(currentQuestion);
}

async function showResults(updateQuizCount = true) {
    const educationContent = document.getElementById('education-content');
    if (!educationContent) return;
    const startEducationBtn = document.getElementById('start-education');
    const quizId = questions[0]?.id;
    preserveScroll(async () => {
        let score = 0;
        let explanations = '';
        questions.forEach((q, i) => {
            if (answers[i] === q.correct) score += 20;
            else {
                explanations += `<p>Question ${i + 1}: Incorrect. ${q.explanation}</p>`;
            }
        });
        const percent = Math.min((score / 100) * 100, 100);
        const passed = (percent <= 69 && percent >= 48) || percent >= 80;
        let html = '<div class="slide">';
        html += `<div class="slide-section">Score: ${score}/100 (${percent.toFixed(0)}%) - ${passed ? 'Passed' : 'Failed'}</div>`;
        if (passed) {
            if (score === 100) {
                html += '<div class="slide-section"><b>Congratulations for passing the cyber awareness quiz with a perfect score!</b></div>';
            } else {
                html += '<div class="slide-section"><b>Congratulations for passing the cyber awareness quiz!</b></div>';
                html += '<div class="slide-section">Some questions were incorrect. Review the explanations below.</div>';
            }
        }
        html += explanations;
        html += '</div>';
        let message = localStorage.getItem('quizSubmissionMessage') || 'Sign in to save your score.';
        if (questions.length > 0 && !localStorage.getItem('quizSubmitted')) {
            localStorage.removeItem('quizSubmitted');
            localStorage.removeItem('quizSubmissionMessage');
            try {
                const res = await fetchWithRetry(`/api/submit_quiz/${quizId}`, 3, 2000, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ score })
                });
                const data = await res.json();
                message = data.message;
                localStorage.setItem('quizSubmissionMessage', data.message);
                if (data.saved) {
                    localStorage.setItem('quizSubmitted', 'true');
                }
            } catch (e) {
                console.error('Failed to submit quiz score:', e);
                message = 'Error submitting score. Please try again.';
                localStorage.setItem('quizSubmissionMessage', message);
            }
        }
        if (updateQuizCount && !localStorage.getItem('quizCountUpdated')) {
            try {
                console.log('Attempting quiz count update');
                const countRes = await fetchWithRetry('/api/update_quiz_count', 3, 2000, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const countData = await countRes.json();
                const quizCountSpan = document.getElementById('quiz-count');
                if (quizCountSpan) quizCountSpan.textContent = countData.count;
                console.log('Quiz count updated:', countData.count);
                localStorage.setItem('quizCountUpdated', 'true');
            } catch (e) {
                console.error('Failed to update quiz count:', e);
            }
        }
        html += `<div class="slide-section">${message}</div>`;
        html += '<button class="exit-quiz" id="exit-quiz">Continue</button>';
        educationContent.innerHTML = html;
        if (startEducationBtn) startEducationBtn.style.display = 'none';
        localStorage.setItem('educationState', JSON.stringify({
            currentSlide,
            slides,
            currentQuestion,
            questions,
            answers,
            refreshTimestamp: latestRefreshTimestamp,
            quizId,
            pendingQuizSubmission: false
        }));
        localStorage.setItem('currentSection', 'results');
        console.log('Saved educationState in showResults:', localStorage.getItem('educationState'));
        const exitQuizButton = document.getElementById('exit-quiz');
        if (exitQuizButton) {
            exitQuizButton.addEventListener('click', () => {
                preserveScroll(() => {
                    currentQuestion = 0;
                    questions = [];
                    answers = [];
                    showSlide(0);
                    localStorage.setItem('educationState', JSON.stringify({
                        currentSlide: 0,
                        slides,
                        currentQuestion: 0,
                        questions: [],
                        answers: [],
                        refreshTimestamp: latestRefreshTimestamp,
                        quizId
                    }));
                    localStorage.removeItem('quizSubmitted');
                    localStorage.removeItem('quizSubmissionMessage');
                    localStorage.removeItem('quizCountUpdated');
                    localStorage.setItem('currentSection', 'home');
                    console.log('Cleared quiz state and saved educationState after continue:', localStorage.getItem('educationState'));
                });
            });
        }
    });
}

function resetToMain() {
    clearUserState();
    slides = [];
    questions = [];
    currentSlide = 0;
    currentQuestion = 0;
    answers = [];
    const educationContent = document.getElementById('education-content');
    if (educationContent) educationContent.innerHTML = '';
    console.log('Resetting to main, fetching slides');
    showSection('home');
}

function restartEducation() {
    clearUserState();
    slides = [];
    questions = [];
    currentSlide = 0;
    currentQuestion = 0;
    answers = [];
    console.log('Restarting education, fetching slides');
    startEducation();
}