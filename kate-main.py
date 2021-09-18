# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import sqlite3 as sql
import asyncio
import random
import functools
import itertools
import math
import youtube_dl
from async_timeout import timeout
from Cybernator import Paginator
import os
import sys
import datetime

conn = sql.Connection("database.sql")
cur = conn.cursor()
bot = commands.Bot(command_prefix="+", intents=discord.Intents.all(), help_command=None, strip_after_prefix=True, max_messages=10000)
MainColor = discord.Color.green()

crimes_positive = [
    ["Вы пробрались в дом соседа и украли у него "],
    ["Пока ваш друг отвлекся на звонок, вы засунули руку в его карман и достали оттуда "],
    ["Проходя мимо кассы, вы схватили пару купюр на сумму "]
    ]

crimes_negative = [
    ["Вы пробрались в дом соседа в попытке украсть у него немного денег, но он увидел вас, и приехавшая на место полиция оштрафовала вас на "],
    ["Пока ваш друг отвлекся на звонок, вы попытались взять пару купюр из его кармана, но он это заметил и сам забрал у вас "],
    ["Проходя мимо кассы, вы схватили пару купюр, но камеры вас заметили, и у вас не только забрали то что вы награбили, но и дополнительно оштрафовали на "]
    ]

works = [
    ["Вы поработали на заводе и получили "],
    ["Вы починили компьютер другу, и тот в благодарность дал вам "],
    ["Вы приняли участие в бета-тесте одной популярной программы, и нашли критическую ошибку. За это компания-разработчик зачислила вам на баланс "],
    ["После месяца упорной работы, вы получаете зарплату размером в "],
    ["Вы выиграли в азартной игре, и получили "],
    ["За активное участие в жизни школы, вам подарили сертификат на сумму "],
    ]

def adduser(userid, guildid):
    cur.execute(f"INSERT INTO users VALUES (0, {userid}, {guildid}, 1, 0)")
    conn.commit()
    print(f"В базу данных добавлен пользователь {userid} (сервер {guildid})")

youtube_dl.utils.bug_reports_message = lambda: ''


class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    def __str__(self):
        return '**{0.title}** от **{0.uploader}**'.format(self)

    @classmethod
    async def create_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YTDLError('Мы не смогли найти ничего похожего на `{}`'.format(search))

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YTDLError('Мы не смогли найти ничего похожего на `{}`'.format(search))

        webpage_url = process_info['webpage_url']
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YTDLError('Невозможно получить `{}`'.format(webpage_url))

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YTDLError('Неудалось получить совпадения для `{}`'.format(webpage_url))

        return cls(ctx, discord.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append('{} days'.format(days))
        if hours > 0:
            duration.append('{} hours'.format(hours))
        if minutes > 0:
            duration.append('{} minutes'.format(minutes))
        if seconds > 0:
            duration.append('{} seconds'.format(seconds))

        return ', '.join(duration)


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(title='Сейчас играет',
                               description='```css\n{0.source.title}\n```'.format(self),
                               color=discord.Color.blurple())
                 .add_field(name='Длительность', value=self.source.duration)
                 .add_field(name='Запросил', value=self.requester.mention)
                 .add_field(name='Загрузчик', value='[{0.source.uploader}]({0.source.uploader_url})'.format(self))
                 .add_field(name='URL', value='[Клик]({0.source.url})'.format(self))
                 .set_thumbnail(url=self.source.thumbnail))

        return embed


class SongQueue(asyncio.Queue):
    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current = None
        self.voice = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def audio_player_task(self):
        while True:
            self.next.clear()

            if not self.loop:
                # Try to get the next song within 3 minutes.
                # If no song will be added to the queue in time,
                # the player will disconnect due to performance
                # reasons.
                try:
                    async with timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    self.bot.loop.create_task(self.stop())
                    return

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            await self.current.source.channel.send(embed=self.current.create_embed())

            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('Эту команду нельзя использовать в личных сообщениях.')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('Произошла ошибка: {}'.format(str(error)))

    @commands.command(name='join', invoke_without_subcommand=True, aliases=["connect"])
    async def _join(self, ctx: commands.Context):
        """Подключается к голосовому каналу."""

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='summon')
    @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Призывает бота в указанный канал.

        Если канал не указан, бот подключается в канал вызвавшего команду.
        """

        if not channel and not ctx.author.voice:
            raise VoiceError('Вы не подключены к голосовому каналу и не указали канал к которому подключаться.')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        """Очищает очередь и выходит из голосового канала."""

        if not ctx.voice_state.voice:
            return await ctx.send('Бот не подключен ни к одному каналу.')

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    async def _volume(self, ctx: commands.Context, *, volume: int):
        """Устанавливает громкость проигрывателя."""

        if not ctx.voice_state.is_playing:
            return await ctx.send('В этот момент ничего не проигрывается.')

        if 0 > volume > 100:
            return await ctx.send('Громкость должна быть между 0 и 100')

        ctx.voice_state.volume = volume / 100
        await ctx.send('Звук проигрывателя установлен на {}%'.format(volume))

    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        """Показывает текущую песню."""

        await ctx.send(embed=ctx.voice_state.current.create_embed())

    @commands.command(name='pause')
    async def _pause(self, ctx: commands.Context):
        """Ставит песню на паузу."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='resume')
    async def _resume(self, ctx: commands.Context):
        """Возобновляет проигрывание песни."""

        if not ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('⏯')

    @commands.command(name='stop')
    async def _stop(self, ctx: commands.Context):
        """Останавливает песню и очищает очередь."""

        ctx.voice_state.songs.clear()

        if not ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('⏹')

    @commands.command(name='skip')
    async def _skip(self, ctx: commands.Context):
        """Голосование за пропуск песни. Тот кто заказал эту песню может пропустить ее без голосования.
        Для пропуска необходимо 3 голоса.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('Музыка сейчас не играет')

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send('Голос за пропуск добавлен, сейчас голосов: **{}/3**'.format(total_votes))

        else:
            await ctx.send('Вы уже голосовали за пропуск этой песни.')

    @commands.command(name='queue')
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        """Показывает очередь проигрывателя.

        Вы можете уточнить, какую страницу показать. На каждой странице 10 элементов.
        """

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Очередь пустая.')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(i + 1, song)

        embed = (discord.Embed(description='**{} песен:**\n\n{}'.format(len(ctx.voice_state.songs), queue))
                 .set_footer(text='Страница {}/{}'.format(page, pages)))
        await ctx.send(embed=embed)

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """\"Встряхивает\" очередь (перемешивает песни в очереди)."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Пустая очередь.')

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('✅')

    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):
        """Удаляет песню под указанным номером из очереди."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Пустая очередь.')

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction('✅')

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        """Зацикливает текущую песню.

        Вызовите эту команду еще раз чтобы разорвать цикл.
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('Сейчас ничего не играет.')

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.message.add_reaction('✅')

    @commands.command(name='play')
    async def _play(self, ctx: commands.Context, *, search: str):
        """Проигрывает указанную песню.

        Если в очереди есть песни, указанная песня добавляется в конец очереди.

        Поиск ведется по нескольким сайтам, если URL не указано.
        Список этих сайтов можно найти здесь: https://rg3.github.io/youtube-dl/supportedsites.html
        """

        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except YTDLError as e:
                await ctx.send('Во время обработки запроса произошла ошибка: {}'.format(str(e).replace("search is a required argument that is missing", "вы не указали запрос для поиска")))
            else:
                song = Song(source)

                await ctx.voice_state.songs.put(song)
                await ctx.send('Добавлено в очередь: {}'.format(str(source)))

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('Вы не подключены ни к одному голосовому каналу.')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('Бот уже находится в голосовом канале.')

@bot.event
async def on_ready():
    
    cur.execute("CREATE TABLE IF NOT EXISTS users (cash INT, id INT, guildid INT, lvl INT, xp INT)")
    conn.commit()
    
    cur.execute("CREATE TABLE IF NOT EXISTS giveaways (guildid INT, messageid INT, rewardtype TEXT, reward INT, members INT, authorid INT)")
    conn.commit()
    
    cur.execute("CREATE TABLE IF NOT EXISTS warns (guildid INT, userid INT, authorid INT, number INT, reason TEXT)")
    conn.commit()
    
    cur.execute("CREATE TABLE IF NOT EXISTS coupons (guildid INT, name TEXT, reward INT, maxuses INT, uses INT, author INT)")
    conn.commit()
    
    cur.execute("CREATE TABLE IF NOT EXISTS guilds (guildid INT, currency INT, crimechance INT, muterole INT)")
    conn.commit()
    
    cur.execute("CREATE TABLE IF NOT EXISTS mutes (guildid INT, userid INT, reason TEXT)")
    conn.commit()
    
    cur.execute("CREATE TABLE IF NOT EXISTS shop (guildid INT, cost INT, item INT, description TEXT)")
    conn.commit()
    
    for guild in bot.guilds:
        for member in guild.members:
            if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {guild.id}").fetchone() == None:
                adduser(userid=member.id, guildid=guild.id)
                print(f"В базу данных добавлен пользователь {member.id} (сервер {guild.id})")
            else:
                pass
    print("Ready")

