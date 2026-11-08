from os import listdir, makedirs, remove
from os import replace as replace_file
from os.path import exists, isdir, isfile, join, splitext

from core.layout import POSTS_DIR, TEXTS_DIR
from core.protect import lock_folder, unlock


def tidy_texts(root, rep):
    """Наводит порядок в тексте постов:
    1. .md из корня папки канала переезжают в «Текст постов»;
    2. копии .md в папках постов удаляются (вместо них media.py создаст ярлыки);
    3. все тексты в «Текст постов» защищаются от редактирования (только чтение).
    Текст не теряется: копия удаляется, только если такой же файл уже лежит в «Текст постов»."""
    if not isdir(root):
        return

    texts = join(root, TEXTS_DIR)
    moved = removed = 0
    errors = []

    # 1. корень папки канала -> «Текст постов»
    for name in listdir(root):
        path = join(root, name)
        stem, ext = splitext(name)
        if not (isfile(path) and ext == ".md" and stem.isdigit()):
            continue
        try:
            makedirs(texts, exist_ok=True)
            target = join(texts, name)
            unlock(path)
            if exists(target):
                remove(path)   # такой текст уже есть в «Текст постов»
            else:
                replace_file(path, target)
            moved += 1
        except OSError as error:
            errors.append(f"{name}: {error}")

    # 2. копии в папках постов
    posts_dir = join(root, POSTS_DIR)
    if isdir(posts_dir):
        for folder in listdir(posts_dir):
            post_dir = join(posts_dir, folder)
            copy = join(post_dir, f"{folder}.md")
            if not (folder.isdigit() and isdir(post_dir) and isfile(copy)):
                continue
            try:
                target = join(texts, f"{folder}.md")
                unlock(copy)
                if exists(target):
                    remove(copy)
                else:
                    makedirs(texts, exist_ok=True)
                    replace_file(copy, target)  # единственный экземпляр: переносим, а не удаляем
                removed += 1
            except OSError as error:
                errors.append(f"{folder}/{folder}.md: {error}")

    # 3. защита от редактирования
    locked = lock_folder(texts)

    if moved or removed:
        rep.log(f"Порядок: текстов перенесено {moved}, копий убрано {removed}.")
    if locked:
        rep.log(f"Защита: файлов только для чтения {locked}.")
    if errors:
        rep.log(f"Порядок: не удалось обработать {len(errors)} файлов (закройте их и повторите), "
                f"например {errors[0]}")