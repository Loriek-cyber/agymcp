# agymcp — Antigravity MCP Installer & Manager

Applicazione desktop nativa (**PyQt6**) e CLI rapida per installare e gestire i server MCP di **Antigravity** (`~/.gemini/config/mcp_config.json`) incollando direttamente un link come `https://api.streak.com/mcp`.

## Funzionalità principali

- **Installazione 1-Click da Link**: incolla l'URL MCP (es. `https://api.streak.com/mcp`), il nome (`streak`) viene dedotto automaticamente e il server viene scritto nello schema nativo di Antigravity (`serverUrl`) con backup `.bak` automatico e scrittura atomica.
- **Autenticazione Opzionale**: supporto per OAuth automatico (nessun header statico), Bearer Token (`Authorization: Bearer ...`), API Key Header (`X-Api-Key`, `X-Goog-Api-Key`, ecc.) o header personalizzati.
- **Test Connessione HTTP**: verifica raggiungibilità dell'endpoint, rilevamento di risposte `401/403` (auth richiesta) e riconoscimento automatico dei vecchi endpoint `/sse` con opzione bridge `npx -y mcp-remote`.
- **Manager Completo**: tabella con switch Attiva/Disattiva per ogni server, aggiunta e modifica di server locali **Stdio** (`uvx`, `npx`, `uv`, ecc.) ed editor JSON raw con validazione e ripristino da `.bak`.

## Installazione Locale

```bash
chmod +x install.sh
./install.sh
```

Lo script installa:
- il comando `agymcp` in `~/.local/bin/agymcp`
- il collegamento desktop **Antigravity MCP Installer** nel menu applicazioni di sistema.

## Utilizzo

### Interfaccia Grafica
- Apri **Antigravity MCP Installer** dal menu applicazioni oppure esegui:
  ```bash
  agymcp
  ```
- Puoi anche aprire la GUI con un link già precompilato:
  ```bash
  agymcp https://api.streak.com/mcp --gui
  ```

### Riga di Comando (CLI)
```bash
# Installa subito un server MCP remoto da link (nome 'streak' auto-dedotto)
agymcp https://api.streak.com/mcp

# Specifica un nome personalizzato o autenticazione
agymcp https://api.streak.com/mcp -n my-streak -b IL_TUO_TOKEN
agymcp https://example.com/mcp -H "X-Api-Key: secret"

# Vecchio server legacy SSE tramite bridge npx mcp-remote
agymcp https://example.com/sse --bridge

# Gestione server configurati
agymcp --list
agymcp --disable streak
agymcp --enable streak
agymcp --remove streak
agymcp --test https://api.streak.com/mcp
```

## Test

```bash
python3 -m unittest discover -s tests -v
```
