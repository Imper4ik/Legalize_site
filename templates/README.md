[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Root Templates

This directory contains the primary global templates for the project, located in the root `templates/` folder. These often take precedence over app-level templates.

## Files

### 1. `base.html`
The master layout template.
*   Contains the `<html>`, `<head>`, and `<body>` structure.
*   Includes global CSS/JS.
*   Defines blocks like `{% block content %}` that child templates override.

### 2. `403.html`
Custom "Permission Denied" error page.
*   Shown when a user accesses a view they are not authorized for (e.g., non-staff trying to access staff views).

## Subdirectories

*   **`account/`**: Templates for `django-allauth` (login, signup, password reset). Overrides default allauth templates.
*   **`admin/`**: Overrides for the Django Admin interface (e.g., custom branding).
*   **`clients/`**: Potential global overrides for client-related templates.
*   **`includes/`**: Reusable partials (e.g., headers, footers, navigation bars).
*   **`socialaccount/`**: Templates for social authentication providers.

---

# Polski <a name="polski"></a>

# Szablony Główne (Root Templates)

Ten katalog zawiera główne globalne szablony projektu, znajdujące się w głównym folderze `templates/`. Często mają one pierwszeństwo przed szablonami na poziomie aplikacji.

## Pliki

### 1. `base.html`
Główny szablon układu (master layout).
*   Zawiera strukturę `<html>`, `<head>` i `<body>`.
*   Dołącza globalne style CSS i skrypty JS.
*   Definiuje bloki, takie jak `{% block content %}`, które są nadpisywane przez szablony podrzędne.

### 2. `403.html`
Niestandardowa strona błędu "Brak uprawnień".
*   Wyświetlana, gdy użytkownik próbuje uzyskać dostęp do widoku, do którego nie ma uprawnień (np. osoba niebędąca pracownikiem próbuje wejść w panel pracownika).

## Podkatalogi

*   **`account/`**: Szablony dla `django-allauth` (logowanie, rejestracja, reset hasła). Nadpisują domyślne szablony allauth.
*   **`admin/`**: Nadpisania interfejsu panelu administratora Django (np. własny branding).
*   **`clients/`**: Ewentualne globalne nadpisania szablonów związanych z klientami.
*   **`includes/`**: Fragmenty wielokrotnego użytku (np. nagłówki, stopki, paski nawigacji).
*   **`socialaccount/`**: Szablony dla dostawców uwierzytelniania społecznościowego.

---

# Русский <a name="русский"></a>

# Корневые Шаблоны (Root Templates)

Этот каталог содержит основные глобальные шаблоны проекта, расположенные в корневой папке `templates/`. Они часто имеют приоритет над шаблонами уровня приложений.

## Файлы

### 1. `base.html`
Мастер-шаблон макета.
*   Содержит структуру `<html>`, `<head>` и `<body>`.
*   Подключает глобальные CSS и JS.
*   Определяет блоки, такие как `{% block content %}`, которые переопределяются дочерними шаблонами.

### 2. `403.html`
Кастомная страница ошибки "Доступ запрещен".
*   Показывается, когда пользователь заходит туда, куда ему нельзя (например, не-сотрудник пытается открыть админскую часть).

## Подпапки

*   **`account/`**: Шаблоны для `django-allauth` (вход, регистрация, сброс пароля). Переопределяют стандартные шаблоны библиотеки.
*   **`admin/`**: Переопределения интерфейса Django Admin (например, свой брендинг).
*   **`clients/`**: Возможные глобальные переопределения шаблонов клиентов.
*   **`includes/`**: Переиспользуемые фрагменты (навбары, футеры, хедеры).
*   **`socialaccount/`**: Шаблоны для провайдеров социального входа.
