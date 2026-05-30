"""
启动celery： celery -A DjangoUserService worker -l INFO -P gevent -Q celery,email
"""

import os
from celery import Celery
from celery.signals import after_setup_logger
import logging

# 设置django的settings模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DjangoUserService.settings')

app = Celery('DjangoUserService')

app.conf.timezone = 'Asia/Shanghai'

# 日志管理
@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'log', 'django'))
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, 'celery.log'), encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

# 配置从settins.py中读取celery配置信息，所有Celery配置信息都要以CELERY_开头
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现任务，任务可以写在app/tasks.py中
app.autodiscover_tasks()

# 测试任务
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
