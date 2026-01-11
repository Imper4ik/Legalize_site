[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Templates

This folder contains the global HTML templates for the project.

## Structure

*   **`base.html`**: The main layout file (header, footer, navigation). All other pages inherit from this file.
*   **`account/`**: Templates for authentication (login, logout, password reset) provided by `django-allauth`.
*   **`clients/`**: Possibly overrides for templates from the `clients` app, or global templates related to clients.
*   **`includes/`**: Reusable HTML snippets (e.g., navbar, sidebar, messages) included in other templates using `{% include ... %}`.
*   **`socialaccount/`**: Templates for social login (Google, Facebook) via `django-allauth`.

---

# Polski <a name="polski"></a>

# Szablony (Templates)

Ten folder zawiera globalne szablony HTML dla projektu.

## Struktura

*   **`base.html`**: Główny plik układu (nagłówek, stopka, nawigacja). Wszystkie inne strony dziedziczą po tym pliku.
*   **`account/`**: Szablony uwierzytelniania (logowanie, wylogowanie, reset hasła) dostarczane przez `django-allauth`.
*   **`clients/`**: Możliwe nadpisania szablonów z aplikacji `clients` lub globalne szablony związane z klientami.
*   **`includes/`**: Fragmenty HTML wielokrotnego użytku (np. pasek nawigacji, pasek boczny, komunikaty) dołączane do innych szablonów za pomocą `{% include ... %}`.
*   **`socialaccount/`**: Szablony logowania społecznościowego (Google, Facebook) przez `django-allauth`.

---

# Русский <a name="русский"></a>

# Шаблоны (Templates)

Эта папка содержит глобальные HTML-шаблоны проекта.

## Структура

*   **`base.html`**: Главный файл макета (шапка, подвал, навигация). Все остальные страницы наследуются от этого файла.
*   **`account/`**: Шаблоны аутентификации (вход, выход, сброс пароля), предоставляемые `django-allauth`.
*   **`clients/`**: Возможно, переопределения шаблонов из приложения `clients` или глобальные шаблоны, связанные с клиентами.
*   **`includes/`**: Переиспользуемые фрагменты HTML (например, навбар, сайдбар, сообщения), включаемые в другие шаблоны через `{% include ... %}`.
*   **`socialaccount/`**: Шаблоны социального входа (Google, Facebook) через `django-allauth`.
