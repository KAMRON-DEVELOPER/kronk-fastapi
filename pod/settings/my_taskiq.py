from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend, RedisScheduleSource

from settings.my_config import get_settings

settings = get_settings()

broker = ListQueueBroker(
    url=f"rediss://@{settings.REDIS_HOST}:6379",
    ssl=True,
    ssl_ca_certs=settings.CA_PATH,
    ssl_certfile=settings.FASTAPI_CLIENT_CERT_PATH,
    ssl_keyfile=settings.FASTAPI_CLIENT_KEY_PATH,
    ssl_cert_reqs="required",
    ssl_check_hostname=True
).with_result_backend(result_backend=RedisAsyncResultBackend(
    redis_url=f"rediss://@{settings.REDIS_HOST}:6379",
    result_ex_time=600,
    ssl=True,
    ssl_ca_certs=settings.CA_PATH,
    ssl_certfile=settings.FASTAPI_CLIENT_CERT_PATH,
    ssl_keyfile=settings.FASTAPI_CLIENT_KEY_PATH,
    ssl_cert_reqs="required",
    ssl_check_hostname=True
),
)

redis_schedule_source = RedisScheduleSource(
    url=f"rediss://@{settings.REDIS_HOST}:6379",
    ssl=True,
    ssl_ca_certs=settings.CA_PATH,
    ssl_certfile=settings.FASTAPI_CLIENT_CERT_PATH,
    ssl_keyfile=settings.FASTAPI_CLIENT_KEY_PATH,
    # ssl_ca_certs="/run/secrets/ca.pem",
    # ssl_certfile="/run/secrets/fastapi_client_cert.pem",
    # ssl_keyfile="/run/secrets/fastapi_client_key.pem",
    ssl_cert_reqs="required",
    ssl_check_hostname=True
)

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker=broker), redis_schedule_source],
)
