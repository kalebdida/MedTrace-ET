import os, shutil, tempfile, time, json
from pathlib import Path
import httpx
from huggingface_hub import HfApi

api = HfApi(token=os.environ["HF_TOKEN"])
space = os.environ["HF_SPACE_ID"]
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    revision = os.environ["GITHUB_SHA"]
    (root / "deployment_revision.txt").write_text(revision)
    for name in ["app.py", "server.py", "requirements.txt", "requirements-server.txt"]:
        shutil.copy(Path("backend") / name, root / name)
    for name in ["medtrace", "visual_model"]:
        shutil.copytree(
            Path("backend") / name,
            root / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copy("backend/Dockerfile.server", root / "Dockerfile")
    shutil.copy("hf-space/README.md", root / "README.md")
    commit = api.upload_folder(
        repo_id=space, repo_type="space", folder_path=tmp, delete_patterns=["*"]
    )
for attempt in range(120):
    info = api.space_info(space)
    runtime = api.get_space_runtime(space)
    if runtime.stage == "RUNNING" and info.sha == commit.oid:
        url = info.host
        if not url.startswith("https://"):
            url = "https://" + url
        try:
            health = httpx.get(url + "/health", timeout=30)
            health.raise_for_status()
            assert health.headers.get("X-Deployment-Revision") == revision
            body = json.loads(json.load(open("backend/events/parse.json"))["body"])
            parsed = httpx.post(url + "/parse", json=body, timeout=30)
            parsed.raise_for_status()
            assert health.json()["status"] == "ok" and parsed.json()["valid"]
            print("Live API:", url)
            break
        except (httpx.HTTPError, AssertionError):
            pass
    if runtime.stage in ("BUILD_ERROR", "RUNTIME_ERROR"):
        raise RuntimeError("Space failed; inspect Space logs")
    time.sleep(10)
else:
    raise TimeoutError("Space readiness deadline exceeded")
