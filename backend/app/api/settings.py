"""引擎 / LLM 设置读写与连通性测试。"""
from fastapi import APIRouter, HTTPException

from .. import db
from ..providers.registry import get_provider

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_all_settings():
    """返回全部引擎配置（合并各引擎已注册字段）+ LLM 配置。"""
    from ..providers.registry import all_providers

    provider_configs = {p.meta.id: await p.get_config() for p in all_providers()}
    return {
        "providers": provider_configs,
        "llm": await db.get_setting("llm", {"base_url": "", "api_key": "", "model": ""}),
    }


@router.put("/providers/{provider_id}")
async def save_provider_settings(provider_id: str, config: dict):
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(404, f"引擎不存在：{provider_id}")
    await db.save_provider_config(provider_id, config)
    return {"ok": True}


@router.put("/llm")
async def save_llm_settings(config: dict):
    await db.set_setting("llm", {
        "base_url": (config.get("base_url") or "").strip(),
        "api_key": (config.get("api_key") or "").strip(),
        "model": (config.get("model") or "").strip(),
    })
    return {"ok": True}


@router.post("/test/providers/{provider_id}")
async def test_provider(provider_id: str):
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(404, f"引擎不存在：{provider_id}")
    ok, message = await provider.test_connection()
    return {"ok": ok, "message": message}
