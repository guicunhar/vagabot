import os
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
import discord
from discord.ext import commands
import csv

# ----------------------- Configuração -----------------------
load_dotenv()  # Lê o arquivo .env

TOKEN = os.getenv("DISCORD_TOKEN")
TEXT_CHANNEL_ID = os.getenv("TEXT_CHANNEL_ID")
TEXT_CHANNEL_ID = int(TEXT_CHANNEL_ID) if TEXT_CHANNEL_ID else None

PREFIX = "-"

# ----------------------- Logging -----------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-monitor")

# ----------------------- Intents -----------------------
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True  # Necessário pra listar quem está no canal
intents.message_content = True 

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


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

def atualizar_tempo_csv(member_id, duracao):
    """Atualiza (ou cria) a linha do usuário no arquivo CSV somando a duração."""
    arquivo = "voice_log.csv"

    # Ler o conteúdo atual
    dados = {}
    try:
        with open(arquivo, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    uid, tempo_str = row
                    # Converter tempo acumulado (ex: '0:10:05') para timedelta
                    try:
                        h, m, s = map(int, tempo_str.split(":"))
                        tempo_total = timedelta(hours=h, minutes=m, seconds=s)
                    except ValueError:
                        tempo_total = timedelta()
                    dados[uid] = tempo_total
    except FileNotFoundError:
        pass 

    # Somar ou criar o tempo
    duracao_td = duracao if isinstance(duracao, timedelta) else timedelta()
    if str(member_id) in dados:
        dados[str(member_id)] += duracao_td
    else:
        dados[str(member_id)] = duracao_td

    with open(arquivo, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for uid, tempo_total in dados.items():
            h, m, s = str(tempo_total).split(":")
            writer.writerow([uid, f"{int(float(h))}:{m}:{s.split('.')[0]}"])

import csv
from datetime import datetime, timedelta

voice_entry_times = {}

def atualizar_tempo_csv(member_id, duracao):
    """Atualiza (ou cria) a linha do usuário no arquivo CSV somando a duração."""
    arquivo = "voice_log.csv"
    dados = {}

    # Ler o conteúdo atual
    try:
        with open(arquivo, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    uid, tempo_str = row
                    try:
                        h, m, s = map(int, tempo_str.split(":"))
                        tempo_total = timedelta(hours=h, minutes=m, seconds=s)
                    except ValueError:
                        tempo_total = timedelta()
                    dados[uid] = tempo_total
    except FileNotFoundError:
        pass

    # Somar ou criar o tempo
    duracao_td = duracao if isinstance(duracao, timedelta) else timedelta()
    if str(member_id) in dados:
        dados[str(member_id)] += duracao_td
    else:
        dados[str(member_id)] = duracao_td

    # Regravar o arquivo inteiro
    with open(arquivo, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for uid, tempo_total in dados.items():
            total_str = str(tempo_total).split(".")[0]
            writer.writerow([uid, total_str])

@bot.event
async def on_voice_state_update(member, before, after):
    """Detecta entrada e saída de canais de voz e mostra no terminal."""
    try:
        before_channel = before.channel
        after_channel = after.channel

        # Entrou
        if before_channel is None and after_channel is not None:
            hora_entrada = datetime.now()
            voice_entry_times[member.id] = hora_entrada
            print(f"🟢 {member.display_name} entrou em {after_channel.name} às {hora_entrada.strftime('%d/%m/%Y %H:%M:%S')}")

        # Saiu
        elif before_channel is not None and after_channel is None:
            hora_saida = datetime.now()
            hora_entrada = voice_entry_times.pop(member.id, None)

            if hora_entrada:
                duracao = hora_saida - hora_entrada
                duracao_str = str(duracao).split('.')[0]
                print(
                    f"🔴 {member.display_name} saiu de {before_channel.name} às "
                    f"{hora_saida.strftime('%d/%m/%Y %H:%M:%S')} (ficou por {duracao_str})"
                )

                atualizar_tempo_csv(member.id, duracao)
            else:
                print(f"🔴 {member.display_name} saiu de {before_channel.name} às {hora_saida.strftime('%d/%m/%Y %H:%M:%S')}")

    except Exception as e:
        print(f"⚠️ Erro ao processar mudança de voz: {e}")

# ----------------------- Comandos -----------------------
def carregar_ranking():
    """Lê o CSV e retorna lista ordenada [(user_id, timedelta), ...]"""
    arquivo = "voice_log.csv"
    ranking = []
    try:
        with open(arquivo, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    uid, tempo_str = row
                    try:
                        h, m, s = map(int, tempo_str.split(":"))
                        tempo_total = timedelta(hours=h, minutes=m, seconds=s)
                        ranking.append((uid, tempo_total))
                    except ValueError:
                        pass
    except FileNotFoundError:
        return []
    ranking.sort(key=lambda x: x[1], reverse=True)
    return ranking

@bot.command(name="rank")
async def rank(ctx):
    """Mostra o ranking de tempo total em call."""
    ranking = carregar_ranking()
    if not ranking:
        await ctx.send("📊 Nenhum dado encontrado no `voice_log.csv` ainda.")
        return

    # Monta o texto do ranking
    msg = ["🏆 **RANK DE TEMPO EM CALL** 🏆\n"]
    for i, (uid, tempo) in enumerate(ranking, 1):
        user = await bot.fetch_user(int(uid))  # tenta buscar o nome do usuário
        nome = user.display_name if user else uid
        msg.append(f"**{i}.** {nome} — `{str(tempo).split('.')[0]}`")

    # Adiciona data/hora da última atualização do arquivo CSV
    try:
        arquivo = "voice_log.csv"
        ultima_modificacao = datetime.fromtimestamp(os.path.getmtime(arquivo))
        msg.append(f"\n🕒 **Última atualização:** {ultima_modificacao.strftime('%d/%m/%Y %H:%M:%S')}")
    except Exception:
        msg.append("\n🕒 **Última atualização:** desconhecida")

    await ctx.send("\n".join(msg))


# ----------------------- Execução -----------------------
if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN não configurado no arquivo .env")
        raise SystemExit(1)

    while True:  # modo auto-reconexão
        try:
            bot.run(TOKEN)
        except Exception as e:
            logger.exception("Bot caiu: %s", e)
            logger.info("Tentando reconectar em 10s...")
            asyncio.sleep(10)
