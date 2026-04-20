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

reddit_opts = {
    'format': 'bestvideo+bestaudio/best',
    'outtmpl': '%(title)s.%(ext)s',
    'merge_output_format': 'mp4',
    'ffmpeg_location': "C:\\Libraries\\ffmpeg\\bin",
    'restrictfilenames': True,
    'quiet': True,
    'extract_flat': False,
    'force_generic_extractor': False,
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

def checkVideo(info):
    print("Pre-checkVideo")
    ext = info.get("ext")
    print("checkVideo is able to run")

    if ext in ["mp4", "webm", "mkv"]:
        print("Video detected")
        return True
    elif ext in ["jpg", "png", "webp", "jpeg"]:
        print("Image detected")
        return False
    else:
        raise Exception("Unknown File")
    
def imgCompression(maxSizeMB, infile, outfile):
    quality = 95 #Quality is a pillow/image property from 100 to 0 which represents the % quality of an image

    while quality > 10:
        img = Image.open(infile)
        img.save(outfile, quality=quality)

        size = outfile.stat().st_size
        if size <= (maxSizeMB-1) * 1024 * 1024:
            break

        quality -= 5

    return outfile

def redditImageUrlConv(url):
    #https://www.reddit.com/media?url=https%3A%2F%2Fi.redd.it%2Foyy3g24sqtvg1.jpeg -> https://i.redd.it/oyy3g24sqtvg1.jpeg
    result = url.split("%F")[-1]
    redditURL = "https://i.redd.it/" + result

    return redditURL

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
                
    elif any(x in URL for x in ["reddit.com", "redd.it", "i.redd.it", "preview.redd.it"]):
        infile = None
        outfile = None
        temp_files = []
        multi_outfiles = []

        #Notes: yt-dlp cannot handle reddit images cuz some weird shit so use Invoke-WebRequest
        #       Also, this assumes a post does not have both images and videos: Either single video or single image or multiple images
        #       Also, use reddit.json instead of ytdlp. reddit.json exposes a lot of information about the post

        try:
            URL = URL + ".json"
            headers = {"User-Agent": "my-bot/0.1"} #prevents reddit from blocking access

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

    await bot.process_commands(message)

'''
        try: 
            with YoutubeDL(reddit_opts) as ydl:
                print("reddit pre-info")
                info = ydl.extract_info(URL, download = False)
                print("reddit post-info")

                title = info.get("title") or "Reddit Post" #or operator in the context is like, if the first is null us the second
                description = info.get("description") or ""

                #filename = ydl.prepare_filename(info) <- breaks code if it is a playlist

                if info.get("_type") != "playlist":
                    if checkVideo(info):
                        info = ydl.extract_info(URL, download=True)

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
                    else: #else it is an image
                        imageURL = redditImageUrlConv(info.get("url"))
                        filename = Path(urlparse(imageURL).path).name  # gets "oyy3g24sqtvg1.jpeg"
                        infile = Path(filename)

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
                else: #else it is a gallary (only image)
                    print("Hi")

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
'''

    


bot.run(token, log_handler=handler, log_level=logging.DEBUG)