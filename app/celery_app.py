"""Celery 实例与配置。

Broker（任务队列）与 Result Backend 均使用 Redis。任务定义在 app/tasks/ 下，
通过 include 注册，避免与 app 其它模块产生循环导入。

Worker 启动：
    celery -A app.celery_app worker --loglevel=info
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "rag_center",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.indexing"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
