# proxy-llm

Python 3.12 Tkinter GUI for managing `llm-proxy-server` configuration.

## Quick start

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Project structure

| Path | Purpose |
|------|---------|
| `main.py` | Single entrypoint — launches Tkinter main window |
| `src/models/__init__.py` | Dataclass models (`AppConfig`, `Provider`, `RoutingRule`, `Group`, `ServerConfig`) |
| `src/utils/config.py` | JSON read/write, TOML export, validation helpers |
| `src/utils/tokens.py` | tiktoken token counting + cost estimation |
| `src/utils/test_connection*.py` | Provider connectivity test helpers |
| `llm_proxy_config.json` | Default config file (JSON) |
| `proxy_config.toml` | Exported TOML consumed by `llm-proxy-server` |

## Key facts

- **No tests.** No test framework, no CI, no test directory.
- **No linter/formatter/typechecker config.** No `pyproject.toml`, `setup.py`, `setup.cfg`.
- **Pydantic is listed in `requirements.txt` but unused.** The project uses only `dataclasses`.
- **Config persistence** is JSON (`llm_proxy_config.json`). TOML export (`proxy_config.toml`) is written by `config_to_toml()` for the external `llm-proxy-server` binary.
- **Server management:** `ProxyServer` in `main.py:25` spawns `llm-proxy-server --config <toml>` as a subprocess. On Windows uses `subprocess.CREATE_NO_WINDOW`. Force-kills port via `netstat -ano` + `taskkill`.
- **Dark theme** via `ttk.Style` with `clam` theme. Color palette defined in `LLMGuiApp.setup_styles()`.
- **Built-in providers** (disabled by default): deepseek, moonshot, minimax — defined in `src/models/__init__.py:56`.
- The `.venv/` is at project root (Python 3.12.7). Activate before running.
