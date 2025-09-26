import { preserveScroll, fetchWithRetry, formatDate, showToast, debounce } from './utils.js';

export async function loadProfile(username = null) {
    const profileContent = document.getElementById('profile-content');
    const quizHistoryContent = document.getElementById('quiz-history-content');
    if (!profileContent) return;
    preserveScroll(async () => {
        profileContent.innerHTML = '<p>Loading profile...</p>';
        try {
            let targetUsername = username;
            let userStatus = { user: null };
            try {
                const userStatusRes = await fetchWithRetry('/api/user_status', 3, 2000);
                userStatus = await userStatusRes.json();
            } catch (e) {
                console.error('User status fetch error:', e);
                userStatus = { user: null };
            }
            if (!targetUsername) {
                targetUsername = userStatus.user ? userStatus.user.username : null;
                if (!targetUsername) {
                    profileContent.innerHTML = '<p>Please log in to view your profile</p>';
                    if (quizHistoryContent) quizHistoryContent.innerHTML = '';
                    return;
                }
            }
            const res = await fetchWithRetry(`/api/profile/${encodeURIComponent(targetUsername)}`, 3, 2000);
            const data = await res.json();
            console.log('Profile data:', data);
            if (data.error) {
                profileContent.innerHTML = `<p>${data.error}</p>`;
                if (quizHistoryContent) quizHistoryContent.innerHTML = '';
                return;
            }
            let lastQuizDisplay = data.profile_data.last_quiz || 'None';
            if (data.profile_data.last_quiz && data.profile_data.last_quiz !== 'Unknown') {
                const lastQuizDate = new Date(data.profile_data.last_quiz);
                if (isNaN(lastQuizDate.getTime())) {
                    console.error('Invalid last_quiz date:', data.profile_data.last_quiz);
                    lastQuizDisplay = 'Unknown';
                } else {
                    const now = new Date();
                    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                    const quizDay = new Date(lastQuizDate.getFullYear(), lastQuizDate.getMonth(), lastQuizDate.getDate());
                    const daysDiff = Math.floor((today - quizDay) / (1000 * 60 * 60 * 24));
                    const formattedDate = formatDate(data.profile_data.last_quiz);
                    if (daysDiff > 0) {
                        const dayText = daysDiff === 1 ? 'day' : 'days';
                        lastQuizDisplay = `${daysDiff} ${dayText} ago (${formattedDate})`;
                    } else {
                        lastQuizDisplay = formattedDate;
                    }
                }
            }
            profileContent.innerHTML = `
                <p><strong>Username:</strong> <span id="profile-username">${data.profile_data.username}</span></p>
                <p><strong>Bio:</strong> <span id="profile-bio">${data.profile_data.bio || 'No bio yet'}</span></p>
                <p><strong>Domain:</strong> <span id="profile-domain">${data.profile_data.domain || 'None'}</span></p>
                <p><strong>Team Joined:</strong> <span id="profile-join-team">${data.profile_data.join_team ? 'Yes' : 'No'}</span></p>
                <p><strong>Public Leaderboard Joined:</strong> <span id="profile-join-public">${data.profile_data.join_public ? 'Yes' : 'No'}</span></p>
                <p><strong>Rank:</strong> <span id="profile-rank">${data.profile_data.rank || 'Unranked'}</span></p>
                <p><strong>Total Score:</strong> <span id="profile-total-score">${data.profile_data.total_score || 0}</span></p>
                <p><strong>Quizzes Taken:</strong> <span id="profile-quizzes-taken">${data.profile_data.quizzes_taken || 0}</span></p>
                <p><strong>Average Score:</strong> <span id="profile-avg-score">${data.profile_data.avg_score || 0}</span></p>
                <p><strong>Perfect Quizzes:</strong> <span id="profile-perfect-quizzes">${data.profile_data.perfect_quizzes || 0}</span></p>
                <p><strong>Last Quiz:</strong> <span id="profile-last-quiz">${lastQuizDisplay}</span></p>
            `;
            if (userStatus.user && userStatus.user.username === data.profile_data.username) {
                preserveScroll(() => {
                    profileContent.innerHTML += `
                        <button id="edit-profile-btn" onclick="toggleEditProfile()">Edit Profile</button>
                        <div id="edit-profile-form" style="display: none;">
                            <div class="input-wrapper">
                                <div class="input-container">
                                    <input id="edit-username" type="text" placeholder="New username (5-30 chars)" maxlength="30" value="${data.profile_data.username}">
                                    <span class="char-count" id="username-count">${data.profile_data.username.length}/30</span>
                                </div>
                                <span id="username-error"></span>
                            </div>
                            <div class="input-wrapper">
                                <div class="input-container">
                                    <input id="edit-bio" type="text" placeholder="Bio (max 100 chars)" maxlength="100" value="${data.profile_data.bio || ''}">
                                    <span class="char-count" id="bio-count">${(data.profile_data.bio || '').length}/100</span>
                                </div>
                                <span id="bio-error"></span>
                            </div>
                            <div id="join-team-container">
                                <label for="join-team">Join team leaderboard:</label>
                                <input type="checkbox" id="join-team" class="team-toggle-switch" ${data.profile_data.join_team ? 'checked' : ''}>
                            </div>
                            <div id="join-public-container">
                                <label for="join-public">Join public leaderboard:</label>
                                <input type="checkbox" id="join-public" class="team-toggle-switch" ${data.profile_data.join_public ? 'checked' : ''}>
                            </div>
                            <button id="save-profile-btn" onclick="updateProfile()">Save</button>
                        </div>
                        <div id="quiz-history-content"></div>
                    `;
                    const usernameInput = document.getElementById('edit-username');
                    const bioInput = document.getElementById('edit-bio');
                    const usernameCount = document.getElementById('username-count');
                    const bioCount = document.getElementById('bio-count');
                    const saveButton = document.getElementById('save-profile-btn');
                    let currentUsername = data.profile_data.username;
                    async function validateUsername(value) {
                        const errorEl = document.getElementById('username-error');
                        if (!errorEl) return true;
                        if (value.length < 5 || value.length > 30) {
                            errorEl.textContent = 'Username must be 5-30 characters';
                            saveButton.disabled = true;
                            return false;
                        }
                        if (!/^[a-zA-Z0-9_]+$/.test(value)) {
                            errorEl.textContent = 'Username must be alphanumeric or underscore';
                            saveButton.disabled = true;
                            return false;
                        }
                        if (value !== currentUsername) {
                            try {
                                const res = await fetchWithRetry('/api/check_username', 3, 2000, {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ username: value })
                                });
                                const data = await res.json();
                                if (data.error) {
                                    errorEl.textContent = data.error;
                                    saveButton.disabled = true;
                                    return false;
                                }
                            } catch (e) {
                                console.error('Username check failed:', e);
                                errorEl.textContent = 'Error checking username availability';
                                saveButton.disabled = true;
                                return false;
                            }
                        }
                        errorEl.textContent = '';
                        saveButton.disabled = false;
                        return true;
                    }
                    function validateBio(value) {
                        const errorEl = document.getElementById('bio-error');
                        if (!errorEl) return true;
                        if (value.length > 100) {
                            errorEl.textContent = 'Bio must be 100 characters or less';
                            saveButton.disabled = true;
                            return false;
                        }
                        errorEl.textContent = '';
                        saveButton.disabled = !validateUsername(usernameInput?.value || '');
                        return true;
                    }
                    if (usernameInput) {
                        usernameInput.addEventListener('input', debounce(async () => {
                            const value = usernameInput.value;
                            const usernameCount = document.getElementById('username-count');
                            if (usernameCount) usernameCount.textContent = `${value.length}/30`;
                            await validateUsername(value);
                            if (usernameCount) {
                                usernameCount.style.display = 'none';
                                usernameCount.offsetHeight;
                                usernameCount.style.display = 'block';
                            }
                        }, 500));
                        usernameInput.addEventListener('focus', () => {
                            currentUsername = usernameInput.value;
                        });
                    }
                    if (bioInput) {
                        bioInput.addEventListener('input', () => {
                            const value = bioInput.value;
                            const bioCount = document.getElementById('bio-count');
                            if (bioCount) bioCount.textContent = `${value.length}/100`;
                            validateBio(value);
                            if (bioCount) {
                                bioCount.style.display = 'none';
                                bioCount.offsetHeight;
                                bioCount.style.display = 'block';
                            }
                        });
                    }
                    validateUsername(usernameInput?.value || '');
                    validateBio(bioInput?.value || '');
                    if (usernameCount) {
                        usernameCount.style.display = 'none';
                        usernameCount.offsetHeight;
                        usernameCount.style.display = 'block';
                    }
                    if (bioCount) {
                        bioCount.style.display = 'none';
                        bioCount.offsetHeight;
                        bioCount.style.display = 'block';
                    }
                    const joinTeamToggle = document.getElementById('join-team');
                    const joinPublicToggle = document.getElementById('join-public');
                    if (joinTeamToggle) {
                        joinTeamToggle.addEventListener('change', () => {
                            preserveScroll(() => updateTeamStatus(joinTeamToggle.checked));
                        });
                    }
                    if (joinPublicToggle) {
                        joinPublicToggle.addEventListener('change', () => {
                            preserveScroll(() => updatePublicStatus(joinPublicToggle.checked));
                        });
                    }
                });
                preserveScroll(() => loadQuizHistory(1));
            } else if (quizHistoryContent) {
                preserveScroll(() => {
                    profileContent.innerHTML += '<div id="quiz-history-content"></div>';
                    quizHistoryContent.innerHTML = '';
                });
            }
        } catch (e) {
            console.error('Profile fetch error:', e);
            profileContent.innerHTML = '<p>Error loading profile</p>';
            if (quizHistoryContent) quizHistoryContent.innerHTML = '';
        }
    });
}

