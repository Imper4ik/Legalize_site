# Code Review Summary

## 1. Клиентский портал удалён

В проекте больше нет Django-приложения `portal`, поэтому ранее описанные замечания по его формам, адаптерам и загрузке документов утратили актуальность. Если функциональность кабинета клиентов потребуется вновь, стоит пересмотреть архитектуру заново и учесть прежние выводы.

## 2. Committed virtual environment inflates the repository
*Files: `legalize_site/venv/*`*

The repository contains a complete Python virtual environment under `legalize_site/venv/` (for example, `pyvenv.cfg`).【F:legalize_site/venv/pyvenv.cfg†L1-L3】 Committing generated interpreter files bloats the repo and risks platform-specific incompatibilities. It's better to remove this directory from version control and add it to `.gitignore` so each developer (and Render) can build the environment locally.

