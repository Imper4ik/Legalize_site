# Deployment

## Обязательные переменные окружения

Для продакшена необходимо задать переменную `PDF_FONT_PATH` с абсолютным путём к файлу шрифта TrueType/OpenType,
который будет использоваться для генерации PDF (например, `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Бэкапы

Инструкция по включению и восстановлению бэкапов на Railway находится в документе: [docs/backups.md](backups.md).
