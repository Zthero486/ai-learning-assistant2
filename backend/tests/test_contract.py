"""v2 重构护栏：接口契约快照（P0 基线固化）。

为什么要有这个文件
------------------
v2 要把 `main.py` 拆成分层架构（core / repositories / services / ai / api）。
重构最容易犯的错不是"跑不起来"，而是**某个接口悄悄少了一个字段、改了一个类型、
换了一个错误码**——后端测试照样绿、前端页面直接白屏。

本文件把 26 个接口的**结构**（路径、方法、路径参数、查询参数、请求体字段、
成功状态码、响应 JSON 的字段名与类型、错误响应结构）冻结成快照文件：

    backend/tests/snapshots/api_contract.json

之后每次 `pytest` 都会重新采集一遍结构与快照比对，不一致就失败并打印差异。
**只比结构、不比数据**（字段值里的 id / 时间戳 / 中文内容都不进快照），
所以刷新数据库、换测试机、改文案都不会误报。

覆盖范围与 26 个接口的对应关系见 `CONTRACT_MANIFEST`；
若有人新增接口却没登记，`test_接口清单与实测一致` 会失败，防止快照"漏掉"接口。

怎么用
------
改了接口并确认是**有意**变更（不是重构手滑）：

    cd backend
    python tests/test_contract.py            # 重新生成快照
    git diff tests/snapshots/api_contract.json   # 用 diff 审一遍，确认改的都是想改的
    python -m pytest -q                      # 再跑一遍，应该全绿

其余情况一律视为回归，先修代码，别刷快照。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("AI_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")  # 测试环境强制走规则引擎，不碰外网

from app import ai_helper  # noqa: E402
from app import main as app_main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SNAPSHOT = Path(__file__).resolve().parent / "snapshots" / "api_contract.json"
SNAPSHOT_VERSION = 1

# 静态资源托管（frontend/dist）存在时会多挂一个 "/" 路由，与契约无关
STATIC_PATHS = {"/"}

# ==================== 接口清单（33 个接口，手工登记） ====================
# "METHOD /path"：与 main.py 中 @app.xxx 装饰器一一对应，改接口必须同步改这里。
CONTRACT_MANIFEST = {
    "GET /api/health",
    "POST /api/auth/register",
    "POST /api/auth/login",
    "GET /api/auth/me",
    "POST /api/auth/logout",
    "POST /api/materials/upload",
    "GET /api/materials",
    "GET /api/materials/{mid}",
    "DELETE /api/materials/{mid}",
    "POST /api/knowledge-points",
    "GET /api/knowledge-points",
    "PUT /api/knowledge-points/{kid}",
    "DELETE /api/knowledge-points/{kid}",
    "POST /api/tasks",
    "GET /api/tasks",
    "PATCH /api/tasks/{tid}/status",
    "DELETE /api/tasks/{tid}",
    "GET /api/tasks/due-soon",
    "POST /api/questions/generate",
    "GET /api/questions",
    "POST /api/practice/submit",
    "GET /api/wrong-book",
    "PATCH /api/wrong-book/{wid}",
    "GET /api/wrong-book/export/csv",
    "GET /api/wrong-book/print",
    "GET /api/search",
    "GET /api/stats/overview",
    "GET /api/config/ai",
    "POST /api/config/ai",
    "POST /api/ai/test",
    "POST /api/ai/summarize",
    "POST /api/ai/ask",
    "POST /api/ai/weak-analysis",
}

# ==================== 结构采集 ====================


def schema_of(value):
    """把 JSON 值折叠成"类型骨架"。

    - 标量 -> 类型名（string / integer / number / boolean / null）
    - 列表 -> list<元素骨架>；元素是对象时输出 `list<{...}>`，只取第一个元素
    - 字典 -> 递归展开，字段按字母序排列保证稳定
    - 空容器 -> list<any> / 空字典 {}，不产生噪声
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        if not value:
            return "list<any>"
        first = value[0]
        if isinstance(first, dict):
            # 列表里的对象：字段结构一致就只描述一次，不一致时逐项标注类型
            shapes = [schema_of(item) for item in value]
            if all(shape == shapes[0] for shape in shapes):
                return f"list<{_stringify(shapes[0])}>"
            return f"list<{'|'.join(sorted({_stringify(s) for s in shapes}))}>"
        return f"list<{'|'.join(sorted({schema_of(item) for item in value}))}>"
    if isinstance(value, dict):
        return {key: schema_of(value[key]) for key in sorted(value)}
    raise TypeError(f"无法识别的 JSON 类型：{type(value)!r}")