export function toggleEditProfile() {
    const editForm = document.getElementById('edit-profile-form');
    if (editForm) editForm.style.display = editForm.style.display === 'none' ? 'block' : 'none';
}

export async function updateProfile() {
    const username = document.getElementById('edit-username')?.value;
    const bio = document.getElementById('edit-bio')?.value;
    const join_team = document.getElementById('join-team') ? document.getElementById('join-team').checked : false;
    const join_public = document.getElementById('join-public') ? document.getElementById('join-public').checked : false;
    preserveScroll(async () => {
        try {
            const res = await fetchWithRetry('/api/update_profile', 3, 2000, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, bio, join_team, join_public })
            });
            const data = await res.json();
            if (data.error) {
                showToast(`Error updating profile: ${data.error}`, 'error');
            } else {
                const userInfo = document.getElementById('user-info');
                if (userInfo) userInfo.innerHTML = `Welcome, ${data.username} | <a href="/logout">Sign out</a>`;
                await loadProfile(data.username);
                toggleEditProfile();
                const newUrlPath = `/profile/${encodeURIComponent(data.username)}`;
                history.pushState({ section: 'profile', username: data.username }, '', newUrlPath);
                showToast('Profile updated successfully', 'success');
                await fetchUserTeamStatus();
            }
        } catch (e) {
            console.error('Error updating profile:', e);
            showToast('Error updating profile', 'error');
        }
    });
}

