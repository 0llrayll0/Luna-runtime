from __future__ import annotations

import contextlib
import urllib.parse
from pathlib import Path

import typer
import yaml
import httpx
from rich.console import Console
from rich.table import Table

from luna.core.config import ExecutionSettings, ModelsSettings, Settings, _resolve_path, load_config
from luna.runtime.core import LunaRuntime

app = typer.Typer(help="Luna Runtime CLI")
console = Console()

agent_app = typer.Typer(help="Agent commands")
model_app = typer.Typer(help="Model commands")
provider_app = typer.Typer(help="Provider commands")
tool_app = typer.Typer(help="Tool commands")
session_app = typer.Typer(help="Session commands")

app.add_typer(agent_app, name="agent")
app.add_typer(model_app, name="model")
app.add_typer(provider_app, name="provider")
app.add_typer(tool_app, name="tool")
app.add_typer(session_app, name="session")


DEFAULT_TEMPLATE = Settings(
    models=ModelsSettings(
        default="ollama/qwen3-coder:30b",
        providers=[{"name": "ollama", "type": "ollama", "base_url": "http://localhost:11434", "timeout": 180}],
    ),
    execution=ExecutionSettings(timeout_seconds=60),
).model_dump()


def _config_path() -> Path:
    return _resolve_path(None)


def get_runtime() -> LunaRuntime:
    rt = LunaRuntime()
    return rt


