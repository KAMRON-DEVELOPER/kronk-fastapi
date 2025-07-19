import ssl

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend, RedisScheduleSource

from settings.my_config import get_settings

settings = get_settings()

ssl_params = {
    "ssl_ca_certs": str(settings.CA_PATH),
    "ssl_certfile": str(settings.FASTAPI_CLIENT_CERT_PATH),
    "ssl_keyfile": str(settings.FASTAPI_CLIENT_KEY_PATH),
    "ssl_cert_reqs": ssl.CERT_REQUIRED,
    "ssl_check_hostname": True,
}

redis_url = f"rediss://@{settings.REDIS_HOST}:6379"

ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(settings.CA_PATH))
ssl_context.load_cert_chain(certfile=str(settings.FASTAPI_CLIENT_CERT_PATH), keyfile=str(settings.FASTAPI_CLIENT_KEY_PATH))
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED

broker = ListQueueBroker(
    url=redis_url,
    ssl=ssl_context,
).with_result_backend(result_backend=RedisAsyncResultBackend(
    redis_url=redis_url,
    result_ex_time=600,
    ssl=ssl_context,
),
)

redis_schedule_source = RedisScheduleSource(
    url=redis_url,
    ssl=ssl_context,
)

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker=broker), redis_schedule_source],
)