export async function updateTeamStatus(join_team) {
    const joinTeamToggle = document.getElementById('join-team');
    if (!joinTeamToggle) return false;
    const originalState = joinTeamToggle.checked;
    try {
        const res = await fetchWithRetry('/api/update_team_status', 3, 2000, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ join_team })
        });
        const data = await res.json();
        if (data.error) {
            console.error('Failed to update team status:', data.error);
            showToast(`Error updating team status: ${data.error}`, 'error');
            joinTeamToggle.checked = !originalState;
            return false;
        }
        const profileJoinTeam = document.getElementById('profile-join-team');
        if (profileJoinTeam) profileJoinTeam.textContent = data.join_team ? 'Yes' : 'No';
        if (data.join_team) {
            showToast('You have joined the team leaderboard.', 'info');
        } else {
            showToast('You have left the team leaderboard.', 'info');
        }
        await fetchUserTeamStatus();
        return true;
    } catch (e) {
        console.error('Failed to update team status:', e);
        showToast('Error updating team status', 'error');
        joinTeamToggle.checked = !originalState;
        return false;
    }
}

export async function updatePublicStatus(join_public) {
    const joinPublicToggle = document.getElementById('join-public');
    if (!joinPublicToggle) return false;
    const originalState = joinPublicToggle.checked;
    try {
        const res = await fetchWithRetry('/api/update_public_status', 3, 2000, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ join_public })
        });
        const data = await res.json();
        if (data.error) {
            console.error('Failed to update public status:', data.error);
            showToast(`Error updating public leaderboard status: ${data.error}`, 'error');
            joinPublicToggle.checked = !originalState;
            return false;
        }
        const profileJoinPublic = document.getElementById('profile-join-public');
        if (profileJoinPublic) profileJoinPublic.textContent = data.join_public ? 'Yes' : 'No';
        if (!data.join_public) {
            showToast('Your scores are now private and not shown on the public leaderboard.', 'info');
        } else {
            showToast('Your scores are now visible on the public leaderboard.', 'info');
        }
        return true;
    } catch (e) {
        console.error('Failed to update public status:', e);
        showToast('Error updating public leaderboard status', 'error');
        joinPublicToggle.checked = !originalState;
        return false;
    }
}

