import discord 
from discord.ext import commands
import logging
from dotenv import load_dotenv 
import os

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