@bot.event
async def on_message(message):
    
    if message.guild is not None:
        AlreadyGiven = False
        if cur.execute(f"SELECT cash FROM users WHERE id = {message.author.id} AND guildid = {message.guild.id}").fetchone() == None:
            adduser(userid=message.author.id, guildid=message.guild.id)
        else:
            pass
        if len(message.content) > 40 and not AlreadyGiven:
            cur.execute(f"UPDATE users SET cash = cash + 8 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            cur.execute(f"UPDATE users SET xp = xp + 4 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            AlreadyGiven = True
        elif len(message.content) > 25 and not AlreadyGiven:
            cur.execute(f"UPDATE users SET cash = cash + 5 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            cur.execute(f"UPDATE users SET xp = xp + 3 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            AlreadyGiven = True
        
        elif len(message.content) > 14 and not AlreadyGiven:
            cur.execute(f"UPDATE users SET cash = cash + 3 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            cur.execute(f"UPDATE users SET xp = xp + 2 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            AlreadyGiven = True
        
        elif len(message.content) > 6 and not AlreadyGiven:
            cur.execute(f"UPDATE users SET cash = cash + 1 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            cur.execute(f"UPDATE users SET xp = xp + 1 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            AlreadyGiven = True
        
        currentxp = cur.execute(f"SELECT xp FROM users WHERE id = {message.author.id} AND guildid = {message.guild.id}").fetchone()[0]
        
        currentlvl = cur.execute(f"SELECT lvl FROM users WHERE id = {message.author.id} AND guildid = {message.guild.id}").fetchone()[0]
        
        xpneeded = 20*currentlvl
        
        if cur.execute(f"SELECT xp FROM users WHERE id = {message.author.id} AND guildid = {message.guild.id}").fetchone()[0] >= xpneeded:
            cur.execute(f"UPDATE users SET lvl = lvl + 1 WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            newxp = currentxp - xpneeded
            cur.execute(f"UPDATE users SET xp = {newxp} WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            conn.commit()
            cur.execute(f"UPDATE users SET cash = cash + {5 * currentlvl} WHERE id = {message.author.id} AND guildid = {message.guild.id}")
            await message.channel.send(embed=discord.Embed(description=f"{message.author.mention} повысил свой уровень до **{currentlvl + 1}**!\nПроверить свой уровень - `+rank`", color=MainColor))
            
        else:
            pass
    else:
        pass
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send(embed=discord.Embed(description=f"Неверный аргумент для команды `{ctx.command.name}`", color=MainColor))
        print(dir(error))
    else:
        raise error

@bot.event
async def on_message_delete(message):
    channel = bot.get_channel(835194587421212685)
    if channel:
    	await channel.send(embed=discord.Embed(description=f"В канале {message.channel.mention} было удалено сообщение.\nТекст сообщения:\n{message.content}\nАвтор сообщения: **{message.author.name}** ({message.author.mention})", color=MainColor))

@bot.event
async def on_message_edit(before, after):
    channel = bot.get_channel(835194587421212685)
    if channel:
    	await channel.send(embed=discord.Embed(description=f"В канале {before.channel.mention} было изменено сообщение.\nТекст сообщения до:\n{before.content}\nТекст сообщения после:\n{after.content}\nАвтор сообщения: **{before.author.name}** ({before.author.mention})", color=MainColor))

@bot.event
async def on_member_ban(guild, user):
    bannedby = None
    async for entry in guild.audit_logs(limit=3):
        if entry.action == discord.AuditLogAction.ban:
            if entry.target.id == user.id:
                bannedby = entry.user
                break
            else:
                bannedby = "Неизвестно"
        else:
            bannedby = "Неизвестно"
    if isinstance(bannedby, str):
        channel = bot.get_channel(835194587421212685)
        if channel:
        	await channel.send(embed=discord.Embed(description=f"Участник **{user.name}** был забанен.\nАдминистратор: **{bannedby}**", color=MainColor))
    else:
        channel = bot.get_channel(835194587421212685)
        if channel:
        	await channel.send(embed=discord.Embed(description=f"Участник **{user.name}** был забанен.\nАдминистратор: **{bannedby.name}** ({bannedby.mention})", color=MainColor))

@bot.event
async def on_member_unban(guild, user):
    unbannedby = ""
    async for entry in guild.audit_logs(limit=3):
        if entry.action == discord.AuditLogAction.unban:
            if entry.target.id == user.id:
                unbannedby = entry.user
                break
            else:
                unbannedby = "Неизвестно"
        else:
            unbannedby = "Неизвестно"
    if isinstance(unbannedby, str):
        channel = bot.get_channel(835194587421212685)
        if channel:
        	await channel.send(embed=discord.Embed(description=f"Пользователь {user.name} был разбанен.\nАдминистратор: **{unbannedby}**", color=MainColor))
    else:
        channel = bot.get_channel(835194587421212685)
        if channel:
        	await channel.send(embed=discord.Embed(description=f"Пользователь {user.name} был разбанен.\nАдминистратор: **{unbannedby.name}** ({unbannedby.mention})", color=MainColor))

@bot.event
async def on_member_leave(member):
    async for entry in member.guild.audit_logs(limit=3):
        if entry.action == discord.AuditLogAction.kick:
            if entry.target.id == member.id:
                channel = bot.get_channel(835194587421212685)
                if channel:
                	await channel.send(embed=discord.Embed(description=f"Пользователь {member.name} был кикнут\nАдминистратор: **{entry.user.name}** ({entry.user.mention}).", color=MainColor))
                break
            else:
                pass
        else:
            pass

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) == '✅':
        messageid = None
        try:
            messageid = cur.execute(f"SELECT messageid FROM giveaways WHERE guildid = {payload.guild_id} AND messageid = {payload.message_id}").fetchone()[0]
        except TypeError:
            pass
        else:
            guild = bot.get_guild(payload.guild_id)
            channel = None
            for channelitem in guild.text_channels:
                if channelitem.id == payload.channel_id:
                    channel = channelitem
                else:
                    pass
            message = await channel.fetch_message(payload.message_id)
            members = cur.execute(f"SELECT members FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0]
            rewardtype = cur.execute(f"SELECT rewardtype FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0]
            author = get_member(cur.execute(f"SELECT authorid FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0])
            
            if rewardtype == 'role':
                reward = guild.get_role(cur.execute(f"SELECT reward FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0])
                await message.edit(embed=discord.Embed(description=f"{author.mention} начал розыгрыш!\nПриз: {reward.mention}\nУчастников: {members + 1}"))
            else:
                reward = cur.execute(f"SELECT reward FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0]
                await message.edit(embed=discord.Embed(description=f"{author.mention} начал розыгрыш!\nПриз: {reward} монет\nУчастников: {members + 1}"))
            cur.execute(f"UPDATE giveaways SET members = {members + 1} WHERE messageid = {message.id} AND guildid = {guild.id}")
            conn.commit()

@bot.event
async def on_raw_reaction_remove(payload):
    if str(payload.emoji) == '✅':
        messageid = None
        try:
            messageid = cur.execute(f"SELECT messageid FROM giveaways WHERE guildid = {payload.guild_id} AND messageid = {payload.message_id}").fetchone()[0]
        except TypeError:
            pass
        else:
            guild = bot.get_guild(payload.guild_id)
            channel = None
            for channelitem in guild.text_channels:
                if channelitem.id == payload.channel_id:
                    channel = channelitem
                else:
                    pass
            message = await channel.fetch_message(payload.message_id)
            members = cur.execute(f"SELECT members FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0]
            rewardtype = cur.execute(f"SELECT rewardtype FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0]
            author = get_member(cur.execute(f"SELECT authorid FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0])
            
            if rewardtype == 'role':
                reward = guild.get_role(cur.execute(f"SELECT reward FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0])
                await message.edit(embed=discord.Embed(description=f"{author.mention} начал розыгрыш!\nПриз: {reward.mention}\nУчастников: {members - 1}"))
            else:
                reward = cur.execute(f"SELECT reward FROM giveaways WHERE messageid = {message.id} AND guildid = {guild.id}").fetchone()[0]
                await message.edit(embed=discord.Embed(description=f"{author.mention} начал розыгрыш!\nПриз: {reward} монет\nУчастников: {members - 1}"))
            cur.execute(f"UPDATE giveaways SET members = {members - 1} WHERE messageid = {message.id} AND guildid = {guild.id}")
            conn.commit()

@bot.command(aliases=["bal", "cash", "money"])
async def balance(ctx, member: discord.Member = None):
    
    if ctx.guild is not None:
        
        currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if currency != None:
            currency = bot.get_emoji(currency[0])
        else:
            currency = '💵'
        if member == None:
            
            if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                
                adduser(userid=ctx.author.id, guildid=ctx.guild.id)
                await ctx.send(embed=discord.Embed(description=f"Ваш баланс составляет **{0}** {str(currency)}.", color=MainColor))
            else:
                balance = cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone()[0]
                await ctx.send(embed=discord.Embed(description=f"Ваш баланс составляет **{balance}** {str(currency)}", color=MainColor))
        else:
            
            if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                
                adduser(userid=member.id, guildid=ctx.guild.id)
                await ctx.send(embed=discord.Embed(description=f"Баланс участника {member.mention} составляет **{0}** {str(currency)}.", color=MainColor))
            
            else:
                balance = cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone()[0]
                await ctx.send(embed=discord.Embed(description=f"Баланс участника {member.mention} составляет **{balance}** {str(currency)}.", color=MainColor))
    
    else:
        pass

@bot.command()
async def pay(ctx, amount: int = None, member: discord.Member = None):
    
    if ctx.guild is not None:
        
        if amount is not None and amount > 0:
            
            if member is not None:
                
                currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
                if currency != None:
                    currency = bot.get_emoji(currency[0])
                else:
                    currency = '💵'
                if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                    adduser(userid=ctx.author.id, guildid=ctx.guild.id)
                else:
                    pass
                
                if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                    adduser(userid=member.id, guildid=ctx.guild.id)
                else:
                    pass
                
                if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone()[0] < amount:
                    await ctx.send(embed=discord.Embed(description="У вас недостаточно денег на балансе", color=MainColor))
                else:
                    cur.execute(f"UPDATE users SET cash = cash - {amount} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
                    conn.commit()
                    cur.execute(f"UPDATE users SET cash = cash + {amount} WHERE id = {member.id} AND guildid = {ctx.guild.id}")
                    conn.commit()
                    await ctx.send(embed=discord.Embed(description=f"С баланса {ctx.author.mention} на баланс {member.mention} было переведено **{amount}** {str(currency)}"))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали пользователя которому необходимо передать деньги", color=MainColor))
        elif amount is not None and amount < 1:
            await ctx.send(embed=discord.Embed(description="Минимальная сумма для перевода - 1", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали сумму перевода", color=MainColor))
    else:
        pass

@bot.command()
@commands.has_permissions(administrator=True)
async def give(ctx, amount: int = None, member: discord.Member = None):
    if ctx.guild is not None:
        
        if amount is not None and amount > 0:
            
            if member is not None:
                
                currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
                if currency != None:
                    currency = bot.get_emoji(currency[0])
                else:
                    currency = '💵'
                if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                    adduser(userid=member.id, guildid=ctx.guild.id)
                else:
                    pass
                
                cur.execute(f"UPDATE users SET cash = cash + {amount} WHERE id = {member.id} AND guildid = {ctx.guild.id}")
                conn.commit()
                await ctx.send(embed=discord.Embed(description=f"На баланс {member.mention} было зачислено **{amount}** {str(currency)}", color=MainColor))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали пользователя которому необходимо передать деньги", color=MainColor))
        elif amount is not None and amount < 1:
            await ctx.send(embed=discord.Embed(description="Минимальная сумма для перевода - 1", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали сумму перевода", color=MainColor))
    else:
        pass

@bot.command(aliases=["take", "remove-money"], pass_content=True)
@commands.has_permissions(administrator=True)
async def remove_money(ctx, amount: int = None, member: discord.Member = None):
    if ctx.guild is not None:
        
        if amount is not None and amount > 0:
            
            if member is not None:
                currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
                if currency != None:
                    currency = bot.get_emoji(currency[0])
                else:
                    currency = '💵'
                if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                    adduser(userid=member.id, guildid=ctx.guild.id)
                else:
                    pass
                if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone()[0] >= amount:
                    cur.execute(f"UPDATE users SET cash = cash - {amount} WHERE id = {member.id} AND guildid = {ctx.guild.id}")
                    conn.commit()
                    await ctx.send(embed=discord.Embed(description=f"С баланса {member.mention} было вычтено **{amount}** {str(currency)}", color=MainColor))
                else:
                    cur.execute(f"UPDATE users SET cash = 0 WHERE id = {member.id} AND guildid = {ctx.guild.id}")
                    conn.commit()
                    await ctx.send(embed=discord.Embed(description=f"С баланса {member.mention} было вычтено максимально возможное количество {str(currency)}", color=MainColor))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали пользователя у которого нужно забрать деньги", color=MainColor))
        elif amount is not None and amount < 1:
            await ctx.send(embed=discord.Embed(description="Минимальная сумма для удаления - 1", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали сумму для удаления", color=MainColor))
    else:
        pass

@bot.command()
@commands.cooldown(rate=1, per=3600.0, type=commands.BucketType.member)
async def hourly(ctx):
    if ctx.guild is not None:
        amount = random.randint(200, 1000)
        if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
            adduser(userid=ctx.author.id, guildid=ctx.guild.id)
        else:
            pass
        cur.execute(f"UPDATE users SET cash = cash + {amount} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
        conn.commit()
        currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if currency != None:
            currency = bot.get_emoji(currency[0])
        else:
            currency = '💵'
        await ctx.send(embed=discord.Embed(description=f"Вы получили **{amount}** {str(currency)}.", color=MainColor))
    else:
        pass

@bot.command()
@commands.cooldown(rate=1, per=86400.0, type=commands.BucketType.member)
async def daily(ctx):
    if ctx.guild is not None:
        amount = random.randint(600, 1800)
        if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
            adduser(userid=ctx.author.id, guildid=ctx.guild.id)
        else:
            pass
        cur.execute(f"UPDATE users SET cash = cash + {amount} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
        conn.commit()
        currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if currency != None:
            currency = bot.get_emoji(currency[0])
        else:
            currency = '💵'
        await ctx.send(embed=discord.Embed(description=f"Вы получили **{amount}** {str(currency)}.", color=MainColor))
    else:
        pass

@bot.command()
@commands.cooldown(rate=1, per=604800.0, type=commands.BucketType.member)
async def weekly(ctx):
    if ctx.guild is not None:
        amount = random.randint(1000, 3500)
        if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
            adduser(userid=ctx.author.id, guildid=ctx.guild.id)
        else:
            pass
        cur.execute(f"UPDATE users SET cash = cash + {amount} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
        conn.commit()
        currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if currency != None:
            currency = bot.get_emoji(currency[0])
        else:
            currency = '💵'
        await ctx.send(embed=discord.Embed(description=f"Вы получили **{amount}** {str(currency)}.", color=MainColor))
    else:
        pass

@bot.command(aliases=["coin"])
async def coinflip(ctx, amount: int = None):
    if ctx.guild is not None:
        
        if amount is not None and amount > 0:
            
            if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                adduser(userid=ctx.author.id, guildid=ctx.guild.id)
            else:
                pass
            
            if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone()[0] >= amount:
                currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
                if currency != None:
                    currency = bot.get_emoji(currency[0])
                else:
                    currency = '💵'
                def check(message):
                    m = message
                    return str(m.content) in ["1", "2", "3"] and m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
                msg1 = await ctx.send(content=f"{ctx.author.mention}", embed=discord.Embed(description="**Coinflip**\nСтавка на...\n1 - Орел\n2 - Ребро\n3 - Решка", color=MainColor))
                try:
                    msg2 = await bot.wait_for('message', timeout=20.0, check=check)
                except asyncio.TimeoutError:
                    msg1.edit(content=f"{ctx.author.mention}", embed=discord.Embed(description="Время истекло", color=MainColor))
                else:
                    CP = str(random.randint(1, 3))
                    CPF = ""
                    UCPF = ""
                    if CP == "1":
                        CPF = "Орел"
                    elif CP == "2":
                        CPF = "Ребро"
                    else:
                        CPF = "Решка"
                    if str(msg2.content) == "1":
                        UCPF = "Орел"
                    elif str(msg2.content) == "2":
                        UCPF = "Ребро"
                    else:
                        UCPF = "Решка"
                    if CP == str(msg2.content):
                        cur.execute(f"UPDATE users SET cash = cash + {amount} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
                        conn.commit()
                        await msg1.edit(content=f"{ctx.author.mention}", embed=discord.Embed(description=f"Вы выиграли {amount} {str(currency)}!\nВыпало: **{CPF}**\nВы выбрали: **{CPF}**"))
                    else:
                        cur.execute(f"UPDATE users SET cash = cash - {amount} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
                        conn.commit()
                        await msg1.edit(content=f"{ctx.author.mention}", embed=discord.Embed(description=f"Вы проиграли на {amount} {str(currency)}!\nВыпало: **{CPF}**\nВы выбрали: **{UCPF}**"))
            else:
                await ctx.send(embed=discord.Embed(description="У вас недостаточно средств на балансе", color=MainColor))

@bot.command()
async def rank(ctx, member: discord.Member = None):
    
    if ctx.guild is not None:
        
        if member == None:
            
            if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                adduser(userid=ctx.author.id, guildid=ctx.guild.id)
            else:
                pass
            level = cur.execute(f"SELECT lvl FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone()[0]
            xp = cur.execute(f"SELECT xp FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone()[0]
            xpneeded = 20 * level
            cash = cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone()[0]
            currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
            if currency != None:
                currency = bot.get_emoji(currency[0])
            else:
                currency = '💵'
            await ctx.send(embed=discord.Embed(description=f"Профиль {ctx.author.mention}:\nУровень — **{level}**\nОпыт — **{xp}**/**{xpneeded}**\nДеньги — **{cash}** {str(currency)}", color=MainColor))
        else:
            
            if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                adduser(userid=member.id, guildid=ctx.guild.id)
            else:
                pass
            level = cur.execute(f"SELECT lvl FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone()[0]
            xp = cur.execute(f"SELECT xp FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone()[0]
            xpneeded = 20 * level
            cash = cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone()[0]
            currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
            if currency != None:
                currency = bot.get_emoji(currency[0])
            else:
                currency = '💵'
            await ctx.send(embed=discord.Embed(description=f"Профиль {member.mention}:\nУровень — **{level}**\nОпыт — **{xp}**/**{xpneeded}**\nДеньги — **{cash}** {str(currency)}", color=MainColor))
    else:
        pass

@bot.command(aliases=["setlevel", "setlvl"])
@commands.has_permissions(administrator=True)
async def level(ctx, lvl: int = None, member: discord.Member = None):
    if ctx.guild is not None:
        
        if lvl is not None and lvl > 0:
            
            if member is not None:
                if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                    adduser(userid=member.id, guildid=ctx.guild.id)
                else:
                    pass
                cur.execute(f"UPDATE users SET lvl = {lvl}, xp = 0 WHERE id = {member.id} AND guildid = {ctx.guild.id}")
                conn.commit()
                await ctx.send(embed=discord.Embed(description=f"Участнику {member.mention} установлен уровень {lvl}", color=MainColor))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали участника", color=MainColor))
        elif lvl == 0:
            await ctx.send(embed=discord.Embed(description="Уровень должен быть больше нуля", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали уровень", color=MainColor))
    else:
        pass

@bot.command()
async def top(ctx, topby: str = 'level'):
    if ctx.guild is not None:
        currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if currency != None:
            currency = bot.get_emoji(currency[0])
        else:
            currency = '💵'
        if topby in ['level', 'lvl']:
            emb = discord.Embed(title="Топ 10 по уровням", color=MainColor)
            loop = 0
            for id in cur.execute(f"SELECT id FROM users WHERE guildid = {ctx.guild.id} ORDER BY lvl DESC LIMIT 10").fetchall():
                loop += 1
                member = ctx.guild.get_member(int(id[0]))
                level = cur.execute(f"SELECT lvl FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone()[0]
                emb.add_field(name=f"Топ {loop}", value=f"{member.mention} | {level}", inline=False)
            await ctx.send(embed=emb)
        elif topby in ['money', 'cash']:
            emb = discord.Embed(title="Топ 10 по деньгам", color=MainColor)
            loop = 0
            for id in cur.execute(f"SELECT id FROM users WHERE guildid = {ctx.guild.id} ORDER BY cash DESC LIMIT 10").fetchall():
                loop += 1
                member = ctx.guild.get_member(int(id))
                money = cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone()[0]
                emb.add_field(name=f"Топ {loop}", value=f"{member.mention} | {money} {str(currency)}", inline=False)
            await ctx.send(embed=emb)
        else:
            await ctx.send(embed=discord.Embed(description=f"Неизвестный тип сортировки: {topby}", color=MainColor))
    else:
        pass

@bot.command(aliases=["server", "guildinfo"])
async def serverinfo(ctx):
    guild = bot.get_guild(834124741102141441)
    members_emo = await guild.fetch_emoji(887403122962595990)
    people_emo = await guild.fetch_emoji(887403122954227732)
    bots_emo = await guild.fetch_emoji(887403123059097620)
    offline_emo = await guild.fetch_emoji(887402767495360564)
    dnd_emo = await guild.fetch_emoji(887402767579246643)
    idle_emo = await guild.fetch_emoji(887403123038117908)
    online_emo = await guild.fetch_emoji(887403122966790224)
    channels_emo = await guild.fetch_emoji(887403122966822972)
    text_emo = await guild.fetch_emoji(887403122954215505)
    voice_emo = await guild.fetch_emoji(887403123109421087)
    stage_emo = await guild.fetch_emoji(887403122715152445)
    members_emo = str(members_emo)
    people_emo = str(people_emo)
    members_emo = str(people_emo)
    bots_emo = str(bots_emo)
    offline_emo = str(offline_emo)
    dnd_emo = str(dnd_emo)
    idle_emo = str(idle_emo)
    online_emo = str(online_emo)
    channels_emo = str(channels_emo)
    text_emo = str(text_emo)
    voice_emo = str(voice_emo)
    stage_emo = str(stage_emo)
    people = 0
    bots = 0
    online = 0
    offline = 0
    dnd = 0
    idle = 0
    unknown = 0
    channels = len(ctx.guild.channels)
    text = len(ctx.guild.text_channels)
    voice = len(ctx.guild.voice_channels)
    stage = len(ctx.guild.stage_channels)
    created_at = ctx.guild.created_at
    created_at_month = ""
    if ctx.guild.created_at.month == 1:
        created_at_month = "Января"
    elif ctx.guild.created_at.month == 2:
        created_at_month = "Февраля"
    elif ctx.guild.created_at.month == 3:
        created_at_month = "Марта"
    elif ctx.guild.created_at.month == 4:
        created_at_month = "Апреля"
    elif ctx.guild.created_at.month == 5:
        created_at_month = "Мая"
    elif ctx.guild.created_at.month == 6:
        created_at_month = "Июня"
    elif ctx.guild.created_at.month == 7:
        created_at_month = "Июля"
    elif ctx.guild.created_at.month == 8:
        created_at_month = "Августа"
    elif ctx.guild.created_at.month == 9:
        created_at_month = "Сентября"
    elif ctx.guild.created_at.month == 10:
        created_at_month = "Октября"
    elif ctx.guild.created_at.month == 11:
        created_at_month = "Ноября"
    elif ctx.guild.created_at.month == 12:
        created_at_month = "Декабря"
    created_at_str = f"{created_at.day} {created_at_month} {created_at.year}, {created_at.hour}:{created_at.minute}"
    for member in ctx.guild.members:
        if member.bot != True:
            people += 1
        else:
            bots += 1
        if member.status == discord.Status.online:
            online += 1
        elif member.status == discord.Status.offline:
            offline += 1
        elif member.status == discord.Status.dnd:
            dnd += 1
        elif member.status == discord.Status.idle:
            idle += 1
        else:
            unknown += 1
    embed = discord.Embed(description=f"Информация о сервере **{ctx.guild.name}**\n{members_emo} Всего:  **{ctx.guild.member_count}**\n{people_emo} Людей:  **{people}**\n{bots_emo} Ботов:  **{bots}**\n \n**По статусам:**\n{online_emo} В сети:  **{online}**\n{idle_emo} Не активен:  **{idle}**\n{dnd_emo} Не беспокоить:  **{dnd}**\n{offline_emo} Не в сети:  **{offline}**\n**Каналы:**\n{channels_emo} Всего:  **{channels}**\n{text_emo} Текстовых:  **{text}**\n{voice_emo} Голосовых:  **{voice}**\n{stage_emo} Трибунных: **{stage}**\n**Владелец:**\n{ctx.guild.owner.name + '#' + ctx.guild.owner.discriminator}\nСоздана ||{created_at_str}||", color=MainColor).set_thumbnail(url=ctx.guild.icon_url)
    await ctx.send(embed=embed)

@bot.command()
async def help(ctx):
    emb = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.", color=MainColor)
    emb.add_field(name="balance", value="Алиасы: `cash`, `money`, `bal`\nИспользование: `balance [@member]`\nПоказывает баланс участника `member` или вызвавшего команду, если `member` не указан.", inline=False)
    emb.add_field(name="pay", value="Без алиасов.\nИспользование: `pay <amount> <@member>`\nПереводит `amount` денег со счета вызвавшего команду на счет `member`-а.", inline=False)
    emb.add_field(name="hourly", value="Без алиасов.\nИспользование: `hourly`\nЕжечасная награда.", inline=False)
    emb.add_field(name="daily", value="Без алиасов.\nИспользование: `daily`\nЕжедневная награда.", inline=False)
    emb.add_field(name="weekly", value="Без алиасов.\nИспользование: `weekly`\nЕженедельная награда.", inline=False)
    emb.add_field(name="coinflip", value="Алиасы: `coin`\nИспользование: `coinflip <amount>`\nАзартная игра: бот \"Подбрасывает монетку\", и если игрок угадал сторону, на которую она упала, то ставка умножается на два и начисляется игроку, если игрок не угадал, ставка списывается с его счета.", inline=False)
    
    
    emb1 = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.", color=MainColor)
    emb1.add_field(name="giveaway", value="Алиасы: `drop`\nИспользование: `giveaway <timeout> <reward>`\nНачинает раздачу с таймаутом `timeout` и призом `reward`", inline=False)
    emb1.add_field(name="create-coupon", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `create-coupon <name> <amount> <maxuses>`\nСоздает купон с именем `name` и максимальным кол-вом использований `maxuses`, за использование которого дается <amount> денег.")
    emb1.add_field(name="delete-coupon", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `delete-coupon <name>`\nУдаляет купон с именем `name`, если он существует.", inline=False)
    emb1.add_field(name="coupon", value="Алиасы: `use-coupon`\nИспользование: `coupon <name>`\nИспользует купон с именем `name`, если он существует. Во избежания фарма, эту команду можно использовать только раз в 30 минут.", inline=False)
    emb1.add_field(name="crime", value="Без алиасов.\nИспользование: `crime`\nС определенным шансом вы либо теряете, либо получаете деньги. Шанс могут установить администраторы с помощью команды `set-crime-chance`")
    
    
    emb2 = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.", color=MainColor)
    emb2.add_field(name="rank", value="Без алиасов.\nИспользование: `rank [@member]`\nПоказывает уровень и опыт участника `member`, или вызвавшего команду если `member` не указан.", inline=False)
    emb2.add_field(name="top", value="Без алиасов.\nИспользование: `top [level | money]`\nПоказывает топ 10 сервера по уровням (если `level`), или деньгам (если `money`).", inline=False)
    emb2.add_field(name="give", value="`ADMIN-ONLY!`\nБез алиасов.\nИспользование: `give <amount> <@member>`\nВыдает `amount` денег на счет `member`-а.", inline=False)
    emb2.add_field(name="remove-money", value="`ADMIN-ONLY!`\nАлиасы: `take`.\nИспользование: `remove <amount> <@member>`\nЗабирает `amount` денег с счета `member`-а.", inline=False)
    emb2.add_field(name="level", value="`ADMIN-ONLY!`\nАлиасы: `setlevel`, `setlvl`\nИспользование: `level <level> <@member>`\nУстанавливает `member`-у уровень `level`.", inline=False)
    emb2.add_field(name="work", value="Без алиасов.\nИспользование: `work`\nВы \"работаете\", и получаете случайное количество денег.")
    
    
    emb3 = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.\n", color=MainColor)
    emb3.add_field(name="play", value="Без алиасов.\nИспользование: `play <query>`\nИщет песню по запросу `query` и проигрывает в текущем канале.", inline=False)
    emb3.add_field(name="join", value="Алиасы: `connect`\nИспользование: `join`\nПодключается к голосовому каналу вызвавшего команду.", inline=False)
    emb3.add_field(name="pause", value="Без алиасов.\nИспользование: `pause`\nСтавит текущий трек на паузу.", inline=False)
    emb3.add_field(name="resume", value="Без алиасов.\nИспользование: `resume`\nВозобновляет проигрывание текущего трека.", inline=False)
    emb3.add_field(name="stop", value="Без алиасов.\nИспользование: `stop`\nОстанавливает проигрывание и очищает очередь.", inline=False)
    emb3.add_field(name="volume", value="Без алиасов.\nИспользование: `volume <coef>`\nУстанавливает громкость проигрывателя на `coef`.", inline=False)
    
    
    emb4 = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.\n", color=MainColor)
    emb4.add_field(name="now", value="Алиасы: `playing`, `current`\nИспользование: `now`\nПоказывает информацию о текущем треке.", inline=False)
    emb4.add_field(name="skip", value="Без алиасов.\nИспользование: `skip`\nГолосование за пропуск песни. Тот кто заказал эту песню может пропустить ее без голосования. Для пропуска необходимо 3 голоса.", inline=False)
    emb4.add_field(name="queue", value="Без алиасов.\nИспользование: `queue [page]`\nПоказывает страницы со всеми песнями в очереди. На каждой странице 10 элементов.", inline=False)
    emb4.add_field(name="shuffle", value="Без алиасов.\nИспользование: `shuffle`\nПеремешивает песни в очереди.", inline=False)
    emb4.add_field(name="remove", value="Без алиасов.\nИспользование: `remove <index>`\nУдаляет песню под номером `index` из очереди.", inline=False)
    emb4.add_field(name="loop", value="Без алиасов.\nИспользование: `loop`\nЗацикливает воспроизведение очереди.", inline=False)
    
    
    emb5 = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.\n", color=MainColor)
    emb5.add_field(name="summon", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `summon [channel]`\nПризывает бота в указанный канал, либо в канал вызвавшего команду если `channel` не указан.", inline=False)
    emb5.add_field(name="leave", value="`ADMIN-ONLY`\nАлиасы: `disconnect`\nИспользование: `leave`\nПокидает текущий голосовой канал.", inline=False)
    emb5.add_field(name="set-crime-chance", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `set-crime-chance <coef>`\nУстанавливает шанс на выигрыш в `crime` на `coef`", inline=False)
    emb5.add_field(name="set-currency-symbol", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `set-currency-symbol <emoji>`\nУстанавливает эмодзи валюты на текущем сервере.", inline=False)
    emb5.add_field(name="reset-xp", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `reset-xp <@member>`\nСбрасывает уровень и опыт участника `member`", inline=False)
    
    
    emb6 = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.\n", color=MainColor)
    emb6.add_field(name="ban", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `ban <@member> [reason]`\nБанит участника `member` по причине `reason`. Если `reason` не был указан, тогда причиной будет `'No reason provided'`", inline=False)
    emb6.add_field(name="unban", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `unban <@member> [reason]`\nРазбанивает участника `member` по причине `reason`. Если `reason` не был указан, тогда причиной будет `'No reason provided'`", inline=False)
    emb6.add_field(name="kick", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `kick <@member> [reason]`\nКикает участника `member` по причине `reason`. Если `reason` не был указан, тогда причиной будет `'No reason provided'`", inline=False)
    emb6.add_field(name="warn", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `warn <@member> [reason]`\nВыдает предупреждение участнику `member` по причине `reason`. Если `reason` не был указан, тогда причиной будет `'No reason provided'`", inline=False)
    emb6.add_field(name="remwarn", value="`ADMIN-ONLY`\nАлиасы: `remove-warn`, `rem-warn`\nИспользование: `remwarn <@member> <index>`\nСнимает у участника `member` предупреждение под номером `index`", inline=False)
    emb6.add_field(name="warns", value="Алиасы: `listwarn`\nИспользование: `warns <@member>`\nПоказывает все предупреждения участника `member`", inline=False)
    
    
    emb7 = discord.Embed(title="Помощь", description="<arg> - обязательный аргумент,\n[arg] - необязательный аргумент.\n", color=MainColor)
    emb7.add_field(name="add-item", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `add-item <@role> <cost> <description>`\nДобавляет предмет `role` с описанием `description` и ценой `cost` в магазин.", inline=False)
    emb7.add_field(name="remove-item", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `remove-item <@role>`\nУдаляет предмет из магазина.", inline=False)
    emb7.add_field(name="shop", value="Без алиасов.\nИспользование: `shop`\nПоказывает магазин сервера.", inline=False)
    emb7.add_field(name="coupons", value="`ADMIN-ONLY`\nБез алиасов.\nИспользование: `coupons`\nПоказывает купоны сервера.", inline=False)
    
    embeds = [emb, emb1, emb2, emb3, emb4, emb5, emb6]
    message = await ctx.send(embed=emb)
    Page = Paginator(bot, message, only=ctx.author, use_more=True, embeds=embeds, use_exit=True, timeout=70)
    await Page.start()

@bot.command(aliases=["drop"], pass_content=True)
@commands.has_permissions(administrator=True)
async def giveaway(ctx, timeout: int = None, reward = None):
    if ctx.guild is not None:
        
        if timeout is not None and timeout >= 60:
            currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
            if currency != None:
                currency = bot.get_emoji(currency[0])
            else:
                currency = '💵'
            if reward == None:
                await ctx.send(embed=discord.Embed(description="Вы не указали награду", color=MainColor))
            elif isinstance(reward, discord.Role):
                
                msg = await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention} начал розыгрыш!\nПриз: {reward.mention}\nУчастников: 0", color=MainColor))
                cur.execute(f"INSERT INTO giveaways VALUES ({ctx.guild.id}, {msg.id}, 'role', {reward.id}, 0, {ctx.author.id})")
                conn.commit()
                await msg.add_reaction('✅')
                await ctx.message.delete()
                asyncio.sleep(timeout)
                users = []
                async for react in msg.reactions:
                    if str(react.emoji) == '✅':
                        async for user in react.users():
                            if user.id != bot.user.id:
                                users.append(user)
                            else:
                                pass
                    else:
                        pass
                if len(users) > 0:
                    winner = random.choice(users)
                    if cur.execute(f"SELECT cash FROM users WHERE id = {winner.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                        adduser(userid=winner.id, guildid=ctx.guild.id)
                    await msg.edit(embed=discord.Embed(description=f"Розыгрыш завершен!\nПобедитель: **{winner.name}** ({winner.mention})", color=MainColor))
                    await user.add_roles(reward, reason="Giveaway reward!")
                    cur.execute(f"DELETE FROM giveaways WHERE guildid = {ctx.guild.id} AND messageid = {msg.id}")
                    conn.commit()
                else:
                    await msg.edit(embed=discord.Embed(description=f"Розыгрыш завершен!\nПобедитель отсутствует, так как никто не учавствовал в розыгрыше.", color=MainColor))
                    cur.execute(f"DELETE FROM giveaways WHERE guildid = {ctx.guild.id} AND messageid = {msg.id}")
                    conn.commit()
                
            else:
                try:
                    reward = int(reward)
                except ValueError:
                    pass
                if isinstance(reward, int):
                    money =	'money'
                    msg = await ctx.send(embed=discord.Embed(description=f"{ctx.author.mention} начал розыгрыш!\nПриз: {reward} {str(currency)}\nУчастников: 0", color=MainColor))
                    cur.execute(f"INSERT INTO giveaways VALUES ({ctx.guild.id}, {msg.id}, 'money', {reward}, 0, {ctx.author.id})")
                    conn.commit()
                    await msg.add_reaction('✅')
                    await ctx.message.delete()
                    asyncio.sleep(timeout)
                    users = []
                    async for react in msg.reactions:
                        if str(react.emoji) == '✅':
                            async for user in react.users():
                                if user.id != bot.user.id:
                                    users.append(user)
                                else:
                                    pass
                        else:
                            pass
                    if len(users) > 0:
                        winner = random.choice(users)
                        if cur.execute(f"SELECT cash FROM users WHERE id = {winner.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                        	adduser(userid=winner.id, guildid=ctx.guild.id)
                        await msg.edit(embed=discord.Embed(description=f"Розыгрыш завершен!\nПобедитель: **{winner.name}** ({winner.mention})", color=MainColor))
                        cur.execute(f"UPDATE users SET cash = cash + {reward} WHERE id = {winner.id} AND guildid = {ctx.guild.id}")
                        conn.commit()
                        cur.execute(f"DELETE FROM giveaways WHERE guildid = {ctx.guild.id} AND messageid = {msg.id}")
                        conn.commit()
                    else:
                        await msg.edit(embed=discord.Embed(description=f"Розыгрыш завершен!\nПобедитель отсутствует, так как никто не учавствовал в розыгрыше.", color=MainColor))
                        cur.execute(f"DELETE FROM giveaways WHERE guildid = {ctx.guild.id} AND messageid = {msg.id}")
                        conn.commit()
                else:
                    await ctx.send(embed=discord.Embed(description=f"Неизвестный тип награды: **{str(type(reward))}"))
        elif timeout < 60:
            await ctx.send(embed=discord.Embed(description="Минимальный таймаут - 60", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали таймаут", color=MainColor))
    else:
        pass

@bot.command(pass_content=True)
@commands.has_permissions(administrator=True)
async def ban(ctx, member: discord.Member = None, *, reason: str = 'No reason provided'):
    if ctx.guild is not None:
        
        if member is not None:
            
            await member.ban(reason=reason)
            if reason == 'No reason provided':
                reason == 'Отсутствует'
            await ctx.send(embed=discord.Embed(description="Участник **{member.name}** был забанен по причине \"**{reason}**\"", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали участника которого необходимо забанить.", color=MainColor))
    else:
        pass

@bot.command(pass_content=True)
@commands.has_permissions(administrator=True)
async def kick(ctx, member: discord.Member = None, *, reason: str = 'No reason provided'):
    if ctx.guild is not None:
        
        if member is not None:
            
            await member.ban(reason=reason)
            if reason == 'No reason provided':
                reason == 'Отсутствует'
            await ctx.send(embed=discord.Embed(description="Участник **{member.name}** был кикнут по причине \"**{reason}**\"", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали участника которого необходимо кикнуть.", color=MainColor))
    else:
        pass

@bot.command(pass_content=True)
@commands.has_permissions(administrator=True)
async def unban(ctx, member: discord.User = None, *, reason: str = 'No reason provided'):
    if ctx.guild is not None:
        
        if member is not None:
            
            if isinstance(member, discord.User):
                await ctx.guild.unban(member, reason=reason)
                if reason == 'No reason provided':
                    reason == 'Отсутствует'
                await ctx.send(embed=discord.Embed(description="Пользователь **{member.name}** был разбанен по причине \"**{reason}**\"", color=MainColor))
            else:
                await ctx.send(embed=discord.Embed(description="Я не смог найти пользователя с указанным ID..", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали ID пользователя которого необходимо разбанить.", color=MainColor))
    else:
        pass

@bot.command(pass_content=True)
@commands.has_permissions(administrator=True)
async def warn(ctx, member: discord.Member = None, *, reason: str = 'No reason provided'):
    
    if ctx.guild is not None:
        
        if member is not None:
            reason = reason.replace("'", "").replace('"', '')
            try:
                num = len(cur.execute(f"SELECT number FROM warns WHERE guildid = {ctx.guild.id} AND userid = {member.id}").fetchall()) + 1
            except TypeError:
                num = 1
            cur.execute(f"INSERT INTO warns VALUES ({ctx.guild.id}, {member.id}, {ctx.author.id}, {num}, '{reason}')")
            conn.commit()
            await ctx.send(embed=discord.Embed(description=f"Участнику **{member.mention}** было выдано предупреждение `#{num}`", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали участника которому хотите выдать варн.", color=MainColor))
    else:
        pass

@bot.command(aliases=["remove-warn", "rem-warn"], pass_content=True)
@commands.has_permissions(administrator=True)
async def remwarn(ctx, member: discord.Member = None, index: int = None):
    if ctx.guild is not None:
        
        if member is not None:
            
            if index is not None:
                
                if cur.execute(f"SELECT number FROM warns WHERE userid = {member.id} AND guildid = {ctx.guild.id} AND number = {index}").fetchone() == None:
                    await ctx.send(embed=discord.Embed(description=f"У пользователя {member.mention} не было найдено предупреждения под номером **{index}**", color=MainColor))
                else:
                    cur.execute(f"DELETE FROM warns WHERE userid = {member.id} AND guildid = {ctx.guild.id} AND number = {index}")
                    conn.commit()
                    await ctx.send(embed=discord.Embed(description=f"Предупреждение `#{index}` было снято.", color=MainColor))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали номер предупреждения.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали участника", color=MainColor))
    else:
        pass

@bot.command(aliases=["listwarns"])
async def warns(ctx, member: discord.Member = None):
    if ctx.guild is not None:
        
        if member is not None:
            emb = discord.Embed(title=f"Предупреждения участника {member.name}:", color=MainColor)
            for entry in cur.execute(f"SELECT * FROM warns WHERE guildid = {ctx.guild.id} AND userid = {member.id}").fetchall():
                moderator = bot.get_user(entry[2])
                number = entry[3]
                reason = entry[4]
                emb.add_field(name=f"Предупреждение `#{number}`", value=f"Модератор: **{moderator.name}** ({moderator.mention})\nПричина: {reason}")
            if emb.fields not in [None, discord.Embed.Empty, []]:
                await ctx.send(embed=emb)
            else:
                await ctx.send(embed=discord.Embed(description=f"У пользователя {member.mention} нету предупреждений.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали пользователя.", color=MainColor))
    else:
        pass

@bot.command(aliases=["create-coupon"], pass_content=True)
@commands.has_permissions(administrator=True)
async def create_coupon(ctx, name: str = None, amount: int = None, max_uses: int = None):
    if ctx.guild is not None:
        
        if name is not None:
            
            if amount is not None:
                
                if max_uses is not None:
                    name = name.replace("'", "").replace('"', '')
                    if cur.execute(f"SELECT name FROM coupons WHERE name = '{name}' AND guildid = {ctx.guild.id}").fetchone() == None:
                        cur.execute(f"INSERT INTO coupons VALUES ({ctx.guild.id}, '{name}', {amount}, {max_uses}, 0, {ctx.author.id})")
                        conn.commit()
                        await ctx.send(embed=discord.Embed(description=f"Купон **{name}** создан.\nМаксимум использований: **{max_uses}**\nНаграда: **{amount}**", color=MainColor))
                    else:
                        await ctx.send(embed=discord.Embed(description="Такой купон уже существует.", color=MainColor))
                else:
                    await ctx.send(embed=discord.Embed(description="Вы не указали максимальное кол-во использований."))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали кол-во денег выдаваемых при использовании этого купона.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали имя для купона.", color=MainColor))
    else:
        pass

@bot.command(aliases=["delete-coupon"], pass_content=True)
@commands.has_permissions(administrator=True)
async def delete_coupon(ctx, name: str = None):
    if ctx.guild is not None:
        
        if name is not None:
            name = name.replace("'", "").replace('"', '')
            if cur.execute(f"SELECT name FROM coupons WHERE name = '{name}' AND guildid = {ctx.guild.id}").fetchone() == None:
                await ctx.send(embed=discord.Embed(description=f"На этом сервере нету купона с именем **{name}**", color=MainColor))
            else:
                cur.execute(f"DELETE FROM coupons WHERE guildid = {ctx.guild.id} AND name = '{name}'")
                conn.commit()
                await ctx.send(embed=discord.Embed(description=f"Купон **{name}** был удален.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали имя купона", color=MainColor))
    else:
        pass

@bot.command(aliases=["use-coupon"])
@commands.cooldown(rate=1, per=1800, type=commands.BucketType.member)
async def coupon(ctx, name: str = None):
    if ctx.guild is not None:
        
        if name is not None:
            name = name.replace("'", "").replace('"', '')
            if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                adduser(userid=ctx.author.id, guildid=ctx.guild.id)
            else:
                pass
            if cur.execute(f"SELECT name FROM coupons WHERE name = '{name}' AND guildid = {ctx.guild.id}").fetchone() == None:
                await ctx.send(embed=discord.Embed(description=f"На этом сервере нету купона с именем **{name}**", color=MainColor))
            else:
                if cur.execute(f"SELECT uses FROM coupons WHERE name = '{name}' AND guildid = {ctx.guild.id}").fetchone()[0] == cur.execute(f"SELECT maxuses FROM coupons WHERE name = '{name}' AND guildid = {ctx.guild.id}").fetchone()[0]:
                    await ctx.send(embed=discord.Embed(description=f"Данный купон уже использовали максимальное количество раз.", color=MainColor))
                else:
                    currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
                    if currency != None:
                        currency = bot.get_emoji(currency[0])
                    else:
                        currency = '💵'
                    award = cur.execute(f"SELECT reward FROM coupons WHERE guildid = {ctx.guild.id} AND name = '{name}'").fetchone()[0]
                    author = await bot.fetch_user(cur.execute(f"SELECT author FROM coupons WHERE guildid = {ctx.guild.id} AND name = '{name}'").fetchone()[0])
                    uses = cur.execute(f"SELECT uses FROM coupons WHERE guildid = {ctx.guild.id} AND name = '{name}'").fetchone()[0] + 1
                    max_uses = cur.execute(f"SELECT maxuses FROM coupons WHERE guildid = {ctx.guild.id} AND name = '{name}'").fetchone()[0]
                    if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                        adduser(userid=ctx.author.id, guildid=ctx.guild.id)
                    cur.execute(f"UPDATE users SET cash = cash + {award} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
                    conn.commit()
                    cur.execute(f"UPDATE coupons SET uses = uses + 1 WHERE guildid = {ctx.guild.id} AND name = '{name}'")
                    conn.commit()
                    await ctx.send(embed=discord.Embed(description=f"Вы использовали купон **{name}** от {author.mention} и получили **{award}** {str(currency)}!\nОсталось использований: **{max_uses - uses}**", color=MainColor), delete_after=5.0)
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали купон.", color=MainColor))
    else:
        pass

@bot.command(aliases=["set-currency-symbol"], pass_content=True)
@commands.has_permissions(administrator=True)
async def set_currency_symbol(ctx, symbol: discord.Emoji = None):
    if ctx.guild is not None:
        
        if symbol is not None:
            if cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone() in [None, 0]:
                cur.execute(f"INSERT INTO guilds VALUES ({ctx.guild.id}, {symbol.id}, 50, 0)")
                conn.commit()
            else:
                cur.execute(f"UPDATE guilds SET currency = {symbol.id} WHERE guildid = {ctx.guild.id}")
                conn.commit()
            await ctx.send(embed=discord.Embed(description=f"{str(symbol)} установлен как значок валюты на этом сервере.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали эмодзи валюты.", color=MainColor))
    else:
        pass

@bot.command(aliases=["set-crime-chance"], pass_content=True)
@commands.has_permissions(administrator=True)
async def set_crime_chance(ctx, chance: int = None):
    if ctx.guild is not None:
        
        if chance is not None and chance > 15 and chance < 90:
            
            if cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone() in [None, 0]:
                cur.execute(f"INSERT INTO guilds VALUES ({ctx.guild.id}, 0, {chance}, 0)")
                conn.commit()
            else:
                cur.execute(f"UPDATE guilds SET crimechance = {chance} WHERE guildid = {ctx.guild.id}")
                conn.commit()
            await ctx.send(embed=discord.Embed(description=f"Шанс кражи для этого сервера установлен на **{chance}**"))
        elif chance is not None and chance < 15:
            await ctx.send(embed=discord.Embed(description="Шанс должен быть больше 15", color=MainColor))
        elif chance is not None and chance > 90:
            await ctx.send(embed=discord.Embed(description="Шанс должен быть меньше 90", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали шанс", color=MainColor))
    else:
        pass

@bot.command(pass_content=True)
@commands.cooldown(rate=1, per=3600, type=commands.BucketType.member)
async def work(ctx):
    if ctx.guild is not None:
        currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if currency != None:
            currency = bot.get_emoji(currency[0])
        else:
            currency = '💵'
        if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
            adduser(userid=ctx.author.id, guildid=ctx.guild.id)
        else:
            pass
        award = random.randint(150, 350)
        cur.execute(f"UPDATE users SET cash = cash + {award} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
        conn.commit()
        workmsg = random.choice(works)[0]
        emb = discord.Embed(description=workmsg + f"**{award}** {str(currency)}", color=MainColor)
        await ctx.send(embed=emb)
    else:
        pass

@bot.command()
@commands.cooldown(rate=1, per=3600, type=commands.BucketType.member)
async def crime(ctx):
    if ctx.guild is not None:
        
        currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if currency != None:
            currency = bot.get_emoji(currency[0])
        else:
            currency = '💵'
        
        chance = cur.execute(f"SELECT crimechance FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
        if chance == None:
            cur.execute(f"INSERT INTO guilds VALUES ({ctx.guild.id}, 0, 50, 0)")
            conn.commit()
        else:
            chance = chance[0]
        win = None
        luck = random.randint(1, 100)
        if luck <= chance:
            win = True
        else:
            win = False
        if cur.execute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone() == None:
            adduser(userid=ctx.author.id, guildid=ctx.guild.id)
        else:
            pass
        if win == True:
            award = random.randint(200, 500)
            cur.exexute(f"UPDATE users SET cash = cash + {award} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
            conn.commit()
            crimemsg = random.choice(crimes_positive)[0]
            emb = discord.Embed(description=crimemsg + f"**{award}** {str(currency)}", color=MainColor)
            await ctx.send(embed=emb)
        else:
            cost = random.randint(100, 400)
            if cur.exexute(f"SELECT cash FROM users WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}").fetchone()[0] >= cost:
                cur.exexute(f"UPDATE users SET cash = cash - {cost} WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
                conn.commit()
            else:
                cur.exexute(f"UPDATE users SET cash = 0 WHERE id = {ctx.author.id} AND guildid = {ctx.guild.id}")
                conn.commit()
            crimemsg = random.choice(crimes_negative)[0]
            emb = discord.Embed(description=crimemsg + f"**{award}** {str(currency)}", color=MainColor)
            await ctx.send(embed=emb)
    else:
        pass

@bot.command(aliases=["reset-xp"], pass_content=True)
@commands.has_permissions(administrator=True)
async def reset_xp(ctx, member: discord.Member = None):
    if ctx.guild is not None:
        
        if member is not None:
            
            if cur.execute(f"SELECT cash FROM users WHERE id = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                adduser(userid=member.id, guildid=ctx.guild.id)
                await ctx.send(embed=discord.Embed(description=f"Уровень и опыт участника {member.mention} обнулены!", color=MainColor))
            else:
                cur.execute(f"UPDATE users SET lvl = 1, xp = 0 WHERE id = {member.id} AND guildid = {ctx.guild.id}")
                conn.commit()
                await ctx.send(embed=discord.Embed(description=f"Уровень и опыт участника {member.mention} обнулены!", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали участника.", color=MainColor))
    else:
        pass

@bot.command(aliases=["cmd", "eval"])
async def evaluate(ctx, *, code: str = None):
    isowner = await bot.is_owner(user=ctx.author)
    if isowner == True and code != None:
        try:
            result = eval(code)
            await ctx.send(embed=discord.Embed(description=f"```py\n{result}\n```", color=MainColor))
        except Exception as e:
            await ctx.send(embed=discord.Embed(description=f"```py\n{e}\n```", color=MainColor))
        finally:
            await ctx.send(embed=discord.Embed(description="Операция завершена.", color=MainColor).set_footer(text="Напоминание: результат выполнения кода помещается в переменную, которая потом отправляется в чат. Это значит, что если функция которую вы выполнили ничего не возвращает, то в результате выполнения кода вы увидите лишь None, но это не значит что код не выполнился."))
    elif isowner == True and code == None:
        await ctx.send("А код где?..")
    else:
        pass

@bot.command()
async def shop(ctx):
    if ctx.guild is not None:
        
        if cur.execute(f"SELECT item FROM shop WHERE guildid = {ctx.guild.id}").fetchone() == None:
            await ctx.send(embed=discord.Embed(description="Магазин пуст", color=MainColor))
        else:
            currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
            if currency != None:
                currency = bot.get_emoji(currency[0])
            else:
                currency = '💵'
            
            emb = discord.Embed(title=f"Магазин сервера {ctx.guild.name}", color=MainColor)
            for entry in cur.execute(f"SELECT * FROM shop WHERE guildid = {ctx.guild.id}").fetchall():
                cost = entry[1]
                item = ctx.guild.get_role(entry[2])
                description = entry[3]
                emb.add_field(name=f"{item.name}", value=f"{item.mention} | **{cost}** {str(currency)}\n{description}")
            await ctx.send(embed=emb)

@bot.command(aliases=["add-item", "add-shop"], pass_content=True)
@commands.has_permissions(administrator=True)
async def add_item(ctx, role: discord.Role = None, cost: int = None, *, description: str = None):
    if ctx.guild is not None:
        
        if role is not None:
            
            if cost is not None:
                
                if description is not None:
                    currency = cur.execute(f"SELECT currency FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()
                    if currency != None:
                        currency = bot.get_emoji(currency[0])
                    else:
                        currency = '💵'
                    description = description.replace("'", "").replace('"', '')
                    cur.execute(f"INSERT INTO shop VALUES ({ctx.guild.id}, {cost}, {role.id}, '{description}')")
                    conn.commit()
                    await ctx.send(embed=discord.Embed(description=f"В магазин добавлена роль {role.mention}\nЦена: **{cost}** {str(currency)}\nОписание: **{description}**", color=MainColor))
                else:
                    await ctx.send(embed=discord.Embed(description="Вы не указали описание.", color=MainColor))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали стоимость.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали роль.", color=MainColor))
    else:
        pass

@bot.command(aliases=["listcoupons"], pass_content=True)
@commands.has_permissions(administrator=True)
async def coupons(ctx):
    if ctx.guild is not None:
        emb = discord.Embed(title=f"Купоны сервера {ctx.guild.name}:", color=MainColor)
        loop = 0
        for entry in cur.execute(f"SELECT * FROM coupons WHERE guildid = {ctx.guild.id}").fetchall():
            loop += 1
            name = entry[1]
            reward = entry[2]
            maxuses = entry[3]
            uses = entry[4]
            author = ctx.guild.get_member(entry[5])
            emb.add_field(name=f"Купон `#{loop}`", value=f"Название: **{name}**\nПриз: **{reward}**\nИспользований: **{uses}**/**{maxuses}**\nСоздатель: **{author.name + author.discriminator}** ({author.mention})")
        if emb.fields not in [None, discord.Embed.Empty, []]:
            await ctx.send(embed=emb)
        else:
            await ctx.send(embed=discord.Embed(description=f"На этом сервере нет купонов.", color=MainColor))
    else:
        pass

@bot.command(name="remove-item", pass_content=True)
@commands.has_permissions(administrator=True)
async def remove_item(ctx, role: discord.Role = None):
    if ctx.guild is not None:
        
        if role is not None:
            
            if cur.execute(f"SELECT cost FROM shop WHERE guildid = {ctx.guild.id} AND item = {role.id}").fetchone() == None:
                await ctx.send(embed=discord.Embed(description="На этом сервере нет такого предмета.", color=MainColor))
            else:
                cur.execute(f"DELETE FROM shop WHERE guildid = {ctx.guild.id} AND item = {role.id}")
                conn.commit()
                await ctx.send(embed=discord.Embed(description=f"Предмет {role.mention} был удален.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали роль.", color=MainColor))
    else:
        pass

@bot.command(pass_content=True)
@commands.has_permissions(administrator=True)
async def mute(ctx, member: discord.Member = None, time: int = None, *, reason: str = None):
    if ctx.guild is not None:
        
        if member is not None:
            
            if time is not None and time >= 60:
                
                if reason is not None:
                    
                    if cur.execute(f"SELECT reason FROM mutes WHERE userid = {member.id} AND guildid = {ctx.guild.id}").fetchone() == None:
                        reason = reason.replace("'", "").replace('"', '')
                        if cur.execute(f"SELECT muterole FROM guilds WHERE guildid = {ctx.guild.id}").fetchone() == None:
                            P = discord.Permissions(send_messages=False, add_reactions=False, speak=False)
                            role = await ctx.guild.create_role(name="{RULE_BREAKER}", permissions=P, reason="Because mute role was not found on this server, I created new role. It will be used by default now.")
                            cur.execute(f"INSERT INTO guilds VALUES ({ctx.guild.id}, 0, 50, {role.id}")
                            conn.commit()
                            await member.add_roles(role, reason=f"Muted by {ctx.author.name + '#' + ctx.author.discriminator} at {str(datetime.datetime.now())}")
                        elif cur.execute(f"SELECT muterole FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()[0] == 0:
                            P = discord.Permissions(send_messages=False, add_reactions=False, speak=False)
                            role = await ctx.guild.create_role(name="{RULE_BREAKER}", permissions=P, reason="Because mute role was not found on this server, I created new role. It will be used by default now.")
                            cur.execute(f"UPDATE guilds SET muterole = {role.id} WHERE guildid = {ctx.guild.id}")
                            conn.commit()
                            await member.add_roles(role, reason=f"Muted by {ctx.author.name + '#' + ctx.author.discriminator} at {str(datetime.datetime.now())}")
                        else:
                            role = ctx.guild.get_role(cur.execute(f"SELECT muterole FROM guilds WHERE guildid = {ctx.guild.id}").fetchone()[0])
                            await member.add_roles(role, reason=f"Muted by {ctx.author.name + '#' + ctx.author.discriminator} at {str(datetime.datetime.now())}")
                        cur.execute(f"INSERT INTO mutes VALUES ({ctx.guild.id}, {member.id}, '{reason}'")
                        conn.commit()
                        await ctx.send(embed=discord.Embed(description=f"Участник {member.mention} был замучен на **{time}** секунд по причине **{reason}**", color=MainColor))
                        await asyncio.sleep(time)
                        cur.execute(f"DELETE FROM mutes WHERE guildid = {ctx.guild.id} AND userid = {member.id}")
                        conn.commit()
                    else:
                        await ctx.send(embed=discord.Embed(description=f"Участник {member.mention} уже замучен.", color=MainColor))
                else:
                    await ctx.send(embed=discord.Embed(description="Вы не указали причину.", color=MainColor))
            elif time is not None and time < 60:
                await ctx.send(embed=discord.Embed(description="Время должно быть больше или равно 60", color=MainColor))
            else:
                await ctx.send(embed=discord.Embed(description="Вы не указали время.", color=MainColor))
        else:
            await ctx.send(embed=discord.Embed(description="Вы не указали участника.", color=MainColor))
    else:
        pass

#COUPONS       SHOP              MUTES      
#guildid INT   guildid INT       guildid INT
#name TEXT     cost INT          userid INT 
#reward INT    item INT          reason TEXT
#maxuses INT   description INT              
#uses INT                                   
#author INT                                 

#USERS         GIVEAWAYS         WARNS
#cash INT      guildid INT       guildid INT
#id INT        messageid INT     userid INT
#guildid INT   rewardtype TEXT   authorid INT
#lvl INT       reward INT        number INT
#xp INT        members INT       reason TEXT
#              authorid INT      

#GUILDS
#guildid INT
#currency INT
#crimechance INT
#muterole INT

def restart_program():
    python = sys.executable
    os.execl(python, python, * sys.argv)

@bot.command()
async def restart(ctx):
    if ctx.author.id in [833772802254700544, 486182622565761026]:
        await ctx.send("Reloading. . .")
        restart_program()













bot.run("")
input("...Something went wrong...")