export async function loadQuizHistory(page = 1) {
    const quizHistoryContent = document.getElementById('quiz-history-content');
    if (!quizHistoryContent) return;
    preserveScroll(async () => {
        try {
            let username = 'User';
            try {
                const userStatusRes = await fetchWithRetry('/api/user_status', 3, 2000);
                const userStatus = await userStatusRes.json();
                if (userStatus.user && userStatus.user.username) {
                    username = userStatus.user.username;
                }
            } catch (e) {
                console.error('User status fetch error for quiz history:', e);
            }
            const res = await fetchWithRetry(`/api/quiz_history?page=${page}`, 3, 2000);
            const data = await res.json();
            console.log('Quiz history data:', data);
            if (data.error) {
                quizHistoryContent.innerHTML = `<p>${data.error}</p>`;
                return;
            }
            let html = `<h3 class="section-title">${username}'s Quiz History</h3>`;
            if (data.history.length === 0) {
                html += '<p>No quizzes taken yet—start one on the home page!</p>';
            } else {
                html += '<table class="leaderboard-table quiz-history-table">';
                html += '<tr><th>Quiz Date</th><th>Taken</th><th>Score</th><th>Status</th></tr>';
                data.history.forEach(row => {
                    console.log('Raw quiz history row:', { quiz_date: row.quiz_date, taken: row.taken });
                    const quizDateFormatted = formatDate(row.quiz_date);
                    const takenFormatted = formatDate(row.taken);
                    console.log('Formatted dates:', { quizDate: quizDateFormatted, taken: takenFormatted });
                    const isPass = (row.score <= 69 && row.score >= 48) || (row.score > 69 && row.score >= 80);
                    const isPerfect = row.score === 69 || row.score === 100;
                    const status = isPass
                        ? `<i class="fas fa-check pass"></i>${isPerfect ? ' <i class="fas fa-star perfect"></i>' : ''}`
                        : '<i class="fas fa-times fail"></i>';
                    html += `<tr><td>${quizDateFormatted}</td><td>${takenFormatted}</td><td>${row.score}</td><td>${status}</td></tr>`;
                });
                html += '</table>';
                const totalPages = Math.ceil(data.total / data.limit);
                html += '<div class="pagination">';
                html += `<button class="nav-button" id="prev-history" onclick="loadQuizHistory(${page - 1})" ${page === 1 ? 'disabled' : ''}>Previous</button>`;
                html += `<span>Page ${page} of ${totalPages}</span>`;
                html += `<button class="nav-button" id="next-history" onclick="loadQuizHistory(${page + 1})" ${page >= totalPages ? 'disabled' : ''}>Next</button>`;
                html += '</div>';
            }
            quizHistoryContent.innerHTML = html;
        } catch (e) {
            console.error('Quiz history fetch error:', e);
            quizHistoryContent.innerHTML = '<p>Error loading quiz history</p>';
        }
    });
}