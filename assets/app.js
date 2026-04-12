
const DATA_URL = './data/faustball_data.json';
const state = { data: null, filter: 'Alle' };

const statusText = document.getElementById('status-text');
const statsBox = document.getElementById('stats');
const upcomingBox = document.getElementById('upcoming');
const nextCount = document.getElementById('next-count');
const filtersBox = document.getElementById('filters');
const teamsBox = document.getElementById('teams');
const noticeBox = document.getElementById('notice-box');
const reloadBtn = document.getElementById('reload-btn');

reloadBtn.addEventListener('click', loadData);

function parseDate(value, time = '00:00') {
  if (!value) return null;
  const [day, month, year] = value.split('.').map(Number);
  const [hour, minute] = (time || '00:00').split(':').map(Number);
  return new Date(year, month - 1, day, hour || 0, minute || 0, 0);
}

function formatDate(value, time) {
  const date = parseDate(value, time);
  if (!date) return value || '–';
  return new Intl.DateTimeFormat('de-DE', {
    weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric',
    hour: time ? '2-digit' : undefined,
    minute: time ? '2-digit' : undefined,
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function renderNotice() {
  noticeBox.className = 'card hidden';
  if (!state.data) return;
  const status = state.data.source_status || {};
  const notices = Array.isArray(state.data.notices) ? state.data.notices : [];
  const messages = [];
  if (status.message) messages.push(status.message);
  messages.push(...notices);
  if (!messages.length) return;
  noticeBox.className = `card notice ${status.live_ok ? '' : 'notice-error'}`;
  noticeBox.innerHTML = `<strong>Datenstatus</strong>${messages.map(msg => `<div>${escapeHtml(msg)}</div>`).join('')}`;
}

function buildStats(data) {
  const teams = data.teams || [];
  const standingsCount = teams.filter(team => (data.standings?.[team.id] || []).length > 0).length;
  const matchCount = Object.values(data.matches || {}).reduce((sum, list) => sum + (list?.length || 0), 0);
  const upcoming = (data.upcoming || []).slice().sort((a, b) => parseDate(a.date, a.time) - parseDate(b.date, b.time));
  const nextEvent = upcoming.find(item => parseDate(item.date, item.time) >= new Date()) || upcoming[0];
  const items = [
    ['Teams', teams.length, 'Mannschaften oder Altersklassen'],
    ['Mit Tabelle', standingsCount, 'Bereiche mit erkannter Tabelle'],
    ['Spiele', matchCount, 'Erkannte Resultate'],
    ['Nächster Termin', nextEvent ? nextEvent.ageGroup : '–', nextEvent ? formatDate(nextEvent.date, nextEvent.time) : 'Kein Termin'],
  ];
  statsBox.innerHTML = items.map(([label, value, sub]) => `
    <article class="stat">
      <div class="stat-label">${escapeHtml(label)}</div>
      <div class="stat-value">${escapeHtml(value)}</div>
      <div class="stat-sub">${escapeHtml(sub)}</div>
    </article>
  `).join('');
}

function renderUpcoming(data) {
  const upcoming = (data.upcoming || []).slice().sort((a, b) => parseDate(a.date, a.time) - parseDate(b.date, b.time));
  nextCount.textContent = `${upcoming.length} Einträge`;
  if (!upcoming.length) {
    upcomingBox.innerHTML = '<div class="empty">Keine Termine vorhanden.</div>';
    return;
  }
  upcomingBox.innerHTML = `<div class="upcoming-list">${upcoming.map(item => `
    <article class="upcoming-item">
      <strong>${escapeHtml(item.competition || item.ageGroup || 'Termin')}</strong>
      <div>${escapeHtml(formatDate(item.date, item.time))}</div>
      <div class="meta">${escapeHtml([item.venue, item.location].filter(Boolean).join(' · '))}</div>
    </article>
  `).join('')}</div>`;
}

function renderFilters(data) {
  const groups = ['Alle', ...new Set((data.teams || []).map(team => team.ageGroup).filter(Boolean))];
  filtersBox.innerHTML = groups.map(group => `<button class="chip ${group === state.filter ? 'active' : ''}" data-filter="${escapeHtml(group)}">${escapeHtml(group)}</button>`).join('');
  filtersBox.querySelectorAll('[data-filter]').forEach(button => {
    button.addEventListener('click', () => {
      state.filter = button.dataset.filter;
      renderFilters(data);
      renderTeams(data);
    });
  });
}

function standingsSummary(rows) {
  if (!rows?.length) return 'Keine Tabelle vorhanden';
  const own = rows.find(row => row.isOurTeam) || rows[0];
  if (!own) return 'Keine Tabelle vorhanden';
  return `Platz ${own.position || '–'} · ${own.pointsWon ?? '–'}:${own.pointsLost ?? '–'} Punkte`;
}

function renderTeams(data) {
  const teams = (data.teams || []).filter(team => state.filter === 'Alle' || team.ageGroup === state.filter);
  if (!teams.length) {
    teamsBox.innerHTML = '<div class="empty">Keine Teams für diesen Filter.</div>';
    return;
  }
  teamsBox.innerHTML = teams.map(team => {
    const standings = data.standings?.[team.id] || [];
    const matches = data.matches?.[team.id] || [];
    const squad = team.squad || [];
    const badges = [...(team.achievements || [])].slice(0, 6);
    return `
      <article class="team-card">
        <div class="team-top">
          <div class="team-title">
            <h2>${escapeHtml(team.label || team.id)}</h2>
            <div class="meta">${escapeHtml([team.clubName, team.league, team.gender].filter(Boolean).join(' · '))}</div>
            <div class="meta">${escapeHtml(standingsSummary(standings))}</div>
            ${badges.length ? `<div class="badges">${badges.map(item => `<span class="badge">${escapeHtml(item)}</span>`).join('')}</div>` : ''}
          </div>
          <a class="footer-link" href="${escapeHtml(team.faustballUrl || '#')}" target="_blank" rel="noopener noreferrer">Offizielle Quelle</a>
        </div>
        <div class="team-grid">
          <section class="panel">
            <h3>Tabelle</h3>
            ${standings.length ? `
            <div class="table-wrap">
              <table>
                <thead>
                  <tr><th>#</th><th>Team</th><th>Sp</th><th>Sätze</th><th>Punkte</th></tr>
                </thead>
                <tbody>
                  ${standings.map(row => `
                    <tr class="${row.isOurTeam ? 'our-team' : ''}">
                      <td>${escapeHtml(row.position ?? '–')}</td>
                      <td>${escapeHtml(row.teamName || row.name || '–')}</td>
                      <td>${escapeHtml(row.played ?? '–')}</td>
                      <td>${escapeHtml(`${row.setsWon ?? '–'}:${row.setsLost ?? '–'}`)}</td>
                      <td>${escapeHtml(`${row.pointsWon ?? '–'}:${row.pointsLost ?? '–'}`)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>` : '<div class="empty">Keine Tabellendaten vorhanden.</div>'}
          </section>
          <section class="panel">
            <h3>Letzte Spiele</h3>
            ${matches.length ? `<div class="match-list">${matches.slice().sort((a,b) => parseDate(b.date) - parseDate(a.date)).slice(0, 8).map(match => `
              <article class="match-item">
                <strong>${escapeHtml(match.home || '–')} – ${escapeHtml(match.away || '–')}</strong>
                <div class="meta">${escapeHtml(formatDate(match.date))}</div>
                <div class="${match.isWin ? 'result-win' : 'result-loss'}">${escapeHtml(`${match.scoreHome ?? '–'}:${match.scoreAway ?? '–'}`)}</div>
                ${(match.sets || []).length ? `<div class="meta">${escapeHtml(match.sets.join(' · '))}</div>` : ''}
              </article>
            `).join('')}</div>` : '<div class="empty">Keine Spielresultate vorhanden.</div>'}
          </section>
          <section class="panel">
            <h3>Kader</h3>
            ${squad.length ? `<div class="squad-list">${squad.map(player => `
              <article class="squad-item">
                <strong>${escapeHtml(player.name || '–')}</strong>
                <div class="meta">${escapeHtml([player.number ? '#' + player.number : '', player.position, player.isTrainer ? 'Trainer' : ''].filter(Boolean).join(' · '))}</div>
              </article>
            `).join('')}</div>` : '<div class="empty">Kein Kader im Datensatz.</div>'}
          </section>
        </div>
      </article>
    `;
  }).join('');
}

async function loadData() {
  statusText.textContent = 'Lade Daten ...';
  try {
    const response = await fetch(`${DATA_URL}?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    const generatedAt = state.data.generated_at ? new Date(state.data.generated_at) : null;
    statusText.textContent = generatedAt && !Number.isNaN(generatedAt.getTime())
      ? `Datenstand: ${generatedAt.toLocaleString('de-DE')}`
      : 'Daten geladen';
    renderNotice();
    buildStats(state.data);
    renderUpcoming(state.data);
    renderFilters(state.data);
    renderTeams(state.data);
  } catch (error) {
    console.error(error);
    statusText.textContent = 'Daten konnten nicht geladen werden';
    noticeBox.className = 'card notice notice-error';
    noticeBox.innerHTML = `<strong>Ladefehler</strong><div>${escapeHtml(error.message)}</div>`;
    statsBox.innerHTML = '';
    upcomingBox.innerHTML = '<div class="empty">Keine Daten.</div>';
    teamsBox.innerHTML = '<div class="empty">Keine Daten.</div>';
  }
}

loadData();
