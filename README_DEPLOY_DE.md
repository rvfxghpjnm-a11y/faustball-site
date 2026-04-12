# Faustball-App für GitHub Pages + Raspberry Pi

Das hier ist bewusst ohne Build-Schritt gebaut.

## Ziel
- Frontend liegt statisch auf GitHub Pages
- Raspberry Pi aktualisiert `data/faustball_data.json`
- Danach macht der Pi automatisch `git push`
- GitHub Pages zeigt immer die zuletzt gepushte JSON-Datei an

## Einmalig auf GitHub
1. Neues Repository anlegen, zum Beispiel `faustball-site`
2. Alle Dateien aus diesem Ordner in das Repository hochladen
3. In GitHub: `Settings -> Pages -> Deploy from a branch -> main -> /(root)`

## Einmalig auf dem Raspberry Pi
```bash
cd ~
git clone git@github.com:DEINNAME/faustball-site.git
cd faustball-site
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python scripts/update_faustball_data.py
```

## Testlauf mit Push
```bash
cd ~/faustball-site
./scripts/update_and_push.sh
```

## Automatisch alle 10 Minuten per systemd
```bash
cd ~/faustball-site
mkdir -p ~/.config/systemd/user
cp deploy/faustball-update.service ~/.config/systemd/user/
cp deploy/faustball-update.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now faustball-update.timer
systemctl --user list-timers | grep faustball
```

## Falls du lieber cron willst
```bash
crontab -e
```
Dann diese Zeile eintragen:
```cron
*/10 * * * * cd /home/stefan/faustball-site && ./scripts/update_and_push.sh
```

## Wichtig
Die Startdaten in `data/faustball_data.sample.json` stammen aus deinem gelieferten Perplexity-ZIP.
Der Live-Updater versucht die Faustball-Seiten per Playwright zu öffnen und dort JSON/Tabellen automatisch zu erkennen.
Wenn faustball.com die Struktur ändert, bleiben die letzten funktionierenden Daten stehen. Die App läuft dann weiter.
