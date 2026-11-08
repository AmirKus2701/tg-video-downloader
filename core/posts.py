from os import makedirs
from os.path import join

from core.layout import META_NAME, TEXTS_DIR
from core.meta import load_meta, save_meta
from core.protect import write_locked
from core.telegram import iter_posts, scan_size, step
from core.utils import channel_folder, format_post, is_skipped, make_title


async def save_posts(client, entity, opts, rep):
    """Тексты постов в «Текст постов» (только для чтения) и данные постов в 0_meta.json.
    Возвращает число сохранённых постов."""
    root = channel_folder(opts.out_dir, entity)
    texts_dir = join(root, TEXTS_DIR)
    total, unit = await scan_size(client, entity, opts.limit)

    meta_path = join(root, META_NAME)
    meta = load_meta(meta_path)
    if not opts.dry_run:
        makedirs(texts_dir, exist_ok=True)

    done = count = 0
    try:
        async for group in iter_posts(client, entity, opts.limit):
            rep.check()
            done += step(group, opts.limit)

            post = next((m for m in group if m.text), None)
            if post and not any(is_skipped(m) for m in group):  # «авторские» заглушки пропускаем
                count += 1
                if not opts.dry_run:
                    # файл сохраняется и сразу защищается от редактирования
                    write_locked(join(texts_dir, f"{post.id}.md"), format_post(post.text))

                    meta.setdefault(str(post.id), {}).update({
                        "date": post.date.replace(tzinfo=None).isoformat(timespec="minutes"),
                        "views": post.views or 0,
                        "title": make_title(post),   # заголовок без markdown
                        "length": len(post.raw_text),
                    })

            rep.progress(done, total, f"тексты: {unit} {done}/{total}, сохранено {count}")
    finally:
        if not opts.dry_run:
            save_meta(meta_path, meta)  # данные сохраняем всегда, даже при остановке

    if opts.dry_run:
        rep.log(f"Тексты (пробный режим): постов {count}")
    else:
        rep.log(f"Тексты: сохранено постов {count}")
    return count