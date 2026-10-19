#!/bin/zsh
# Una sola vez: tras el PRÓXIMO reinicio, re-mide la matriz de RAM (auditoría v6.5 §RAM: swap de partida 25 GB
# invalidaba la medición del 19/10 de "Nex + explorador"). Lo dispara el LaunchAgent com.luisfran.remedir-ram al iniciar sesión.
M=~/.local/state/llm-stack/remedir-ram.pendiente; [ -f "$M" ] || exit 0
creado=$(cat "$M"); arranque=$(sysctl -n kern.boottime | grep -oE 'sec = [0-9]+' | grep -oE '[0-9]+')
[ "$arranque" -gt "$creado" ] || exit 0          # aún no ha habido reinicio desde que se programó
sleep 600                                          # dejar que LM Studio, LiteLLM y el resto arranquen
OUT=~/llm-stack/informes/matriz-ram-tras-reinicio-$(date +%F).out
zsh ~/llm-stack/informes/2026-10-19/matriz-ram.sh > "$OUT" 2>&1
rm -f "$M"; osascript -e "display notification \"Matriz de RAM re-medida tras el reinicio: $OUT\" with title \"Stack agéntico\"" 2>/dev/null
launchctl bootout gui/$(id -u)/com.luisfran.remedir-ram 2>/dev/null; rm -f ~/Library/LaunchAgents/com.luisfran.remedir-ram.plist
