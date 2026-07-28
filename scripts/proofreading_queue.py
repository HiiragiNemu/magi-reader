#!/usr/bin/env python3
"""Operate the Cloudflare KV proofreading queue from GitHub Actions.

Commands are deliberately narrow: discover a namespace, claim one approved
submission, mark a result, and synchronize existing PR states. Queue updates
maintain the same status indexes as the website API.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

RECORD_PREFIX = "proofreading:record:"
INDEX_PREFIX = "proofreading:index:"
MAX_TIMESTAMP = 9_999_999_999_999
VALID_STATUSES = {
    "pending", "held", "approved", "processing", "stale", "rejected",
    "pr_created", "merged", "closed",
}
TRANSITIONS = {
    "pending": {"held", "approved", "rejected"},
    "held": {"pending", "approved", "rejected"},
    "approved": {"held", "processing", "stale"},
    "processing": {"held", "stale", "pr_created"},
    "stale": {"held", "rejected"},
    "rejected": set(),
    "pr_created": {"merged", "closed"},
    "merged": set(),
    "closed": set(),
}


class QueueError(RuntimeError):
    pass


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def reverse_timestamp(value: str) -> str:
    try:
        milliseconds = int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except (ValueError, OverflowError):
        milliseconds = int(time.time() * 1000)
    milliseconds = max(0, min(MAX_TIMESTAMP, milliseconds))
    return str(MAX_TIMESTAMP - milliseconds).zfill(13)


def index_key(status: str, date: str, submission_id: str) -> str:
    return f"{INDEX_PREFIX}{status}:{reverse_timestamp(date)}:{submission_id}"


def record_key(submission_id: str) -> str:
    return f"{RECORD_PREFIX}{submission_id}"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise QueueError(f"缺少环境变量 {name}")
    return value


@dataclass
class HttpResponse:
    status: int
    body: bytes


class CloudflareKvClient:
    def __init__(self, *, account_id: str, api_token: str, namespace_id: str | None = None):
        self.account_id = account_id
        self.api_token = api_token
        self.namespace_id = namespace_id
        self.api_root = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/storage/kv/namespaces"

    def _request(self, method: str, url: str, body: bytes | None = None, content_type: str = "application/json") -> HttpResponse:
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": content_type,
                "User-Agent": "magi-reader-proofreading-queue",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return HttpResponse(response.status, response.read())
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise QueueError(f"Cloudflare API {method} {url} 失败（HTTP {exc.code}）: {payload[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise QueueError(f"无法连接 Cloudflare API: {exc}") from exc

    def list_namespaces(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        page = 1
        while True:
            response = self._request("GET", f"{self.api_root}?per_page=100&page={page}")
            payload = json.loads(response.body)
            if not payload.get("success"):
                raise QueueError(f"Cloudflare namespace 列表响应失败: {payload}")
            values = payload.get("result") or []
            if not isinstance(values, list):
                raise QueueError("Cloudflare namespace 列表格式无效")
            result.extend(value for value in values if isinstance(value, dict))
            info = payload.get("result_info") or {}
            total_pages = int(info.get("total_pages") or page)
            if page >= total_pages:
                return result
            page += 1

    def create_namespace(self, title: str) -> str:
        response = self._request("POST", self.api_root, json.dumps({"title": title}).encode())
        payload = json.loads(response.body)
        namespace_id = payload.get("result", {}).get("id") if payload.get("success") else None
        if not isinstance(namespace_id, str) or not namespace_id:
            raise QueueError(f"创建 KV namespace 失败: {payload}")
        return namespace_id

    def _namespace_root(self) -> str:
        if not self.namespace_id:
            raise QueueError("未配置 KV namespace ID")
        return f"{self.api_root}/{self.namespace_id}"

    def get(self, key: str) -> str | None:
        encoded = urllib.parse.quote(key, safe="")
        url = f"{self._namespace_root()}/values/{encoded}"
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "User-Agent": "magi-reader-proofreading-queue",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            payload = exc.read().decode("utf-8", errors="replace")
            raise QueueError(f"读取 KV {key} 失败（HTTP {exc.code}）: {payload[:1000]}") from exc

    def put(self, key: str, value: str) -> None:
        encoded = urllib.parse.quote(key, safe="")
        self._request(
            "PUT",
            f"{self._namespace_root()}/values/{encoded}",
            value.encode("utf-8"),
            "text/plain; charset=utf-8",
        )

    def delete(self, key: str) -> None:
        encoded = urllib.parse.quote(key, safe="")
        self._request("DELETE", f"{self._namespace_root()}/values/{encoded}")

    def list_keys(self, *, prefix: str, limit: int = 1000, cursor: str | None = None) -> tuple[list[str], str | None, bool]:
        params = {"prefix": prefix, "limit": str(limit)}
        if cursor:
            params["cursor"] = cursor
        query = urllib.parse.urlencode(params)
        response = self._request("GET", f"{self._namespace_root()}/keys?{query}")
        payload = json.loads(response.body)
        if not payload.get("success"):
            raise QueueError(f"Cloudflare KV key 列表响应失败: {payload}")
        values = payload.get("result") or []
        keys = [value["name"] for value in values if isinstance(value, dict) and isinstance(value.get("name"), str)]
        info = payload.get("result_info") or {}
        next_cursor = info.get("cursor") if isinstance(info.get("cursor"), str) else None
        complete = not bool(next_cursor)
        return keys, next_cursor, complete


class GithubClient:
    def __init__(self, *, token: str, repository: str):
        self.token = token
        self.repository = repository

    def pull_request(self, number: int) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repository}/pulls/{number}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "magi-reader-proofreading-queue",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                value = json.loads(response.read())
                if not isinstance(value, dict):
                    raise QueueError("GitHub PR 响应格式无效")
                return value
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise QueueError(f"GitHub PR #{number} 查询失败（HTTP {exc.code}）: {payload[:1000]}") from exc


def parse_record(raw: str, expected_id: str | None = None) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QueueError("KV 投稿记录不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise QueueError("KV 投稿记录不是对象")
    submission_id = value.get("id")
    status = value.get("status")
    if not isinstance(submission_id, str) or not submission_id.startswith("ps_"):
        raise QueueError("KV 投稿记录 id 无效")
    if expected_id and submission_id != expected_id:
        raise QueueError("KV 投稿记录 id 与 key 不一致")
    if status not in VALID_STATUSES:
        raise QueueError("KV 投稿记录状态无效")
    return value


def transition(client: CloudflareKvClient, record: dict[str, Any], next_status: str, patch: Mapping[str, Any] | None = None) -> dict[str, Any]:
    current = str(record.get("status") or "")
    if next_status not in VALID_STATUSES:
        raise QueueError(f"无效目标状态: {next_status}")
    if current != next_status and next_status not in TRANSITIONS.get(current, set()):
        raise QueueError(f"非法状态转换: {current} -> {next_status}")
    now = iso_now()
    next_index = index_key(next_status, now, str(record["id"]))
    updated = {**record, **(patch or {}), "status": next_status, "updated_at": now, "index_key": next_index}
    client.put(record_key(str(record["id"])), json.dumps(updated, ensure_ascii=False, separators=(",", ":")))
    client.put(next_index, record_key(str(record["id"])))
    old_index = record.get("index_key")
    if isinstance(old_index, str) and old_index and old_index != next_index:
        client.delete(old_index)
    return updated


def load_record(client: CloudflareKvClient, submission_id: str) -> dict[str, Any]:
    raw = client.get(record_key(submission_id))
    if raw is None:
        raise QueueError(f"没有找到投稿 {submission_id}")
    return parse_record(raw, submission_id)


def iter_status_records(client: CloudflareKvClient, status: str, maximum: int = 10_000):
    cursor = None
    yielded = 0
    while yielded < maximum:
        keys, cursor, complete = client.list_keys(prefix=f"{INDEX_PREFIX}{status}:", cursor=cursor)
        for key in sorted(keys):
            pointer = client.get(key)
            if not pointer or not pointer.startswith(RECORD_PREFIX):
                continue
            raw = client.get(pointer)
            if not raw:
                continue
            record = parse_record(raw)
            if record.get("status") != status or record.get("index_key") != key:
                continue
            yielded += 1
            yield record
            if yielded >= maximum:
                return
        if complete:
            return


def client_from_env(namespace_required: bool = True) -> CloudflareKvClient:
    namespace_id = os.environ.get("PROOFREADING_KV_NAMESPACE_ID", "").strip() or None
    if namespace_required and not namespace_id:
        raise QueueError("缺少 PROOFREADING_KV_NAMESPACE_ID")
    return CloudflareKvClient(
        account_id=require_env("CLOUDFLARE_ACCOUNT_ID"),
        api_token=require_env("CLOUDFLARE_API_TOKEN"),
        namespace_id=namespace_id,
    )


def command_namespace(args: argparse.Namespace) -> int:
    client = client_from_env(namespace_required=False)
    matches = [item for item in client.list_namespaces() if item.get("title") == args.title]
    if len(matches) > 1:
        raise QueueError(f"发现多个同名 KV namespace: {args.title}")
    if matches:
        namespace_id = matches[0].get("id")
    elif args.create:
        namespace_id = client.create_namespace(args.title)
    else:
        raise QueueError(f"没有找到 KV namespace: {args.title}")
    if not isinstance(namespace_id, str):
        raise QueueError("KV namespace ID 无效")
    print(namespace_id)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"namespace_id={namespace_id}\n")
    return 0


def command_claim(args: argparse.Namespace) -> int:
    client = client_from_env()
    record = next(iter_status_records(client, "approved", maximum=1), None)
    if record is None:
        print("没有等待处理的已批准投稿。")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
                handle.write("claimed=false\n")
        return 0
    updated = transition(client, record, "processing", {"processing_error": ""})
    Path(args.output).write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(updated["id"])
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write("claimed=true\n")
            handle.write(f"submission_id={updated['id']}\n")
    return 0


def command_mark(args: argparse.Namespace) -> int:
    client = client_from_env()
    record = load_record(client, args.id)
    patch: dict[str, Any] = {}
    if args.error is not None:
        patch["processing_error"] = args.error[:4000]
    if args.status == "pr_created":
        if not args.pr_number or not args.pr_url or not args.branch:
            raise QueueError("标记 pr_created 必须提供 PR 编号、URL 和分支")
        patch["pull_request"] = {
            "number": args.pr_number,
            "url": args.pr_url,
            "branch": args.branch,
            "created_at": iso_now(),
        }
    updated = transition(client, record, args.status, patch)
    print(json.dumps({"id": updated["id"], "status": updated["status"]}, ensure_ascii=False))
    return 0


def command_sync(args: argparse.Namespace) -> int:
    kv = client_from_env()
    github = GithubClient(
        token=require_env("GITHUB_TOKEN"),
        repository=os.environ.get("GITHUB_REPOSITORY", "HiiragiNemu/magi-reader"),
    )
    changed = 0
    for record in iter_status_records(kv, "pr_created", maximum=args.limit):
        pr = record.get("pull_request")
        number = pr.get("number") if isinstance(pr, dict) else None
        if not isinstance(number, int) or number <= 0:
            continue
        remote = github.pull_request(number)
        merged_at = remote.get("merged_at")
        state = remote.get("state")
        if merged_at:
            next_pr = {**pr, "merged_at": str(merged_at)}
            transition(kv, record, "merged", {"pull_request": next_pr, "processing_error": ""})
            changed += 1
        elif state == "closed":
            next_pr = {**pr, "closed_at": str(remote.get("closed_at") or iso_now())}
            transition(kv, record, "closed", {"pull_request": next_pr})
            changed += 1
    print(f"同步完成，更新 {changed} 条投稿。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    namespace = sub.add_parser("namespace")
    namespace.add_argument("--title", required=True)
    namespace.add_argument("--create", action="store_true")
    namespace.set_defaults(func=command_namespace)
    claim = sub.add_parser("claim")
    claim.add_argument("--output", required=True)
    claim.set_defaults(func=command_claim)
    mark = sub.add_parser("mark")
    mark.add_argument("--id", required=True)
    mark.add_argument("--status", choices=sorted(VALID_STATUSES), required=True)
    mark.add_argument("--error")
    mark.add_argument("--pr-number", type=int)
    mark.add_argument("--pr-url")
    mark.add_argument("--branch")
    mark.set_defaults(func=command_mark)
    sync = sub.add_parser("sync")
    sync.add_argument("--limit", type=int, default=100)
    sync.set_defaults(func=command_sync)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.func(args))
    except QueueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