def _stringify(shape) -> str:
    """把 dict 形态的骨架转成可比较/可排序的字符串（只用于联合类型展示）。"""
    return json.dumps(shape, ensure_ascii=False, sort_keys=True)


def _param_schema(param) -> dict:
    """提取单个路径/查询参数的结构：名字 + 是否必填 + 类型说明。"""
    return {
        "name": param.name,
        "required": bool(param.required),
        "schema": schema_of_field(param.field_info.annotation),
    }


def schema_of_field(annotation) -> str:
    """把 Python 注解折成与 `schema_of` 同构的类型字符串（"int | None" -> "integer|null"）。"""
    mapping = {
        int: "integer",
        float: "number",
        str: "string",
        bool: "boolean",
        type(None): "null",
        bytes: "string",
    }
    if annotation in mapping:
        return mapping[annotation]

    # FastAPI 在 Python 3.10 下把 Optional[X] 表示为 typing.Union / X | None
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is not None and args:
        parts = sorted({schema_of_field(a) for a in args})
        text = "|".join(parts)
        if origin is list or str(origin) in ("<class 'list'>", "typing.List"):
            inner = parts[0] if len(parts) == 1 else text
            return f"list<{inner}>"
        return text
    name = getattr(annotation, "__name__", None)
    if name:
        return name.lower()
    return "any"


def body_schema_of(route) -> dict | None:
    """请求体（JSON / form）字段骨架；无请求体返回 None。

    FastAPI 把 POST/PUT/PATCH 的请求体声明为 body 参数，其 `schema` 里带完整 properties。
    v1 的请求体都是裸 dict，没有 Pydantic 模型，所以字段只能从试探请求里采集，
    这里只记录"有没有请求体 + 是否必填"。
    """
    body_params = [
        p for p in route.dependant.body_params if getattr(p, "name", "") not in ("file", "course")
    ]
    if not any(p.name == "file" for p in route.dependant.body_params):
        if not route.dependant.body_params:
            return None
    return {
        "required": any(p.required for p in route.dependant.body_params),
        "params": sorted(p.name for p in route.dependant.body_params),
    }


def collect_openapi(app) -> dict:
    """从 OpenAPI 文档里取路径、方法、路径/查询参数、响应声明。

    OpenAPI 是 FastAPI 自己生成的、前端也能拿到的"对外契约"，比读路由对象更稳。
    """
    spec = app.openapi()
    routes = {}
    for path, methods in spec.get("paths", {}).items():
        if path in STATIC_PATHS:
            continue
        for method, operation in methods.items():
            key = f"{method.upper()} {path}"
            params = [
                {
                    "name": p["name"],
                    "in": p["in"],
                    "required": bool(p.get("required", False)),
                    "schema": _openapi_schema(p.get("schema", {})),
                }
                for p in operation.get("parameters", [])
            ]
            request_body = operation.get("requestBody")
            routes[key] = {
                "operation_id": operation.get("operationId"),
                "params": sorted(params, key=lambda p: (p["in"], p["name"])),
                "request_body": _openapi_body(request_body),
                "responses": sorted(operation.get("responses", {})),
            }
    return routes


def _openapi_schema(schema: dict) -> str:
    """OpenAPI schema 片段的类型描述（$ref 只保留模型名，防止定义顺序影响快照）。"""
    if not schema:
        return "any"
    ref = schema.get("$ref")
    if ref:
        return ref.rsplit("/", 1)[-1]
    any_of = schema.get("anyOf")
    if any_of:
        return "|".join(sorted({_openapi_schema(s) for s in any_of}))
    if schema.get("type") == "array":
        return f"list<{_openapi_schema(schema.get('items', {}))}>"
    return schema.get("type", "any")


