import os

# Получаем путь к текущей директории
current_dir = os.path.dirname(os.path.abspath(__file__))

# Проходим по всем файлам в текущей папке
for filename in os.listdir(current_dir):
    filepath = os.path.join(current_dir, filename)

    # Пропускаем директории и сам скрипт temp.py
    if os.path.isfile(filepath) and filename != 'temp.py':
        try:
            # Читаем содержимое файла
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Заменяем все 1 на 2
            new_content = content.replace('👨💻', '👨‍💻')
            new_content = new_content.replace('\n\n', '\n')

            # Записываем изменённое содержимое обратно в файл
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)

            print(f"✓ Файл '{filename}' обработан")

        except Exception as e:
            print(f"✗ Ошибка при обработке '{filename}': {e}")

print("Готово!")
