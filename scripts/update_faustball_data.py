#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / 'data' / 'faustball_data.json'
SAMPLE_PATH = ROOT / 'data' / 'faustball_data.sample.json'
CONFIG_PATH = ROOT / 'data' / 'teams_config.json'
DEBUG_DIR = ROOT / 'data' / 'debug'

DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
SCORE_RE = re.compile(r"\b(\d{1,2})\s*[:\-]\s*(\d{1,2})\b")


@dataclass
class TeamDebug:
    team_id: str
    url: str
    ok: bool
    method: str
    message: str


def load_json(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def team_keywords(team: dict[str, Any]) -> list[str]:
    values = [
        team.get('label'),
        team.get('clubName'),
        team.get('league'),
        team.get('ageGroup'),
        team.get('gender'),
    ]
    words = []
    for value in values:
        if not value:
            continue
        words.append(str(value).lower())
    return [word for word in words if word]


def iter_nodes(node: Any) -> Iterable[Any]:
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from iter_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_nodes(item)


def looks_like_standing_row(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    keys = {str(key).lower() for key in node.keys()}
    has_team = any(key in keys for key in {'team', 'teamname', 'name', 'club', 'clubname', 'mannschaft'})
    has_rank = any(key in keys for key in {'position', 'rank', 'platz', 'place'})
    numeric_count = sum(isinstance(value, (int, float)) for value in node.values())
    return has_team and has_rank and numeric_count >= 2


def looks_like_match_row(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    keys = {str(key).lower() for key in node.keys()}
    home_keys = {'home', 'teama', 'heim', 'homeTeam'.lower(), 'team1'}
    away_keys = {'away', 'teamb', 'gast', 'awayTeam'.lower(), 'team2'}
    has_home = any(key in keys for key in home_keys)
    has_away = any(key in keys for key in away_keys)
    has_score = any(key in keys for key in {'score', 'result', 'scorehome', 'scoreaway', 'sets'}) or any(
        isinstance(value, str) and SCORE_RE.search(value) for value in node.values()
    )
    return has_home and has_away and has_score


def normalize_team_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ('name', 'teamName', 'label', 'clubName', 'shortName'):
            if key in value and value[key]:
                return str(value[key]).strip()
        return None
    text = str(value).strip()
    return text or None


def normalize_standing_row(node: dict[str, Any], our_keywords: list[str]) -> dict[str, Any] | None:
    team_name = None
    for key in ('teamName', 'team', 'name', 'clubName', 'club', 'mannschaft', 'label'):
        if key in node:
            team_name = normalize_team_name(node[key])
            if team_name:
                break
    if not team_name:
        return None

    position = None
    for key in ('position', 'rank', 'platz', 'place'):
        if key in node:
            position = node[key]
            break

    def pick(*keys: str) -> int | None:
        for key in keys:
            if key in node and isinstance(node[key], (int, float)):
                return int(node[key])
        return None

    row = {
        'position': position,
        'teamName': team_name,
        'played': pick('played', 'games', 'matches', 'spiele'),
        'setsWon': pick('setsWon', 'sets_won', 'satzGewonnen', 'setWins'),
        'setsLost': pick('setsLost', 'sets_lost', 'satzVerloren', 'setLosses'),
        'pointsWon': pick('pointsWon', 'points', 'punkte', 'wins'),
        'pointsLost': pick('pointsLost', 'minusPoints', 'losses'),
        'isOurTeam': any(keyword in team_name.lower() for keyword in our_keywords),
    }
    return row


def normalize_match_row(node: dict[str, Any], our_keywords: list[str]) -> dict[str, Any] | None:
    home = None
    away = None
    for key in ('home', 'teamA', 'heim', 'team1'):
        if key in node:
            home = normalize_team_name(node[key])
            if home:
                break
    for key in ('away', 'teamB', 'gast', 'team2'):
        if key in node:
            away = normalize_team_name(node[key])
            if away:
                break
    if not home or not away:
        return None

    date = None
    for value in node.values():
        if isinstance(value, str):
            match = DATE_RE.search(value)
            if match:
                date = match.group(1)
                break
    for key in ('date', 'datum'):
        if key in node and isinstance(node[key], str) and DATE_RE.search(node[key]):
            date = DATE_RE.search(node[key]).group(1)
            break

    score_home = None
    score_away = None
    if isinstance(node.get('scoreHome'), (int, float)) and isinstance(node.get('scoreAway'), (int, float)):
        score_home = int(node['scoreHome'])
        score_away = int(node['scoreAway'])
    else:
        for value in node.values():
            if isinstance(value, str):
                score_match = SCORE_RE.search(value)
                if score_match:
                    score_home = int(score_match.group(1))
                    score_away = int(score_match.group(2))
                    break

    sets = []
    raw_sets = node.get('sets')
    if isinstance(raw_sets, list):
        sets = [str(item) for item in raw_sets]

    is_our_match = any(keyword in (home + ' ' + away).lower() for keyword in our_keywords)
    is_win = None
    if score_home is not None and score_away is not None and is_our_match:
        if any(keyword in home.lower() for keyword in our_keywords):
            is_win = score_home > score_away
        elif any(keyword in away.lower() for keyword in our_keywords):
            is_win = score_away > score_home

    return {
        'date': date or '',
        'home': home,
        'away': away,
        'scoreHome': score_home,
        'scoreAway': score_away,
        'sets': sets,
        'isOurMatch': is_our_match,
        'isWin': bool(is_win) if is_win is not None else False,
    }


def dedupe_rows(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def extract_from_payload(payload: Any, team: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    our_keywords = team_keywords(team)
    standings: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    for node in iter_nodes(payload):
        if looks_like_standing_row(node):
            row = normalize_standing_row(node, our_keywords)
            if row:
                standings.append(row)
        if looks_like_match_row(node):
            row = normalize_match_row(node, our_keywords)
            if row:
                matches.append(row)
    standings = dedupe_rows(standings, ('position', 'teamName'))
    matches = dedupe_rows(matches, ('date', 'home', 'away', 'scoreHome', 'scoreAway'))
    return standings, matches


def extract_from_tables(html: str, team: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    our_keywords = team_keywords(team)
    soup = BeautifulSoup(html, 'html.parser')
    standings: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []

    for table in soup.find_all('table'):
        headers = [cell.get_text(' ', strip=True).lower() for cell in table.find_all('th')]
        rows = table.find_all('tr')
        if not headers or not rows:
            continue
        is_standing_table = any(word in ' '.join(headers) for word in ['platz', 'team', 'mannschaft', 'punkte', 'sätze'])
        is_match_table = any(word in ' '.join(headers) for word in ['datum', 'heim', 'gast', 'ergebnis', 'result'])
        for row in rows[1:]:
            cells = [cell.get_text(' ', strip=True) for cell in row.find_all(['td', 'th'])]
            if len(cells) < 2:
                continue
            if is_standing_table and len(cells) >= 5:
                try:
                    pos = int(re.sub(r'\D+', '', cells[0]))
                except ValueError:
                    pos = None
                team_name = cells[1]
                sets = re.findall(r'\d+', cells[3] if len(cells) > 3 else '')
                points = re.findall(r'\d+', cells[4] if len(cells) > 4 else '')
                standings.append({
                    'position': pos,
                    'teamName': team_name,
                    'played': int(re.sub(r'\D+', '', cells[2])) if len(cells) > 2 and re.search(r'\d', cells[2]) else None,
                    'setsWon': int(sets[0]) if len(sets) >= 2 else None,
                    'setsLost': int(sets[1]) if len(sets) >= 2 else None,
                    'pointsWon': int(points[0]) if len(points) >= 2 else None,
                    'pointsLost': int(points[1]) if len(points) >= 2 else None,
                    'isOurTeam': any(keyword in team_name.lower() for keyword in our_keywords),
                })
            elif is_match_table and len(cells) >= 4:
                score = SCORE_RE.search(' '.join(cells))
                matches.append({
                    'date': DATE_RE.search(cells[0]).group(1) if DATE_RE.search(cells[0]) else '',
                    'home': cells[1],
                    'away': cells[2],
                    'scoreHome': int(score.group(1)) if score else None,
                    'scoreAway': int(score.group(2)) if score else None,
                    'sets': [],
                    'isOurMatch': True,
                    'isWin': False,
                })

    return dedupe_rows(standings, ('position', 'teamName')), dedupe_rows(matches, ('date', 'home', 'away', 'scoreHome', 'scoreAway'))


def load_live_team_data(team: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], TeamDebug]:
    url = team.get('faustballUrl') or ''
    collected_payloads: list[Any] = []
    html = ''
    body_text = ''

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale='de-DE')

        def handle_response(response) -> None:
            try:
                content_type = response.headers.get('content-type', '')
                if 'json' not in content_type.lower():
                    return
                data = response.json()
                collected_payloads.append(data)
            except Exception:
                return

        page.on('response', handle_response)
        try:
            page.goto(url, wait_until='networkidle', timeout=45000)
            page.wait_for_timeout(3500)
            html = page.content()
            body_text = page.locator('body').inner_text(timeout=5000)
        except PlaywrightTimeoutError as exc:
            browser.close()
            return [], [], TeamDebug(team['id'], url, False, 'playwright', f'Timeout: {exc}')
        except Exception as exc:
            browser.close()
            return [], [], TeamDebug(team['id'], url, False, 'playwright', str(exc))
        browser.close()

    standings: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []

    for payload in collected_payloads:
        s_rows, m_rows = extract_from_payload(payload, team)
        standings.extend(s_rows)
        matches.extend(m_rows)

    if not standings and not matches and html:
        s_rows, m_rows = extract_from_tables(html, team)
        standings.extend(s_rows)
        matches.extend(m_rows)

    standings = dedupe_rows(standings, ('position', 'teamName'))
    matches = dedupe_rows(matches, ('date', 'home', 'away', 'scoreHome', 'scoreAway'))

    debug_payload = {
        'team_id': team['id'],
        'url': url,
        'json_payloads_seen': len(collected_payloads),
        'body_preview': body_text[:2000],
        'standings_found': len(standings),
        'matches_found': len(matches),
    }
    save_json(DEBUG_DIR / f'{team["id"]}.json', debug_payload)

    if standings or matches:
        return standings, matches, TeamDebug(team['id'], url, True, 'json/dom', f'Standings={len(standings)}, Matches={len(matches)}')
    return [], [], TeamDebug(team['id'], url, False, 'json/dom', 'Keine verwertbaren Live-Daten erkannt')


def main() -> int:
    parser = argparse.ArgumentParser(description='Aktualisiert data/faustball_data.json aus faustball.com mit Fallback auf das Start-Snapshot.')
    parser.add_argument('--output', default=str(DATA_PATH), help='Zielpfad für die erzeugte JSON-Datei')
    args = parser.parse_args()

    output_path = Path(args.output)
    sample = load_json(SAMPLE_PATH)
    data = load_json(output_path) if output_path.exists() else sample
    config = load_json(CONFIG_PATH)

    team_map = {team['id']: team for team in config}
    data['teams'] = config
    data.setdefault('standings', {})
    data.setdefault('matches', {})
    debug_items: list[dict[str, Any]] = []
    notices: list[str] = []
    live_success = 0

    for team in config:
        standings, matches, debug = load_live_team_data(team)
        debug_items.append(debug.__dict__)
        if standings:
            data['standings'][team['id']] = standings
        elif team['id'] not in data['standings']:
            data['standings'][team['id']] = sample.get('standings', {}).get(team['id'], [])
        if matches:
            data['matches'][team['id']] = matches
        elif team['id'] not in data['matches']:
            data['matches'][team['id']] = sample.get('matches', {}).get(team['id'], [])
        if debug.ok:
            live_success += 1
        else:
            notices.append(f"{team['label']}: {debug.message}")

    data['generated_at'] = datetime.now(timezone.utc).astimezone().isoformat()
    data['generated_by'] = 'scripts/update_faustball_data.py'
    data['source_status'] = {
        'mode': 'live_with_fallback',
        'live_ok': live_success > 0,
        'message': f'{live_success} von {len(config)} Team-Bereichen konnten live oder halb-live aktualisiert werden. Nicht erkannte Bereiche bleiben auf dem letzten Stand stehen.'
    }
    data['notices'] = notices[:12]

    save_json(output_path, data)
    save_json(DEBUG_DIR / 'last_run.json', {'generated_at': data['generated_at'], 'teams': debug_items})

    print(f"Geschrieben: {output_path}")
    print(data['source_status']['message'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
