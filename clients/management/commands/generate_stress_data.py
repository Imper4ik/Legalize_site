import time
from typing import Any

from django.core.management.base import BaseCommand
from faker import Faker

from clients.models import Client

fake = Faker()

class Command(BaseCommand):
    help = "Генерирует миллионы/тысячи записей для стресс-тестирования базы данных"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--clients", type=int, default=10000, help="Количество клиентов для создания")
        parser.add_argument("--batch-size", type=int, default=2000, help="Размер батча для bulk_create")

    def handle(self, *args: Any, **options: Any) -> None:
        total_clients = options["clients"]
        batch_size = options["batch_size"]

        self.stdout.write(self.style.WARNING(f"Начинаем генерацию {total_clients} клиентов..."))

        start_time = time.time()
        clients_created = 0

        while clients_created < total_clients:
            batch = []
            limit = min(batch_size, total_clients - clients_created)

            for _ in range(limit):
                batch.append(
                    Client(
                        first_name=fake.first_name(),
                        last_name=fake.last_name(),
                        email=fake.email(),
                        phone=fake.phone_number()[:20],
                        citizenship=fake.country()[:100],
                        application_purpose=fake.random_element(["work", "study", "family"]),
                        status=fake.random_element(["new", "pending", "approved", "rejected"]),
                    )
                )

            # bulk_create is much faster and does not trigger save() signals (which is good for pure DB load test)
            Client.objects.bulk_create(batch)
            clients_created += limit

            self.stdout.write(f"Создано {clients_created}/{total_clients}...")

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"Успешно создано {total_clients} клиентов за {elapsed:.2f} сек."))
