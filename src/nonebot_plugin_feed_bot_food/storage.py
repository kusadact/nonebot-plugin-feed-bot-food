from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1


class StateStorageError(RuntimeError):
    pass


def default_state_path() -> Path:
    try:
        import nonebot_plugin_localstore as store

        directory = store.get_plugin_data_dir()
    except Exception:
        directory = Path("data") / "nonebot_plugin_feed_bot_food"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "state.json"


class JsonStateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()

    async def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": SCHEMA_VERSION, "bots": {}}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            backup = self.path.with_suffix(f"{self.path.suffix}.corrupt")
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                pass
            raise StateStorageError(f"无法读取 JSON 状态文件: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("bots", {}), dict):
            raise StateStorageError("JSON 状态文件格式无效")
        try:
            version = int(data.get("schema_version", 1))
        except (TypeError, ValueError) as exc:
            raise StateStorageError("JSON 状态版本格式无效") from exc
        migrated = False
        if version == LEGACY_SCHEMA_VERSION:
            data = _migrate_v1_to_v2(data)
            migrated = True
        elif version != SCHEMA_VERSION:
            raise StateStorageError(f"不支持的 JSON 状态版本: {version}")
        data.setdefault("schema_version", SCHEMA_VERSION)
        if migrated:
            await self.save(data)
        return data

    async def save(self, data: dict[str, Any]) -> None:
        data = dict(data)
        data["schema_version"] = SCHEMA_VERSION
        data.setdefault("bots", {})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = file.name
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        except OSError as exc:
            raise StateStorageError(f"无法写入 JSON 状态文件: {exc}") from exc
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    bots = data.get("bots", {})
    for raw_state in bots.values():
        if not isinstance(raw_state, dict):
            raise StateStorageError("JSON 状态中的 Bot 数据格式无效")
        daily = raw_state.get("daily", {})
        if not isinstance(daily, dict):
            raise StateStorageError("JSON 状态中的每日统计格式无效")
        for raw_daily in daily.values():
            if not isinstance(raw_daily, dict):
                raise StateStorageError("JSON 状态中的每日统计项格式无效")
            raw_daily.setdefault("weight_change", "0.00")
    data["schema_version"] = SCHEMA_VERSION
    return data
