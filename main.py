import discord 
from discord.ext import commands
import logging
from dotenv import load_dotenv 
import os
from yt_dlp import YoutubeDL
from pathlib import Path #turns strings to path objects (I think)
import subprocess #allows to run command line inputd
from PIL import Image #Pillow, for image compression
import requests
from urllib.parse import urlparse
import json
import asyncio
import time

#referneces:
#   Instagram:
#       https://www.instagram.com/reel/DW2JZIyD28O/?igsh=enI1ejQ5enpwYWZ6
#       https://www.instagram.com/reel/DW2JZIyD28O/?utm_source=ig_web_copy_link&igsh=NTc4MTIwNjQ2YQ==
#   Reddit:
#       https://www.reddit.com/r/aviation/comments/1so32ib/how_concerning_is_this_aviation_experts/
#       https://www.reddit.com/r/moviecritic/comments/1sof97o/what_is_the_scariest_most_unsettling_shot_youve/
#       https://www.reddit.com/r/whatisit/comments/1sppygk/what_is_this_set_up/
#       https://www.reddit.com/r/TikTokCringe/comments/1spx6o7/the_entire_staff_of_a_zara_chased_after_a_lady/

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

CONFIG_FILE = Path("config.json")

handler = logging.FileHandler(filename='discord.log', encoding='utf=8', mode='w')
intents = discord.Intents.default()
intents.message_content = True

videoSizeRestriction = False
videoDurationRestriction = True
imgSizeRestriction = False

maxVideoSize = 20 * 1024 * 1024 #Bytes
maxVideoDuration = 300 #seconds
maxImgSize = 20 * 1024 * 1024 #Bytes

#Note: There is currently no checks to make sure downloading an image is under the restriction, only checks image during compression phase sop fix this later.

ydl_opts = {
    'format': 'best',
    'outtmpl': '%(title)s.%(ext)s',
}

ydl_opts_youtube = {
    'format': 'bestvideo+bestaudio/best',
    'outtmpl': '%(title)s.%(ext)s',
    'cookiefile': 'www.youtube.com_cookies.txt',
    'merge_output_format': 'mp4',
}

ydl_opts_instagram = {
    'format': 'best',
    'outtmpl': '%(title)s.%(ext)s',
    'cookiefile': 'www.instagram.com_cookies.txt',
}

ydl_opts_tiktok = {
    'format': 'best',
    'outtmpl': '%(title)s.%(ext)s',
    'cookiefile': 'www.tiktok.com_cookies.txt',
}

reddit_opts = {
    'format': 'bestvideo+bestaudio/best',
    'outtmpl': '%(title)s.%(ext)s',
    'merge_output_format': 'mp4',
    'restrictfilenames': True,
    'quiet': True,
    'extract_flat': False,
    'force_generic_extractor': False,
    'cookiefile': 'www.reddit.com_cookies.txt',
}

maxSize = 10 #in MB
Firedownz_ID = 478004323700441108

#Rewrite when using a bot host
ffmpegP = "ffmpeg"
ffprobeP =  "ffprobe"

def load_data():
    if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    else:
        return {}
    
def save_data(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4) #indent=4 makes file more human readable

def get_channel_id(guild_id):
    data = load_data()
    return data.get(str(guild_id), {}).get("channel_id", None)

