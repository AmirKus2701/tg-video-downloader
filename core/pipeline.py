from asyncio import to_thread

from core.media import save_media
from core.navigator import build_navigator
from core.posts import save_posts
from core.tidy import tidy_texts
from core.utils import channel_folder


async def download_channel(client, entity, opts, rep):
    """Полный цикл для одного канала: порядок, тексты, медиа, навигатор.
    Возвращает {"texts": число постов или None, "media": статистика или None}.
    Остановка: rep.cancel() -> Cancelled."""
    title = getattr(entity, "title", str(entity.id))
    rep.log(f"Канал: {title}")
    result = {"texts": None, "media": None}
    root = channel_folder(opts.out_dir, entity)

    if not opts.dry_run:
        # тексты из старых мест переезжают в «Текст постов», копии в папках постов убираются
        await to_thread(tidy_texts, root, rep)
        rep.check()

    if opts.texts:
        rep.log("Сохраняю тексты постов...")
        result["texts"] = await save_posts(client, entity, opts, rep)
        rep.check()

    if opts.photos or opts.videos:
        rep.log("Скачиваю медиа...")
        result["media"] = await save_media(client, entity, opts, rep)
        rep.check()

    if not opts.dry_run:
        rep.log("Строю навигатор...")
        try:
            await to_thread(build_navigator, root, rep, opts.timezone)

            # после успешного создания навигатора удаляем служебный 0_meta.json
            from os import remove
            from os.path import exists, join

            from core.layout import META_NAME

            meta_path = join(root, META_NAME)
            if exists(meta_path):
                try:
                    remove(meta_path)
                except OSError:
                    pass

        except PermissionError:
            rep.log(
                "Не удалось записать 0_navigator.xlsx: закройте его в Excel и повторите."
            )

    rep.log("Готово.")
    return result
