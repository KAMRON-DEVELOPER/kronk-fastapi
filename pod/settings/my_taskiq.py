from settings.my_config import get_settings
from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import (ListQueueBroker, RedisAsyncResultBackend,
                          RedisScheduleSource)

settings = get_settings()

redis_url = f"rediss://@{settings.REDIS_HOST}:6379?ssl_cert_reqs=required&ssl_ca_certs={str(settings.CA_PATH)}&ssl_certfile={str(settings.FASTAPI_CLIENT_CERT_PATH)}&ssl_keyfile={str(settings.FASTAPI_CLIENT_KEY_PATH)}"

broker = ListQueueBroker(url=redis_url).with_result_backend(result_backend=RedisAsyncResultBackend(redis_url=redis_url, result_ex_time=600))

redis_schedule_source = RedisScheduleSource(url=redis_url)

scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker=broker), redis_schedule_source])