async def vidCompression(maxSizeMB, infile, outfile, oMessage): #async(ing) a function makes it so that the program can process other stuff while waiting for this function to finish
    infile = Path(infile)
    outfile = Path(outfile)

    target_bytes = (maxSizeMB - 1) * 1024 * 1024

    result = subprocess.run(
        [
            ffprobeP,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(infile)
        ],
        capture_output=True,
        text=True,
        check=True
    )

    duration = float(result.stdout.strip()) #seconds

    if duration is not None and duration >= maxVideoDuration and videoDurationRestriction:
        raise Exception(f"Video is larger than {maxVideoDuration} seconds")
    
    if infile.stat().st_size is not None and infile.stat().st_size / (1024 * 1024) >= maxVideoSize and videoSizeRestriction:
        raise Exception(f"Video is larger than {maxVideoSize / (1024*1024)} MB") 

    audio_bitrate = 32_000   # 32k bits
    total_bitrate = int((target_bytes * 8) / duration)
    video_bitrate = int((total_bitrate - audio_bitrate) * 0.95)

    if video_bitrate <= 10_000:
        raise Exception("Even ultra-low settings are too small for this target")

    cmd = [
        ffmpegP,
        "-y",
        "-i", str(infile),
        "-vf", "scale=-2:240",   # shrink resolution hard
        "-r", "15",              # lower fps
        "-c:v", "libx264",
        "-b:v", f"{max(video_bitrate // 1000, 10)}k",
        "-c:a", "aac",
        "-ac", "1",              # mono audio
        "-b:a", "32k",
        "-progress", "pipe:1",
        str(outfile)
    ]

    proc = await asyncio.create_subprocess_exec( #subprocess.run = freezes and waits; subprocess.open = allows python to do other stuff while waiting; asyncio is the async version which allows for other discord commands
        *cmd, #* is the unpacking operator.Turns list into separate arguments
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    lastEditTime = 0 #important to keep tabs as you can only manipulate discord messages every 0.5-2 seconds

    msg = await oMessage.reply("Compressing: [--------------------] 0%")

    while True:
        line = await proc.stdout.readline()

        if not line:
            break

        line = line.decode().strip()

        if line.startswith("out_time_ms="):
            processed_ms = int(line.split("=")[1])
            processed_seconds = processed_ms / 1_000_000

            percent = min(processed_seconds / duration, 1)

            # only edit every 1 second
            current_time = time.time()

            if current_time - lastEditTime >= 1:
                lastEditTime = current_time

                await msg.edit(
                    content= loadingBarffmpeg(percent)
                )

    await proc.wait()

    await msg.edit(
        content="Compressing: [####################] 100%"
    )

    await msg.delete()

    return outfile

def grabLink(text):
    start = text.find("https://")
    end = text.find(" ", start)

    if start != -1:
        if end == -1:  
            end = len(text)
        text = text[start:end]

    return text
    
def imgCompression(maxSizeMB, infile, outfile):
    quality = 95 #Quality is a pillow/image property from 100 to 0 which represents the % quality of an image

    if infile.stat().st_size is not None and infile.stat().st_size / (1024 * 1024) >= maxImgSize and imgSizeRestriction:
        raise Exception(f"Video is larger than {maxImgSize / (1024*1024)} MB") 

    while quality > 10:
        img = Image.open(infile)
        img.save(outfile, quality=quality)

        size = outfile.stat().st_size
        if size <= (maxSizeMB-1) * 1024 * 1024:
            break

        quality -= 5

    return outfile

def loadingBarffmpeg(percent):
    #Example: Compressing: [#-------------------] 5%
    #20 entries
    filled = int(20 * percent)
    bar = "#" * filled + "-" * (20 - filled)

    return f"Compressing: [{bar}] {int(percent * 100)}%"


bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
async def setChannel(ctx, *, msg):
    if get_channel_id(ctx.guild.id) != None:
        Target_Channel = await bot.fetch_channel(get_channel_id(ctx.guild.id))
    else:
        Target_Channel = None

    try:
        data = load_data()
        guild_id = str(ctx.guild.id)

        if guild_id not in data:
            data[guild_id] = {}

        channel_id = int(msg)
        channel = await bot.fetch_channel(channel_id)
        if Target_Channel == None:
            await ctx.reply(f"Setting channel from 'Nothing' to '{channel.name}':'{channel.id}'")
        else:
            await ctx.reply(f"Setting channel from '{Target_Channel}' to '{channel.name}':'{channel.id}'")
        Target_Channel = channel

        data[guild_id]["channel_id"] = Target_Channel.id
        save_data(data)

        print('set')
    except discord.NotFound:
        await ctx.reply(f"Channel '{channel_id}' does not exist")
        print('not found')
    except discord.Forbidden:
        await ctx.reply(f"Bot cannot access channel '{channel_id}'")
        print('forbidden')
    except discord.HTTPException:
        await ctx.reply(f"Channel '{channel_id}' results in an unknown error")
        print('unknown error')
    except Exception as e:
        await ctx.reply(f"Error: {e}")

@bot.command()
async def currentChannel(ctx):
    if get_channel_id(ctx.guild.id) != None:
        Target_Channel = await bot.fetch_channel(get_channel_id(ctx.guild.id))
    else:
        Target_Channel = None

    if Target_Channel == None:
        await ctx.reply(f"None/Not set")
    else:
        await ctx.reply(f"{Target_Channel.name}: {Target_Channel.id}")

@bot.event
async def on_guild_join(guild):
    #initializes json to default settings
    data = load_data()

    data[str(guild.id)] = {
        "channel_id": None
    }

    save_data(data)

@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")

@bot.event
async def on_message(message):
    if get_channel_id(message.guild.id) != None:
        Target_Channel = await bot.fetch_channel(get_channel_id(message.guild.id))
    else:
        Target_Channel = None

    if message.author == bot.user:
        return
    
    await bot.process_commands(message) # let commands run first

    if message.content.startswith('!'): # prevents commands from reaching code
        return

    if Target_Channel is None or message.channel.id != Target_Channel.id: # only restrict normal messages
        print('not right channel')
        return
    
    URL = grabLink(message.content)

    if "www.instagram.com/reel" in URL:
        infile = None
        outfile = None

        try: 
            with YoutubeDL(ydl_opts_instagram) as ydl:
                info = ydl.extract_info(URL, download = False)

                if info.get("filesize_approx") is not None and info.get("filesize_approx") >= maxVideoSize and videoSizeRestriction:
                    raise Exception(f"Video is larger than {maxVideoSize / (1024*1024)} MB")
                
                if info.get("duration") is not None and info.get("duration") >= maxVideoDuration and videoDurationRestriction:
                    raise Exception(f"Video is larger than {maxVideoDuration} seconds")

                info = ydl.extract_info(URL, download = True) 

                title = info.get("description")

                filename = ydl.prepare_filename(info) #filepath

            infile = Path(filename)

            if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: #size is in bytes, therefore conversion MB->Bytes
                infile = str(filename)
                outfile = str(Path(filename).with_stem(Path(filename).stem + "_compressed"))

                outfile = await vidCompression(maxSize, infile, outfile, message)
                print("compression")
            else:
                outfile = infile
                print("No compression")

            await message.reply(f"**{title}**", file=discord.File(outfile))
        except Exception as e:
            user = await bot.fetch_user(Firedownz_ID)
            await message.reply(f"{user.mention}Download/send failed: `{e}`")

        finally:
            if infile:
                infile = Path(infile)

            if outfile and outfile.exists():
                outfile.unlink(missing_ok=True)
                print("Delete outfile")

            if infile and infile.exists():
                infile.unlink(missing_ok=True)
                print("Deleted infile")
                
    elif any(x in URL for x in ["reddit.com", "redd.it", "i.redd.it", "preview.redd.it"]):
        infile = None
        outfile = None
        temp_files = []
        multi_outfiles = []

        #Notes: yt-dlp cannot handle reddit images cuz some weird shit so use Invoke-WebRequest
        #       Also, this assumes a post does not have both images and videos: Either single video or single image or multiple images
        #       Also, use reddit.json instead of ytdlp. reddit.json exposes a lot of information about the post
        #
        #       Reddit Requires an API for the .json stuff so you gotta apply and wait... bruhhhhhh
        

        try:
            '''
            clean_url = URL.split("?")[0].rstrip("/")
            URL = clean_url + "/.json"

            headers = {"User-Agent": "my-bot/0.1 by u/Firedownz"} #prevents reddit from blocking access

            r = requests.get(URL, headers=headers, timeout=10) #gets the json
            r.raise_for_status() #if error, throws exception

            data = r.json()
            post = data[0]["data"]["children"][0]["data"] #data[0], grabs post, ["data"], blahblah, ifykyk

            if post.get("is_self") == True:
                #Make this do seperate messages for longer posts
                title = post.get("title", "") #get title if not, return blank string
                description = post.get("selftext", "")

                await message.reply(f"**{title}** \n{description}")
            elif post.get("is_video") == True:
                with YoutubeDL(reddit_opts) as ydl:
                    info = ydl.extract_info(URL, download = False)

                    if Restrictions:
                        if info.get("filesize_approx") is not None and info.get("filesize_approx") >= maxVideoSize:
                            raise Exception(f"Video is larger than {maxVideoSize / (1024*1024)} MB")
                        elif info.get("duration") is not None and info.get("duration") >= maxVideoDuration:
                            raise Exception(f"Video is larger than {maxVideoDuration} seconds")

                    info = ydl.extract_info(URL, download = True) 

                    title = info.get("title") or "Reddit Post" #or operator in the context is like, if the first is null us the second
                    description = info.get("description") or ""

                    filename = ydl.prepare_filename(info)
                    infile = Path(filename)

                    temp_files.append(infile)

                    if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: 
                        infile = str(filename)
                        outfile = str(Path(filename).with_stem(Path(filename).stem + "_compressed"))

                        outfile = vidCompression(maxSize, infile, outfile)
                        print("compression")

                        temp_files.append(outfile)
                    else:
                        outfile = infile
                        print("No compression")

                    await message.reply(f"**{title}** \n{description}", file=discord.File(outfile))
            elif post.get("post_hint") == "image":
                imageURL = post.get("url")
                filename = Path(urlparse(imageURL).path).name  # gets "oyy3g24sqtvg1.jpeg"
                infile = Path(filename)
                title = post.get("title", "")
                description = post.get("selftext", "")

                temp_files.append(infile)

                r = requests.get(imageURL, timeout=20)
                r.raise_for_status()

                infile.write_bytes(r.content)

                if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: 
                    infile = filename
                    outfile = Path(filename).with_stem(Path(filename).stem + "_compressed")

                    outfile = imgCompression(maxSize, infile, outfile)
                    print("compression")

                    temp_files.append(outfile)
                else:
                    outfile = infile
                    print("No compression")

                await message.reply(f"**{title}** \n{description}", file=discord.File(outfile))
            elif post.get("is_gallery") == True:
                outfiles = []
                images = []
                title = post.get("title", "")
                description = post.get("selftext", "")

                for item in post["gallery_data"]["items"]:
                        media_id = item["media_id"]
                        meta = post["media_metadata"][media_id]

                        if meta["status"] == "valid":
                            url = meta["s"]["u"]

                            # fix HTML encoding
                            url = url.replace("&amp;", "&")

                            images.append(url)
                for url in images:
                    filename = Path(urlparse(url).path).name 
                    infile = Path(filename)

                    temp_files.append(infile)

                    r = requests.get(url, timeout=20)
                    r.raise_for_status()

                    infile.write_bytes(r.content)

                    if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: 
                        infile = filename
                        outfile = Path(filename).with_stem(Path(filename).stem + "_compressed")

                        outfile = imgCompression(maxSize, infile, outfile)
                        print("compression")

                        temp_files.append(outfile)
                    else:
                        outfile = infile
                        print("No compression")

                    outfiles.append(outfile)
                    discord_files = [discord.File(str(f)) for f in outfiles]

                await message.reply(f"**{title}** \n{description}", files=discord_files)
            '''
            with YoutubeDL(reddit_opts) as ydl:
                info = ydl.extract_info(URL, download = False)

                if info.get("filesize_approx") is not None and info.get("filesize_approx") >= maxVideoSize and videoSizeRestriction:
                    raise Exception(f"Video is larger than {maxVideoSize / (1024*1024)} MB")
                
                if info.get("duration") is not None and info.get("duration") >= maxVideoDuration and videoDurationRestriction:
                    raise Exception(f"Video is larger than {maxVideoDuration} seconds")

                info = ydl.extract_info(URL, download = True) 

                title = info.get("title") or "Reddit Post" #or operator in the context is like, if the first is null us the second
                description = info.get("description") or ""

                filename = ydl.prepare_filename(info)
                infile = Path(filename)

                temp_files.append(infile)

                if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: 
                    infile = str(filename)
                    outfile = str(Path(filename).with_stem(Path(filename).stem + "_compressed"))

                    outfile = await vidCompression(maxSize, infile, outfile, message)
                    print("compression")

                    temp_files.append(outfile)
                else:
                    outfile = infile
                    print("No compression")

                await message.reply(f"**{title}** \n{description}", file=discord.File(outfile))
        except Exception as e:
            user = await bot.fetch_user(Firedownz_ID)
            await message.reply(f"{user.mention}Download/send failed: `{e}`")
        finally:
            for f in temp_files:
                try:
                    if f.exists():
                        f.unlink(missing_ok=True)
                        print(f"Deleted {f}")
                except Exception:
                    pass

    elif "www.tiktok.com" in URL:
        infile = None
        outfile = None

        try: 
            with YoutubeDL(ydl_opts_tiktok) as ydl:
                info = ydl.extract_info(URL, download = False)

                if info.get("filesize_approx") is not None and info.get("filesize_approx") >= maxVideoSize and videoSizeRestriction:
                    raise Exception(f"Video is larger than {maxVideoSize / (1024*1024)} MB")
                
                if info.get("duration") is not None and info.get("duration") >= maxVideoDuration and videoDurationRestriction:
                    raise Exception(f"Video is larger than {maxVideoDuration} seconds")

                info = ydl.extract_info(URL, download = True) 

                title = info.get("description")

                filename = ydl.prepare_filename(info) #filepath

            infile = Path(filename)

            if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: #size is in bytes, therefore conversion MB->Bytes
                infile = str(filename)
                outfile = str(Path(filename).with_stem(Path(filename).stem + "_compressed"))

                outfile = await vidCompression(maxSize, infile, outfile, message)
                print("compression")
            else:
                outfile = infile
                print("No compression")

            await message.reply(f"**{title}**", file=discord.File(outfile))
        except Exception as e:
            user = await bot.fetch_user(Firedownz_ID)
            await message.reply(f"{user.mention}Download/send failed: `{e}`")

        finally:
            if infile:
                infile = Path(infile)

            if outfile and outfile.exists():
                outfile.unlink(missing_ok=True)
                print("Delete outfile")

            if infile and infile.exists():
                infile.unlink(missing_ok=True)
                print("Deleted infile")
    elif any(x in URL for x in ["youtube.com", "youtu.be", "m.youtube.com"]):
        print("Youtube")
        infile = None
        outfile = None

        try: 
            with YoutubeDL(ydl_opts_youtube) as ydl:
                info = ydl.extract_info(URL, download = False)

                if info.get("filesize_approx") is not None and info.get("filesize_approx") >= maxVideoSize and videoSizeRestriction:
                    raise Exception(f"Video is larger than {maxVideoSize / (1024*1024)} MB")
                
                if info.get("duration") is not None and info.get("duration") >= maxVideoDuration and videoDurationRestriction:
                    raise Exception(f"Video is larger than {maxVideoDuration} seconds")

                info = ydl.extract_info(URL, download = True) 

                title = info.get("title")
                description = info.get("description")

                filename = ydl.prepare_filename(info) #filepath

            infile = Path(filename)

            if infile.stat().st_size > (maxSize - 1) * 1024 * 1024: #size is in bytes, therefore conversion MB->Bytes
                infile = str(filename)
                outfile = str(Path(filename).with_stem(Path(filename).stem + "_compressed"))

                outfile = await vidCompression(maxSize, infile, outfile, message)
                print("compression")
            else:
                outfile = infile
                print("No compression")

            await message.reply(f"**{title}**\n{description}", file=discord.File(outfile))
        except Exception as e:
            user = await bot.fetch_user(Firedownz_ID)
            await message.reply(f"{user.mention}Download/send failed: `{e}`")

        finally:
            if infile:
                infile = Path(infile)

            if outfile and outfile.exists():
                outfile.unlink(missing_ok=True)
                print("Deleted outfile")

            if infile and infile.exists():
                infile.unlink(missing_ok=True)
                print("Deleted infile")


bot.run(token, log_handler=handler, log_level=logging.DEBUG)