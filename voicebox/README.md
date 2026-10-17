# Voicebox — voz local del stack (2026-10-17)

Backend de [jamiepine/voicebox](https://github.com/jamiepine/voicebox) (MIT) **sin la app de
escritorio**: TTS, clonado, transcripción, API REST y servidor MCP, todo en `127.0.0.1`.
Sirve para dar voz a agentes (Claude Code vía MCP) y, a futuro, para la voz del bot de recepción
sin mandar texto ni audio a la nube (frontera de datos, regla 8).

## Uso

```bash
zsh ~/llm-stack/stack.sh voz        # arranca backend + altavoz (se niega si Nex está cargado)
zsh ~/llm-stack/stack.sh voz-stop   # descarga modelos de voz y para los dos procesos
```

- API: `http://127.0.0.1:17493` (docs en `/docs`) · MCP: `http://127.0.0.1:17493/mcp/` (con barra final).
- Claude Code: MCP `voicebox` en ámbito de usuario, cabecera `X-Voicebox-Client-Id: claude-code`,
  voz por defecto «Kokoro Dora (es)». Con la voz parada, el MCP sale como desconectado: es normal.
- Herramientas MCP: `voicebox_speak`, `voicebox_transcribe`, `voicebox_list_profiles`, `voicebox_list_captures`.

## Reglas (excepción acotada a la Regla nº1 del stack, OK operador 17/10)

- Voicebox carga sus propios modelos con MLX, fuera de LM Studio. **Solo** vía `stack.sh voz`.
- **Nunca con Nex (GENERAL) en RAM**, ni al revés: `stack.sh general` se niega con la voz viva
  (incidente IOGPU del 21/08, `../incidente-panic-gpu.md`). Test: `zsh ../test-perfil-voz.sh`.
- Nube de Voicebox desactivada (`VOICEBOX_CLOUD_ENABLED` sin definir) y telemetría de HF apagada.
- Licencias de pesos: para uso comercial (Blindbeds) solo motores permisivos y verificados
  (Kokoro Apache-2.0). **OmniVoice es CC-BY-NC** y LuxTTS depende de LinaCodec, **sin licencia**.

## Piezas

| Fichero | Qué es |
|---|---|
| `install.sh` | Instalación reproducible en commit fijo `8af7efe` (main del 07/10, ya con los arreglos de la 0.6: crash de hilos MLX y fuga de memoria). La v0.5.0 publicada (abril) los tiene, por eso no se usa el DMG |
| `run.sh` | Lanzador del backend (`python -m backend.main`, datos en `./data`) |
| `altavoz.py` | El backend solo genera el audio de `speak`; quien suena es la app. Este proceso escucha `/events/speak` y reproduce con `afplay` solo lo que pidió un agente (`speak-start`) |
| `src/`, `venv/`, `data/` | Código de terceros, entorno y datos: fuera de git |

## Estado medido (17/10)

- Kokoro 82M (313 MB): voces españolas `ef_dora`, `em_alex`, `em_santa`. Seis frases de prueba
  generadas en local; pendiente el veredicto al oído del operador (`pruebas/`).
- RAM: ~1,8 GB el backend con Kokoro cargado; con el explorador residente quedaba un 42 % libre.
- Circuito MCP → generación → altavoz verificado de extremo a extremo (~6 s la primera vez).
- **Mía con Qwen3-TTS 1.7B (17/10): ganó a ciegas 5 de 6 → voz de Mía desde la siguiente serie (decisión del operador).** Prueba: misma referencia que VibeVoice
  (`es-MiaBrec_woman.wav`, transcrita con el `mlx_whisper` local), guiones B1 v3 y B4 v2, semillas
  101/303/404, solo paso-alto 85 Hz ×2. F0 173-194 Hz (dentro del registro de Mía); ritmo B1
  2,81-2,95 pal/s frente a 2,46 de la aprobada. Escucha a ciegas en `pruebas/mia-qwen/a_ciegas/`
  (clave en `clave_NO_ABRIR_hasta_votar.txt`). Los originales aprobados no se tocan.
- No probado aún: Chatterbox; dictado local.