@app.command()
def init(force: bool = typer.Option(False, "--force")) -> None:
    """Initialize default config if missing."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        console.print(f"config already exists: {path}")
        return
    path.write_text(yaml.safe_dump(DEFAULT_TEMPLATE, sort_keys=False), encoding="utf-8")
    console.print(f"created: {path}")


@app.command()
def doctor() -> None:
    """Check runtime health."""
    try:
        cfg = load_config()
        console.print(f"config OK: {_config_path()}")
        console.print(f"runtime: {cfg.runtime.name} ({cfg.runtime.environment})")
    except Exception as exc:
        console.print(f"[red]config error: {exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print("doctor: ok")


@app.command("config")
def config_cmd() -> None:
    """Print resolved config."""
    cfg = load_config()
    console.print(yaml.safe_dump(cfg.model_dump(), sort_keys=False))


@agent_app.command("list")
def agent_list() -> None:
    rt = get_runtime()
    table = Table("name", "model", "tools")
    for a in rt.agents.values():
        c = a.config
        table.add_row(c.name, c.model, ",".join(c.tools))
    console.print(table)


@agent_app.command("create")
def agent_create(
    name: str,
    model: str = typer.Option("default", "--model"),
    system_prompt: str = typer.Option("", "--system-prompt"),
    tools: str = typer.Option("", "--tools"),
) -> None:
    rt = get_runtime()
    from luna.agents.schema import AgentConfig

    cfg = AgentConfig(
        name=name,
        model=model,
        system_prompt=system_prompt,
        tools=[t.strip() for t in tools.split(",") if t.strip()],
    )
    agent = rt.create_agent(cfg)
    console.print(f"created agent: {agent.config.name}")


@agent_app.command("run")
def agent_run(task: str, agent: str | None = typer.Option(None, "--agent")) -> None:
    """Run a task with an agent."""
    import asyncio

    rt = get_runtime()
    chosen = rt.agents.get(agent) if agent is not None else None
    if chosen is None and rt.agents:
        chosen = next(iter(rt.agents.values()))
    if chosen is None:
        from luna.agents.schema import AgentConfig

        chosen = rt.create_agent(AgentConfig(name="default", model=rt.config.models.default))
    try:
        result = asyncio.run(chosen.run(task))
    except (TimeoutError, httpx.TimeoutException) as exc:  # noqa: BLE001
        console.print("model cold-load exceeded timeout; aumente timeout no config ou pré-carregue o modelo no ollama")
        raise typer.Exit(code=1) from None
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]error: {exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(result.output or "")
    if result.status != "completed":
        console.print(f"status: {result.status}")


@agent_app.command("inspect")
def agent_inspect(agent_id: str) -> None:
    rt = get_runtime()
    agent = rt.agents.get(agent_id)
    if agent is None:
        console.print(f"[red]agent not found: {agent_id}[/red]")
        raise typer.Exit(code=1) from None
    c = agent.config
    console.print(f"name: {c.name}")
    console.print(f"model: {c.model}")
    console.print(f"system_prompt: {c.system_prompt}")
    console.print(f"tools: {c.tools}")
    console.print(f"max_iterations: {c.max_iterations}")


@model_app.command("list")
def model_list() -> None:
    rt = get_runtime()
    table = Table("provider", "model")
    if not rt.providers:
        console.print("no providers registered")
        return
    try:
        import asyncio

        gw_models = asyncio.run(rt.gateway.list_models())
    except Exception:
        gw_models = {}
    for name, provider in rt.providers.items():
        models = gw_models.get(name)
        if models is None:
            try:
                import asyncio

                models = asyncio.run(provider.list_models())
            except Exception:
                table.add_row(name, "(unreachable)")
                continue
        if not models:
            table.add_row(name, "(no models)")
        for m in models:
            table.add_row(name, str(m))
    console.print(table)


@model_app.command("test")
def model_test(model_ref: str) -> None:
    rt = get_runtime()
    provider_name = None
    model_name = model_ref
    if "/" in model_ref:
        provider_name, model_name = model_ref.split("/", 1)
    provider = rt.providers.get(provider_name) if provider_name else (next(iter(rt.providers.values()), None) if rt.providers else None)
    if provider is None:
        console.print(f"[red]provider not found: {provider_name or '(default)'}[/red]")
        raise typer.Exit(code=1) from None
    try:
        ok = False
        if hasattr(provider, "health"):
            import asyncio

            ok = asyncio.run(provider.health())
        else:
            ok = True
        console.print(f"model {model_ref}: {'ok' if ok else 'unreachable'}")
        if not ok:
            raise typer.Exit(code=1) from None
    except (TimeoutError, httpx.TimeoutException, httpx.ConnectError, Exception) as exc:  # noqa: BLE001
        console.print(f"model {model_ref}: unreachable")
        console.print(f"[red]error: {exc}[/red]")
        raise typer.Exit(code=1) from None


@provider_app.command("list")
def provider_list() -> None:
    rt = get_runtime()
    table = Table("name", "base_url")
    for p in rt.providers.values():
        table.add_row(p.name, getattr(p, "base_url", ""))
    console.print(table)


@provider_app.command("add")
def provider_add(name: str, url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        console.print(f"[red]invalid url: {url}[/red]")
        raise typer.Exit(code=1) from None
    # instantiate OpenAI-compatible? Determine by name? Use Ollama if localhost 11434 else openai
    rt = get_runtime()
    from luna.providers.ollama import OllamaProvider
    from luna.providers.openai_compat import OpenAICompatibleProvider

    if "ollama" in name.lower() or "11434" in url:
        provider = OllamaProvider(base_url=url, name=name)
    else:
        provider = OpenAICompatibleProvider(base_url=url, name=name)
    rt.register_provider(name, provider)
    console.print(f"registered provider: {name} ({url})")


@tool_app.command("list")
def tool_list() -> None:
    from luna.tools.filesystem import register_fs_defaults
    from luna.tools.git import register_git_defaults
    from luna.tools.terminal import register_terminal_defaults

    reg = get_runtime().tool_registry
    if not reg.list():
        register_fs_defaults(reg)
        register_terminal_defaults(reg)
        register_git_defaults(reg)
    table = Table("id", "name", "risk")
    for spec in reg.list_specs():
        table.add_row(spec.id, spec.name, getattr(spec, "risk_level", "low"))
    console.print(table)


@tool_app.command("inspect")
def tool_inspect(tool_id: str) -> None:
    from luna.tools.filesystem import register_fs_defaults
    from luna.tools.git import register_git_defaults
    from luna.tools.terminal import register_terminal_defaults

    reg = get_runtime().tool_registry
    if not reg.list():
        register_fs_defaults(reg)
        register_terminal_defaults(reg)
        register_git_defaults(reg)
    tool = reg.get(tool_id)
    if tool is None:
        console.print(f"[red]tool not found: {tool_id}[/red]")
        raise typer.Exit(code=1) from None
    spec = tool.spec
    console.print(f"id: {spec.id}")
    console.print(f"name: {spec.name}")
    console.print(f"description: {spec.description}")
    console.print(f"risk_level: {spec.risk_level}")
    console.print(f"permissions: {[p.value for p in spec.permissions]}")


@session_app.command("list")
def session_list() -> None:
    import asyncio

    rt = get_runtime()
    sm = rt.session_manager
    asyncio.run(sm.init())
    rows = asyncio.run(sm.list_sessions())
    table = Table("id", "agent")
    for r in rows:
        table.add_row(r.id, r.agent_name or "")
    console.print(table)


@session_app.command("inspect")
def session_inspect(session_id: str) -> None:
    import asyncio

    rt = get_runtime()
    sm = rt.session_manager
    asyncio.run(sm.init())
    rec = asyncio.run(sm.get_session(session_id))
    if rec is None:
        console.print(f"[red]session not found: {session_id}[/red]")
        raise typer.Exit(code=1) from None
    msgs = asyncio.run(sm.get_messages(session_id))
    console.print(f"id: {rec.id}")
    console.print(f"agent: {rec.agent_name}")
    console.print(f"messages: {len(msgs)}")
    for m in msgs:
        console.print(f"- {m.role}: {(m.content or '')[:200]}")


@app.command()
def run(task: str, agent: str | None = typer.Option(None, "--agent")) -> None:
    """Run a task."""
    import asyncio

    rt = get_runtime()
    chosen = None
    if agent is not None:
        chosen = rt.agents.get(agent)
    if chosen is None and rt.agents:
        chosen = next(iter(rt.agents.values()))
    if chosen is None:
        # default agent
        from luna.agents.schema import AgentConfig

        chosen = rt.create_agent(AgentConfig(name="default", model=rt.config.models.default))
    try:
        result = asyncio.run(chosen.run(task))
    except (TimeoutError, httpx.TimeoutException) as exc:  # noqa: BLE001
        console.print("model cold-load exceeded timeout; aumente timeout no config ou pré-carregue o modelo no ollama")
        raise typer.Exit(code=1) from None
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]error: {exc}[/red]")
        raise typer.Exit(code=1) from None
    console.print(result.output or "")
    if result.status != "completed":
        console.print(f"status: {result.status}")


@app.command()
def chat() -> None:
    """Simple REPL."""
    import asyncio

    console.print("chat mode (empty line to exit)")
    while True:
        try:
            line = console.input("> ")
        except EOFError:
            break
        if not line.strip():
            break
        # reuse run logic
        with contextlib.suppress(Exception):
            get_runtime()
        from luna.agents.schema import AgentConfig

        r = get_runtime()
        chosen = next(iter(r.agents.values()), None) if r.agents else r.create_agent(AgentConfig(name="default", model=r.config.models.default))
        result = asyncio.run(chosen.run(line))
        console.print(result.output or result.status)


@app.command("web")
def web(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(5000, "--port"),
) -> None:
    """Start web configuration UI."""
    from luna.web.app import create_app

    flask_app = create_app(None)
    flask_app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    app()