def _openapi_body(request_body) -> dict | None:
    if not request_body:
        return None
    content = request_body.get("content", {})
    kinds = []
    if "application/json" in content:
        kinds.append(f"json:{_openapi_schema(content['application/json'].get('schema', {}))}")
    if "multipart/form-data" in content:
        form = content["multipart/form-data"].get("schema", {})
        props = sorted(form.get("properties", {}))
        required = sorted(form.get("required", []))
        kinds.append(f"form:{props}:required={required}")
    return {"required": bool(request_body.get("required")), "content": sorted(kinds)}


def collect_routes(app) -> list:
    """从运行中的 app 对象取路由表（与 OpenAPI 交叉校验用）。"""
    out = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path or path in STATIC_PATHS:
            continue
        for method in sorted(methods):
            if method in ("HEAD", "OPTIONS"):
                continue
            out.append(f"{method} {path}")
    # 只保留业务接口：FastAPI 自带的 /docs、/redoc、/openapi.json 不算契约
    return sorted(item for item in out if item.split(" ", 1)[1].startswith("/api/"))


# ==================== 场景探针（请求 → 响应） ====================
# 每个探针拿到"一次真实调用的响应骨架"。数据由 fixture 现场造，探针之间互不依赖。


def _probe_health(c, ctx=None) -> dict:
    r = c.get("/api/health")
    return {"status": r.status_code, "body": schema_of(r.json())}


