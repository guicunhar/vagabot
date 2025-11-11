import os
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands
import psycopg2

# ----------------------- Configuração -----------------------
load_dotenv()  # Lê o arquivo .env

TOKEN = os.getenv("DISCORD_TOKEN")
TEXT_CHANNEL_ID = os.getenv("TEXT_CHANNEL_ID")
DATABASE_URL = os.getenv("DATABASE_URL")

TEXT_CHANNEL_ID = int(TEXT_CHANNEL_ID) if TEXT_CHANNEL_ID else None
PREFIX = "-"

# ----------------------- Logging -----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-monitor")

# ----------------------- Intents -----------------------
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ----------------------- Banco de Dados -----------------------
def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def setup_database():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS voice_time (
                    user_id TEXT PRIMARY KEY,
                    total_seconds BIGINT NOT NULL DEFAULT 0
                )
            """)
        conn.commit()

setup_database()

def atualizar_tempo_db(member_id, duracao):
    """Atualiza ou cria o registro de tempo no banco."""
    segundos = int(duracao.total_seconds())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO voice_time (user_id, total_seconds)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET total_seconds = voice_time.total_seconds + EXCLUDED.total_seconds;
            """, (str(member_id), segundos))
        conn.commit()

def carregar_ranking_db():
    """Lê o ranking do banco ordenado por tempo total."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, total_seconds
                FROM voice_time
                ORDER BY total_seconds DESC;
            """)
            return cur.fetchall()

# ----------------------- Helper -----------------------
async def send_text(content: str):
    """Envia mensagem para o canal configurado (ou só loga)."""
    if TEXT_CHANNEL_ID:
        channel = bot.get_channel(TEXT_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            await channel.send(content)
    else:
        logger.info(content)

# ----------------------- Eventos -----------------------
@bot.event
async def on_ready():
    logger.info(f"✅ Logado como {bot.user} (ID: {bot.user.id})")
    logger.info("📡 Monitorando eventos de voz...")
    if TEXT_CHANNEL_ID:
        logger.info(f"Mensagens de log serão enviadas ao canal ID {TEXT_CHANNEL_ID}")

voice_entry_times = {}

@bot.event
async def on_voice_state_update(member, before, after):
    """Detecta entrada e saída de canais de voz e registra tempo."""
    try:
        before_channel = before.channel
        after_channel = after.channel

        # Entrou
        if before_channel is None and after_channel is not None:
            hora_entrada = datetime.now()
            voice_entry_times[member.id] = hora_entrada
            print(f"🟢 {member.display_name} entrou em {after_channel.name} às {hora_entrada.strftime('%H:%M:%S')}")

        # Saiu
        elif before_channel is not None and after_channel is None:
            hora_saida = datetime.now()
            hora_entrada = voice_entry_times.pop(member.id, None)
            if hora_entrada:
                duracao = hora_saida - hora_entrada
                atualizar_tempo_db(member.id, duracao)
                print(f"🔴 {member.display_name} saiu (ficou {str(duracao).split('.')[0]})")
    except Exception as e:
        print(f"⚠️ Erro ao processar mudança de voz: {e}")

# ----------------------- Comando rank -----------------------
@bot.command(name="rank")
async def rank(ctx):
    """Mostra o ranking de tempo total em call (do banco)."""
    ranking = carregar_ranking_db()
    if not ranking:
        await ctx.send("📊 Nenhum dado encontrado ainda.")
        return

    msg = ["🏆 **RANK DE TEMPO EM CALL** 🏆\n"]
    for i, (uid, total_seconds) in enumerate(ranking, 1):
        user = await bot.fetch_user(int(uid))
        nome = user.display_name if user else uid
        tempo = str(timedelta(seconds=total_seconds)).split('.')[0]
        msg.append(f"**{i}.** {nome} — `{tempo}`")

    await ctx.send("\n".join(msg))

# ----------------------- Execução -----------------------
if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN não configurado")
        raise SystemExit(1)

    while True:  # modo auto-reconexão
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.exception("Bot caiu: %s", e)
            logger.info("Tentando reconectar em 10s...")
            asyncio.sleep(10)
