from locust import HttpUser, task, between

class LegalizeStressUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # Если API требует авторизации, можно залогиниться здесь
        pass

    @task(3)
    def search_clients_by_name(self):
        # Имитация поиска клиента по имени
        self.client.get("/clients/search/?q=John", name="Search Clients (Name)")

    @task(2)
    def search_clients_by_email(self):
        # Имитация поиска клиента по email (где сейчас не хватает индекса!)
        self.client.get("/clients/search/?q=test@example.com", name="Search Clients (Email)")

    @task(4)
    def view_dashboard(self):
        # Имитация загрузки дашборда (тяжелые агрегационные запросы)
        self.client.get("/clients/", name="Dashboard View")
