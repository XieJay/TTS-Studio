"""引擎列表与内置音色。"""
from fastapi import APIRouter, HTTPException

from ..providers.base import ProviderError
from ..providers.registry import all_providers, get_provider, list_provider_info

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
async def providers():
    return await list_provider_info()


@router.get("/{provider_id}/voices")
async def provider_voices(provider_id: str):
    provider = get_provider(provider_id)
    if not provider:
        raise HTTPException(404, f"引擎不存在：{provider_id}")
    try:
        voices = await provider.list_voices()
    except ProviderError as exc:
        raise HTTPException(502, exc.message) from exc
    return [v.model_dump() for v in voices]
