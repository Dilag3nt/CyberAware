export async function loadLeaderboard() {
    const leaderboardContent = document.getElementById('leaderboard-content');
    const userRankDiv = document.getElementById('user-rank');
    const statsEl = document.getElementById('leaderboard-stats');
    if (!leaderboardContent || !userRankDiv || !statsEl) return;
    preserveScroll(async () => {
        console.debug('loadLeaderboard: script version 20250920c');
        try {
            const userStatusRes = await fetchWithRetry('/api/user_status', 3, 2000);
            const userStatus = await userStatusRes.json();
            const isLoggedIn = !!userStatus.user;
            const res = await fetchWithRetry(`/api/leaderboard?scope=${currentScope}`, 3, 2000);
            const data = await res.json();
            if (data.error) {
                leaderboardContent.innerHTML = `<p>${data.error}</p>`;
                statsEl.innerHTML = '';
                return;
            }
            let html = '<table class="leaderboard-table">';
            if (data.leaders.length === 0) {
                html += '<tr><td colspan="7">No scores yet — take the quiz!</td></tr>';
            } else {
                html += '<tr><th>Rank</th><th>Username</th><th class="desktop-only">Quizzes</th><th class="desktop-only">Perfect</th><th class="desktop-only">Avg</th><th>Total</th><th>Last Quiz</th></tr>';
                data.leaders.forEach((leader, i) => {
                    const rankSymbol = i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${leader.rank}`;
                    const usernameCell = `<a href="#" onclick="showSection('profile', '${encodeURIComponent(leader.username)}'); return false;">${leader.username}</a>`;
                    let lastQuizDisplay = leader.last_quiz || 'Never';
                    let isInactive = !leader.last_quiz;
                    console.debug('Raw leader row:', { username: leader.username, last_quiz: leader.last_quiz });
                    if (leader.last_quiz) {
                        const lastQuizDate = new Date(leader.last_quiz);
                        if (isNaN(lastQuizDate.getTime())) {
                            console.error('Invalid last_quiz date:', leader.last_quiz);
                            lastQuizDisplay = 'Unknown';
                            isInactive = false;
                        } else {
                            const now = new Date();
                            const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
                            const quizDay = new Date(lastQuizDate.getFullYear(), lastQuizDate.getMonth(), lastQuizDate.getDate());
                            const daysDiff = Math.floor((today - quizDay) / (1000 * 60 * 60 * 24));
                            isInactive = daysDiff > 30;
                            lastQuizDisplay = formatDate(leader.last_quiz);
                        }
                    }
                    html += `<tr class="rank-${i + 1}"><td>${rankSymbol}</td><td>${usernameCell}</td><td class="desktop-only">${leader.quizzes_taken}</td><td class="desktop-only">${leader.perfect_quizzes}</td><td class="desktop-only">${leader.avg_score}</td><td>${leader.total_score}</td><td class="${isInactive ? 'inactive' : ''}">${lastQuizDisplay}</td></tr>`;
                });
            }
            html += '</table>';
            if (data.user_rank) {
                userRankDiv.innerHTML = `<p>You: #${data.user_rank.rank}, ${data.user_rank.total_score} points</p>`;
            } else {
                userRankDiv.innerHTML = '<p>You: Unranked</p>';
            }
            leaderboardContent.innerHTML = html;
            if (data.team_stats) {
                statsEl.innerHTML = `
                    <div class="team-stats">
                        Team Total: ${data.team_stats.team_total} |
                        Team Avg: ${data.team_stats.team_avg} |
                        Team Perfects: ${data.team_stats.team_perfects} |
                        Members: ${data.team_stats.members}
                    </div>
                `;
            } else {
                statsEl.innerHTML = '';
            }
            leaderboardContent.style.opacity = '0';
            setTimeout(() => {
                leaderboardContent.style.opacity = '1';
            }, 50);
        } catch (e) {
            console.error('Leaderboard fetch error:', e);
            leaderboardContent.innerHTML = '<p>Error loading leaderboard</p>';
            statsEl.innerHTML = '';
        }
    });
}