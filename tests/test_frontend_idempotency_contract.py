import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# None marks a deliberately retained backend endpoint with no current Mini App caller.
FRONTEND_CALLERS: dict[tuple[str, str], tuple[tuple[str, str], ...] | None] = {
    ("POST", "/sos/sessions"): None,
    ("POST", "/nicotine-desire"): (
        ("miniapp/src/components/NicotineDesireModal.tsx", 'eventApi("/nicotine-desire"'),
    ),
    ("POST", "/sos/start"): (
        ("miniapp/src/screens/Sos.tsx", 'eventApi<{ id: number }>("/sos/start"'),
    ),
    ("POST", "/sos/{session_id}/complete"): (
        ("miniapp/src/screens/Sos.tsx", "eventApi<"),
        ("miniapp/src/screens/Sos.tsx", "`/sos/${sessionId}/complete`"),
    ),
    ("POST", "/sos/{session_id}/actions"): (
        ("miniapp/src/screens/Sos.tsx", "`/sos/${sessionId}/actions`"),
    ),
    ("POST", "/sos/{session_id}/actions/{action_id}/complete"): (
        (
            "miniapp/src/screens/Sos.tsx",
            "`/sos/${sessionId}/actions/${actionId}/complete`",
        ),
    ),
    ("POST", "/sos/{session_id}/actions/{action_id}/game-result"): (
        (
            "miniapp/src/screens/Sos.tsx",
            "`/sos/${sessionId}/actions/${actionId}/game-result`",
        ),
    ),
    ("PATCH", "/sos/{session_id}/trigger"): None,
    ("POST", "/lapse"): (
        ("miniapp/src/screens/Sos.tsx", 'eventApi("/lapse"'),
    ),
    ("POST", "/quit-attempt/restart"): (
        ("miniapp/src/api/quitAttempt.ts", "idempotentRequest("),
        ("miniapp/src/api/quitAttempt.ts", '"/quit-attempt/restart"'),
        ("miniapp/src/screens/Sos.tsx", 'eventApi("/quit-attempt/restart"'),
    ),
}


def backend_idempotent_endpoints() -> set[tuple[str, str]]:
    source = (ROOT / "app/api/mini_app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    endpoints: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(argument.arg == "idempotency_key" for argument in node.args.args):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            function = decorator.func
            route = decorator.args[0]
            if (
                isinstance(function, ast.Attribute)
                and function.attr in {"post", "put", "patch", "delete"}
                and isinstance(route, ast.Constant)
                and isinstance(route.value, str)
            ):
                endpoints.add((function.attr.upper(), route.value))
    return endpoints


def test_every_backend_idempotent_endpoint_has_an_explicit_frontend_contract() -> None:
    assert backend_idempotent_endpoints() == set(FRONTEND_CALLERS)


def test_all_current_frontend_callers_use_the_idempotent_request_mechanism() -> None:
    for endpoint, callers in FRONTEND_CALLERS.items():
        if callers is None:
            continue
        for relative_path, marker in callers:
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            assert marker in source, f"Missing idempotent caller marker for {endpoint}"

    frontend_paths = [
        *(
            path
            for path in (ROOT / "miniapp/src").rglob("*.ts")
            if ".test." not in path.name
        ),
        *(
            path
            for path in (ROOT / "miniapp/src").rglob("*.tsx")
            if ".test." not in path.name
        ),
    ]
    frontend = "\n".join(path.read_text(encoding="utf-8") for path in frontend_paths)
    assert 'api("/nicotine-desire"' not in frontend
    assert 'api("/lapse"' not in frontend
    assert 'api("/quit-attempt/restart"' not in frontend
