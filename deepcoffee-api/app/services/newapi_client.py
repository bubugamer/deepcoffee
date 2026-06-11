"""HTTP client for the new-api admin API.

DeepCoffee 用它管理「影子计费账户」：为每个用户在 new-api 建用户、配额、内部 token。
对接的是 new-api 的 admin/self 路由（one-api 派生）。需配置 NEW_API_BASE_URL + NEW_API_ADMIN_TOKEN。

注意：以下 HTTP 细节（路径、字段、token 创建流程）依据 new-api 源码契约编写，
**待 new-api 部署后做一次实连校准**（尤其 create_token 的 login→/api/token 流程）。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError


class NewApiError(AppError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(status_code, "new_api_error", message)


class NewApiClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.new_api_enabled:
            raise NewApiError("new-api is not configured.", status_code=503)
        self.base_url = self.settings.new_api_base_url.rstrip("/")

    def _admin_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.new_api_admin_token}",
            "New-API-User": self.settings.new_api_admin_user_id,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _unwrap(resp: httpx.Response) -> Any:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # 非 2xx 也包成 NewApiError，让上层（get_quota/ensure_shadow_account）统一按降级处理。
            raise NewApiError(f"new-api HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
        body = resp.json()
        if isinstance(body, dict) and "success" in body:
            if not body.get("success"):
                raise NewApiError(body.get("message") or "new-api request failed.")
            return body.get("data")
        return body

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """统一发请求 + 解包；连接超时/网络错误也包成 NewApiError，便于上层优雅降级。"""
        headers = kwargs.pop("headers", None) or self._admin_headers()
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=20) as client:
                resp = await client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:  # ConnectError / TimeoutException / etc.
            raise NewApiError(f"new-api unreachable at {self.base_url}: {exc}", status_code=503) from exc
        return self._unwrap(resp)

    async def create_user(self, *, username: str, password: str, display_name: str | None = None) -> dict[str, Any]:
        """POST /api/user/  (AdminAuth) 建影子用户。"""
        payload = {"username": username, "password": password, "display_name": display_name or username}
        await self._request("POST", "/api/user/", json=payload)
        # CreateUser 不回传 id，按用户名搜索取回。
        return await self.get_user_by_username(username)

    async def get_user(self, newapi_user_id: str | int) -> dict[str, Any]:
        """GET /api/user/{id}  → {quota, used_quota, request_count, group, ...}"""
        return await self._request("GET", f"/api/user/{newapi_user_id}")

    async def delete_user(self, newapi_user_id: str | int) -> None:
        """DELETE /api/user/{id}  删除影子用户。

        repair 端点只在这个调用成功，或确认远端用户本来就不存在时，才会删除本地 link。
        这里不吞异常，避免 new-api 临时故障时把本地映射提前清掉。
        """
        await self._request("DELETE", f"/api/user/{newapi_user_id}")

    async def get_user_by_username(self, username: str) -> dict[str, Any]:
        """GET /api/user/search?keyword=  取回刚建用户（含 id）。"""
        data = await self._request("GET", "/api/user/search", params={"keyword": username})
        items = data.get("items", data) if isinstance(data, dict) else data
        for item in items or []:
            if item.get("username") == username:
                return item
        raise NewApiError(f"new-api user '{username}' not found after create.")

    async def set_user_quota(self, newapi_user_id: str | int, *, quota: int) -> None:
        """覆盖式设置用户配额（quota 为 new-api 内部单位）。

        走 `POST /api/user/manage` 的 add_quota/override（AdminAuth）——比 PUT /api/user/
        需要全量用户对象更省事，也避开了旧 PUT 路径的 redis EXECABORT。
        """
        await self._request(
            "POST",
            "/api/user/manage",
            json={"id": int(newapi_user_id), "action": "add_quota", "mode": "override", "value": int(quota)},
        )

    async def create_api_token(self, *, username: str, password: str, name: str = "deepcoffee") -> str:
        """为影子用户创建模型调用 token（sk-...）并取回完整 key。

        token 创建/取 key 都是 self 路由（UserAuth），故以该影子用户登录后操作。
        **实连校准（2026-06-03）**：new-api 在 list/get 里把 key 打码，创建响应也不回传 key；
        真 key 要走 `POST /api/token/{id}/key`（GetTokenKey，对 owner 返回完整 key）。
        整个流程在一个 httpx client 内完成，靠 session cookie 维持登录态。
        """
        async with httpx.AsyncClient(base_url=self.base_url, timeout=20) as client:
            login = await client.post("/api/user/login", json={"username": username, "password": password})
            login_data = self._unwrap(login)  # 设置 session cookie，返回用户信息
            uid = (login_data or {}).get("id") if isinstance(login_data, dict) else None
            headers = {"New-API-User": str(uid)} if uid is not None else {}

            create = await client.post(
                "/api/token/",
                headers=headers,
                json={"name": name, "unlimited_quota": True, "expired_time": -1, "model_limits_enabled": False},
            )
            self._unwrap(create)  # 创建响应只回 success，不含 key

            listed = await client.get("/api/token/", headers=headers, params={"p": 0, "page_size": 100})
            data = self._unwrap(listed)
            items = data.get("items", data) if isinstance(data, dict) else data
            token_id = None
            for item in sorted(items or [], key=lambda x: x.get("id", 0), reverse=True):
                if item.get("name") == name:
                    token_id = item.get("id")
                    break
            if token_id is None:
                raise NewApiError("could not find created new-api token by name.")

            key_resp = await client.post(f"/api/token/{token_id}/key", headers=headers, json={})
            key_data = self._unwrap(key_resp)
        key = (key_data or {}).get("key") if isinstance(key_data, dict) else None
        if not key:
            raise NewApiError("new-api did not return the full token key.")
        return key if key.startswith("sk-") else f"sk-{key}"