def _probe_materials(c, ctx) -> dict:
    mid = ctx["mid"]
    out = {}
    r = c.get("/api/materials")
    out["list"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get("/api/materials", params={"course": "不存在课程"})
    out["list_empty"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get(f"/api/materials/{mid}")
    out["detail"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get("/api/materials/999999")
    out["detail_404"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post(
        "/api/materials/upload",
        files={"file": ("x.exe", b"MZ", "application/octet-stream")},
    )
    out["upload_400"] = {"status": r.status_code, "body": schema_of(r.json())}
    return out


# 上传接口单独测：它会真的落文件，必须放在独立临时目录里
def _probe_upload(c) -> dict:
    r = c.post(
        "/api/materials/upload",
        files={"file": ("样例.md", "监督学习需要标注数据。".encode("utf-8"), "text/markdown")},
        data={"course": "人工智能"},
    )
    body = r.json()
    return {
        "status": r.status_code,
        "body": schema_of(body),
        "id_field": "id" in body,
    }


def _probe_knowledge(c, ctx) -> dict:
    kid = ctx["kid"]
    out = {}
    r = c.get("/api/knowledge-points")
    out["list"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get("/api/knowledge-points", params={"course": "人工智能"})
    out["list_filtered"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.put(f"/api/knowledge-points/{kid}", json={"description": "改过的描述"})
    out["update"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.put(f"/api/knowledge-points/{kid}", json={})
    out["update_400"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/knowledge-points", json={"title": "   "})
    out["create_400"] = {"status": r.status_code, "body": schema_of(r.json())}
    return out


def _probe_tasks(c, ctx) -> dict:
    tid = ctx["tid"]
    out = {}
    r = c.get("/api/tasks")
    out["list"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.patch(f"/api/tasks/{tid}/status", json={"status": "doing"})
    out["patch_status"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.patch(f"/api/tasks/{tid}/status", json={"status": "非法值"})
    out["patch_status_400"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.patch("/api/tasks/999999/status", json={"status": "done"})
    out["patch_status_404"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/tasks", json={"title": "坏日期", "due_date": "不是日期"})
    out["create_400"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get("/api/tasks/due-soon")
    out["due_soon"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get("/api/tasks/due-soon", params={"days": 9999})
    out["due_soon_wide"] = {"status": r.status_code, "body": schema_of(r.json())}
    out["due_soon_wide_has_item"] = len(r.json()) >= 1

    return out


def _probe_questions(c, ctx) -> dict:
    kid, qid = ctx["kid"], ctx["qid"]
    out = {}
    r = c.get("/api/questions")
    out["list"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get("/api/questions", params={"kp_id": kid})
    out["list_by_kp"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/questions/generate", json={"kp_id": 999999, "num": 1})
    out["generate_404"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/practice/submit", json={"question_id": qid, "correct": True, "answer": "x"})
    out["submit"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/practice/submit", json={"question_id": 999999, "correct": False})
    out["submit_404"] = {"status": r.status_code, "body": schema_of(r.json())}
    return out


def _probe_wrong_book(c, ctx) -> dict:
    out = {}
    r = c.get("/api/wrong-book")
    body = r.json()
    out["list"] = {"status": r.status_code, "body": schema_of(body)}
    out["list_has_item"] = len(body) > 0
    if body:
        wid = body[0]["id"]
        r = c.patch(f"/api/wrong-book/{wid}", json={"review_marked": True})
        out["patch"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.patch("/api/wrong-book/999999", json={"resolved": True})
    out["patch_404"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.patch("/api/wrong-book/999999", json={})
    out["patch_400"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.get("/api/wrong-book", params={"only_unresolved": "false"})
    out["list_all"] = {"status": r.status_code, "body": schema_of(r.json())}
    return out


def _probe_stats(c, ctx) -> dict:
    r = c.get("/api/stats/overview")
    return {"status": r.status_code, "body": schema_of(r.json())}


def _probe_ai_config(c, ctx) -> dict:
    """只读配置，不写 .env；写配置的用例在 test_core.py 里已覆盖（要 monkeypatch env_file）。"""
    out = {}
    r = c.get("/api/config/ai")
    body = r.json()
    out["get"] = {"status": r.status_code, "body": schema_of(body)}
    out["presets"] = sorted(body.get("presets", {}))
    out["preset_item"] = schema_of(body["presets"]["zhipu"]) if body.get("presets") else None
    r = c.post("/api/config/ai", json={"api_key": "abc"})
    out["post_400_key"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/config/ai", json={"api_key": "abcdefghijk", "base_url": "ftp://x"})
    out["post_400_url"] = {"status": r.status_code, "body": schema_of(r.json())}
    return out


def _probe_ai_runtime(c, ctx) -> dict:
    out = {}
    r = c.post("/api/ai/test")
    out["test"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/ai/summarize", json={"material_id": 999999})
    out["summarize_404"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/ai/summarize", json={"material_id": ctx["mid"]})
    out["summarize"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/ai/ask", json={"question": "  "})
    out["ask_400"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/ai/ask", json={"question": "什么是监督学习", "material_id": ctx["mid"]})
    out["ask"] = {"status": r.status_code, "body": schema_of(r.json())}
    r = c.post("/api/ai/weak-analysis", json={})
    out["weak_analysis"] = {"status": r.status_code, "body": schema_of(r.json())}
    return out


# ==================== fixture ====================


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """临时库 + 临时上传目录 + 强制规则引擎；与 test_core.py 的 fixture 保持同构。"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(app_main, "DB_PATH", tmp_path / "contract.db")
    monkeypatch.setattr(app_main, "UPLOAD_DIR", upload_dir)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    app_main.init_db()
    from tests.conftest import attach_auth

    with TestClient(app_main.app) as c:
        attach_auth(c)  # 接口都要求登录，快照探针也必须在登录态下采集
        yield c
    for name in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL"):
        os.environ.pop(name, None)
    os.environ["DEEPSEEK_API_KEY"] = ""


@pytest.fixture()
def scenario(client) -> dict:
    """造一份最小可用的学习闭环数据，供各探针取 id。

    顺序固定：资料 → 知识点 → 3 道题 → 答错 1 题（沉淀错题）→ 任务。
    """
    up = client.post(
        "/api/materials/upload",
        files={
            "file": (
                "监督学习.md",
                ("监督学习需要标注数据。无监督学习不需要标注。强化学习靠奖励信号。").encode(
                    "utf-8"
                ),
                "text/markdown",
            )
        },
        data={"course": "人工智能"},
    )
    assert up.status_code == 200, up.text
    mid = up.json()["id"]

    kp = client.post(
        "/api/knowledge-points",
        json={"title": "机器学习范式", "course": "人工智能", "material_id": mid},
    )
    assert kp.status_code == 200, kp.text
    kid = kp.json()["id"]

    gen = client.post("/api/questions/generate", json={"kp_id": kid, "num": 3})
    assert gen.status_code == 200, gen.text
    questions = client.get("/api/questions", params={"kp_id": kid}).json()
    assert len(questions) == 3
    qid = questions[0]["id"]
    client.post("/api/practice/submit", json={"question_id": qid, "correct": False, "answer": "错"})

    task = client.post(
        "/api/tasks",
        json={"title": "复习范式", "course": "人工智能", "due_date": "2099-01-01"},
    )
    assert task.status_code == 200, task.text

    return {"mid": mid, "kid": kid, "qid": qid, "tid": task.json()["id"]}


# ==================== 测试 ====================


def test_接口清单与实测一致():
    """main.py 里挂了多少业务接口，就必须在 CONTRACT_MANIFEST 里登记多少。"""
    actual = set(collect_routes(app_main.app))
    assert actual == CONTRACT_MANIFEST, (
        "接口清单与代码不一致。\n"
        f"  代码里有、清单里没有：{sorted(actual - CONTRACT_MANIFEST)}\n"
        f"  清单里有、代码里没有：{sorted(CONTRACT_MANIFEST - actual)}\n"
        "新增/删除接口时，请同步更新 CONTRACT_MANIFEST 并刷新快照。"
    )
    assert len(CONTRACT_MANIFEST) == 33, f"接口数量应为 33，当前 {len(CONTRACT_MANIFEST)}"


def test_openapi_与路由表一致():
    """OpenAPI 文档不得漏掉任何已注册路由（防止某些接口没进 schema）。"""
    documented = set(collect_openapi(app_main.app))
    assert (
        CONTRACT_MANIFEST <= documented
    ), f"OpenAPI 缺少接口：{sorted(CONTRACT_MANIFEST - documented)}"


def test_结构采集函数自检():
    """采集器本身的行为要锁住：快照的可信度取决于它。"""
    assert schema_of({"b": 1, "a": "x"}) == {"a": "string", "b": "integer"}
    assert schema_of([1, 2]) == "list<integer>"
    assert schema_of([]) == "list<any>"
    assert schema_of([1, None]) == "list<integer|null>"
    assert schema_of(True) == "boolean"
    assert schema_of(1.5) == "number"
    assert schema_of(None) == "null"
    # 列表里的对象：结构一致只描述一次，结构不一则列出联合
    assert schema_of([{"y": 1}, {"y": 2}]) == 'list<{"y": "integer"}>'
    assert schema_of([{"y": 1}, {"y": None}]) == 'list<{"y": "integer"}|{"y": "null"}>'
    assert schema_of({"x": [{"y": 1}]}) == {"x": 'list<{"y": "integer"}>'}


def test_契约快照(client, scenario):
    """采集 26 个接口的结构，与快照逐项比对。"""
    probes = {
        "GET /api/health": _probe_health,
        "POST /api/materials/upload": _probe_upload,
        "GET /api/materials": _probe_materials,
        "GET /api/knowledge-points": _probe_knowledge,
        "GET /api/tasks": _probe_tasks,
        "GET /api/questions": _probe_questions,
        "GET /api/wrong-book": _probe_wrong_book,
        "GET /api/stats/overview": _probe_stats,
        "GET /api/config/ai": _probe_ai_config,
        "POST /api/ai/test": _probe_ai_runtime,
    }
    # 上传探针会真实写库，放在最后跑，避免污染前面的场景数据
    ordered = [(k, v) for k, v in probes.items() if k != "POST /api/materials/upload"]
    ordered.append(("POST /api/materials/upload", probes["POST /api/materials/upload"]))

    actual = {
        "version": SNAPSHOT_VERSION,
        "openapi": collect_openapi(client.app),
        "probes": {},
    }
    for name, probe in ordered:
        actual["probes"][name] = (
            probe(client) if probe is _probe_upload else probe(client, scenario)
        )

    if not SNAPSHOT.exists():
        _write_snapshot(actual)
        pytest.skip(f"快照不存在，已生成基线：{SNAPSHOT}（请 git add 后重跑）")

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    diff = _diff(expected, actual)
    assert not diff, "接口契约与快照不一致（重构回归）：\n" + "\n".join(f"  - {d}" for d in diff)
    # 顺手核对：清单里的 26 个接口都出现在 OpenAPI 里
    missing = [key for key in CONTRACT_MANIFEST if key not in actual["openapi"]]
    assert not missing, f"OpenAPI 中缺少接口：{missing}"


# ==================== 快照读写与差异 ====================


def _write_snapshot(payload: dict) -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _diff(expected, actual, path: str = "") -> list:
    """递归比较，返回人类可读的差异行（只看结构，不比较值）。"""
    out = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            here = f"{path}.{key}" if path else key
            if key not in actual:
                out.append(f"{here}: 快照里有、实际没有")
            elif key not in expected:
                out.append(f"{here}: 实际多出来（快照没有）")
            else:
                out.extend(_diff(expected[key], actual[key], here))
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        if expected != actual:
            only_old = [x for x in expected if x not in actual]
            only_new = [x for x in actual if x not in expected]
            if only_old:
                out.append(f"{path}: 快照有 {only_old}，实际没有")
            if only_new:
                out.append(f"{path}: 实际多出 {only_new}")
            if not only_old and not only_new:
                out.append(f"{path}: 顺序变了 {expected} -> {actual}")
        return out
    if expected != actual:
        out.append(f"{path}: {expected!r} -> {actual!r}")
    return out


# ==================== 生成入口 ====================
# 单独运行本文件即重新生成快照：python tests/test_contract.py


def regenerate() -> int:
    """在不依赖 pytest 的情况下重放一遍探针并写快照，返回退出码。"""
    import shutil
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="contract_"))
    saved = (app_main.DB_PATH, app_main.UPLOAD_DIR)
    try:
        app_main.DB_PATH = tmp / "contract.db"
        app_main.UPLOAD_DIR = tmp / "uploads"
        app_main.UPLOAD_DIR.mkdir()
        app_main.init_db()
        os.environ.pop("AI_API_KEY", None)
        os.environ["DEEPSEEK_API_KEY"] = ""
        with TestClient(app_main.app) as c:
            from tests.conftest import attach_auth

            attach_auth(c)
            scenario = _build_scenario(c)
            probes = [
                ("GET /api/health", _probe_health, False),
                ("GET /api/materials", _probe_materials, True),
                ("GET /api/knowledge-points", _probe_knowledge, True),
                ("GET /api/tasks", _probe_tasks, True),
                ("GET /api/questions", _probe_questions, True),
                ("GET /api/wrong-book", _probe_wrong_book, True),
                ("GET /api/stats/overview", _probe_stats, True),
                ("GET /api/config/ai", _probe_ai_config, True),
                ("POST /api/ai/test", _probe_ai_runtime, True),
                ("POST /api/materials/upload", _probe_upload, False),
            ]
            payload = {
                "version": SNAPSHOT_VERSION,
                "openapi": collect_openapi(c.app),
                "probes": {
                    name: (probe(c, scenario) if uses_ctx else probe(c))
                    for name, probe, uses_ctx in probes
                },
            }
    finally:
        app_main.DB_PATH, app_main.UPLOAD_DIR = saved
        shutil.rmtree(tmp, ignore_errors=True)

    _write_snapshot(payload)
    total = len(payload["openapi"])
    print(f"已生成快照：{SNAPSHOT}")
    print(f"  OpenAPI 接口：{total} 个 | 探针：{len(payload['probes'])} 组")
    return 0


def _build_scenario(client) -> dict:
    """与 pytest fixture 相同的造数逻辑，抽出来供 regenerate 复用。"""
    up = client.post(
        "/api/materials/upload",
        files={
            "file": (
                "监督学习.md",
                ("监督学习需要标注数据。无监督学习不需要标注。强化学习靠奖励信号。").encode(
                    "utf-8"
                ),
                "text/markdown",
            )
        },
        data={"course": "人工智能"},
    )
    mid = up.json()["id"]
    kp = client.post(
        "/api/knowledge-points",
        json={"title": "机器学习范式", "course": "人工智能", "material_id": mid},
    )
    kid = kp.json()["id"]
    client.post("/api/questions/generate", json={"kp_id": kid, "num": 3})
    qid = client.get("/api/questions", params={"kp_id": kid}).json()[0]["id"]
    client.post("/api/practice/submit", json={"question_id": qid, "correct": False, "answer": "错"})
    task = client.post(
        "/api/tasks",
        json={"title": "复习范式", "course": "人工智能", "due_date": "2099-01-01"},
    )
    return {"mid": mid, "kid": kid, "qid": qid, "tid": task.json()["id"]}


if __name__ == "__main__":
    raise SystemExit(regenerate())
