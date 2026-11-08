from core.utils import is_skipped


def is_post(group):
    """Настоящий пост: есть текст, фото или видео. Служебные сообщения (закрепление, смена фото канала)
    и заглушки про авторские права постом не считаются."""
    if any(getattr(msg, "action", None) for msg in group):
        return False
    if any(is_skipped(msg) for msg in group):
        return False
    return any(msg.text or msg.photo or msg.video for msg in group)


async def _groups(client, entity, reverse):
    """Сообщения канала, сгруппированные в посты: альбом (общий grouped_id) идёт одной группой."""
    group, group_id = [], None
    async for msg in client.iter_messages(entity, reverse=reverse):
        if msg.grouped_id and msg.grouped_id == group_id:
            group.append(msg)
            continue
        if group:
            yield group
        group = [msg]
        group_id = msg.grouped_id
    if group:
        yield group


async def iter_posts(client, entity, limit=None):
    """Отдаёт посты как списки сообщений.
    Без limit отдаёт все группы подряд. С limit считает и отдаёт только настоящие посты, начиная с новых."""
    posts = 0
    async for group in _groups(client, entity, reverse=limit is None):
        if not limit:
            yield group
            continue
        if not is_post(group):
            continue
        yield group
        posts += 1
        if posts >= limit:
            return


async def scan_size(client, entity, limit):
    """(всего, единица) для прогресса: при limit считаем посты, иначе сообщения."""
    if limit:
        return limit, "постов"
    return (await client.get_messages(entity, limit=0)).total, "сообщений"


def step(group, limit):
    """На сколько продвинулся прогресс после этого поста."""
    return 1 if limit else len(group)