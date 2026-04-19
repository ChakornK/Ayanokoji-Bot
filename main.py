import discord 
from discord.ext import commands
import logging
from dotenv import load_dotenv 
import os
from yt_dlp import YoutubeDL
from pathlib import Path #turns strings to path objects (I think)
import subprocess #allows to run command line inputd

#referneces:
#   Instagram:
#       https://www.instagram.com/reel/DW2JZIyD28O/?igsh=enI1ejQ5enpwYWZ6
#       https://www.instagram.com/reel/DW2JZIyD28O/?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ==
#   Reddit:
#       https://www.reddit.com/r/aviation/comments/1so32ib/how_concerning_is_this_aviation_experts/
#       https://www.reddit.com/r/moviecritic/comments/1sof97o/what_is_the_scariest_most_unsettling_shot_youve/

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf=8', mode='w')
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")


ydl_opts = {
    'format': 'best',
    'outtmpl': '%(title)s.%(ext)s',
}

#Rewrite when using a bot host
ffmpegP = "C:\\Libraries\\ffmpeg\\bin\\ffmpeg.exe"
ffprobeP =  "C:\\Libraries\\ffmpeg\\bin\\ffprobe.exe"

def vidCompression(maxSizeMB, infile, outfile):
    #1MB = 8000kb
    maxSizekb = (maxSizeMB-1) * 8000

    result = subprocess.run(
        [
            ffprobeP,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            infile
        ],
        capture_output=True,
        text=True
    )

    duration = float(result.stdout.strip())

    bitRate = f"{int(maxSizekb / duration)}k"

    subprocess.run([
        ffmpegP,
        "-i", infile,
        "-b:v", bitRate,
        "-b:a", "128k",
        outfile
    ])

    return outfile

def grabLink(text):
    start = text.find("https://")
    end = text.find(" ", start)

    if start != -1:
        if end == -1:  
            end = len(text)
        text = text[start:end]

    return text

maxSize = 10 #in MB
Firedownz_ID = 478004323700441108

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    URL = grabLink(message.content)

    if "www.instagram.com/reel" in URL:

        infile = None
        outfile = None

        try: 
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(URL, download = True)

                title = info.get("description")

                filename = ydl.prepare_filename(info) #filepath

            infile = Path(filename)

            if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: #size is in bytes, therefore conversion MB->Bytes
                infile = str(filename)
                outfile = str(Path(filename).with_stem(Path(filename).stem + "_compressed"))

                outfile = vidCompression(maxSize, infile, outfile)
                print("compression")
            else:
                outfile = infile
                print("No compression")

            await message.reply(f"**{title}**", file=discord.File(outfile))
        except Exception as e:
            user = await bot.fetch_user(Firedownz_ID)
            await message.reply(f"{user.mention}Download/send failed: `{e}`")

        finally:
            if outfile and outfile.exists():
                outfile.unlink(missing_ok=True)
                print("Delete outfile")

            if infile and infile.exists():
                infile.unlink(missing_ok=True)
                print("Deleted infile")
        

    
    await bot.process_commands(message)


bot.run(token, log_handler=handler, log_level=logging.DEBUG)