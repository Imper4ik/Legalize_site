import os
import sys
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legalize_site.settings.development")
import django
django.setup()

from clients.models import Client
from django.db import connection

# Убедимся, что мы не трогаем защищенные аккаунты
PROTECTED_EMAILS = ["nindse@gmail.com", "afanasenko860@gmail.com"]

def run_db_query(thread_id, queries_per_thread):
    # Каждому потоку нужно свое соединение, Django сделает это автоматически
    # Но мы должны закрывать соединение после работы потока
    try:
        for i in range(queries_per_thread):
            search_type = random.choice(["email", "name", "phone", "case"])
            
            if search_type == "email":
                # Имитация поиска по email
                list(Client.objects.filter(email__icontains="test").values('id'))
            elif search_type == "name":
                # Имитация поиска по имени
                list(Client.objects.filter(first_name__icontains="John", last_name__icontains="Doe").values('id'))
            elif search_type == "phone":
                # Имитация поиска по телефону
                list(Client.objects.filter(phone__icontains="+48").values('id'))
            elif search_type == "case":
                # Имитация запроса тяжелого дашборда со статусами
                list(Client.objects.with_health_stats().filter(workflow_stage="waiting_decision").values('id')[:50])
    finally:
        connection.close()

def run_stress_test(num_threads=20, queries_per_thread=50):
    print(f"Запуск стресс-теста: {num_threads} потоков по {queries_per_thread} запросов каждый...")
    print(f"Всего запросов: {num_threads * queries_per_thread}")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i in range(num_threads):
            futures.append(executor.submit(run_db_query, i, queries_per_thread))
            
        for f in futures:
            f.result() # Дождаться завершения или выбросить ошибку
            
    elapsed = time.time() - start_time
    qps = (num_threads * queries_per_thread) / elapsed
    
    print(f"Стресс-тест завершен за {elapsed:.2f} сек.")
    print(f"Производительность: {qps:.2f} запросов в секунду (QPS)")
    print(f"Среднее время ответа БД: {(elapsed / (num_threads * queries_per_thread)) * 1000:.2f} мс")

if __name__ == "__main__":
    count = Client.objects.count()
    print(f"Текущее количество клиентов в БД: {count}")
    run_stress_test(num_threads=50, queries_per_thread=10)
