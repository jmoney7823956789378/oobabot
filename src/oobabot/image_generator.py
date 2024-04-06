# -*- coding: utf-8 -*-
"""
Generates images from Stable Diffusion
and handles user interactions via text commands.
"""
import asyncio
import io
import re
import typing
import discord
from oobabot import fancy_logger
from oobabot import http_client
from oobabot import ooba_client
from oobabot import prompt_generator
from oobabot import sd_client
from oobabot import templates

async def image_task_to_file(image_task: "asyncio.Task[bytes]", image_request: str):
   await image_task
   img_bytes = image_task.result()
   file_of_bytes = io.BytesIO(img_bytes)
   file = discord.File(file_of_bytes)
   file.filename = "photo.png"
   file.description = f"image generated from '{image_request}'"
   return file

class ImageGenerator:
   """
   Generates images from a given prompt, and posts that image as a
   message to a given channel. Handles user interactions via text commands.
   """
   # if a potential image prompt is shorter than this, we will
   # conclude that it is not an image prompt.
   MIN_IMAGE_PROMPT_LENGTH = 3

   def __init__(
      self,
      ooba_client: ooba_client.OobaClient,
      persona_settings: typing.Dict[str, typing.Any],
      prompt_generator: prompt_generator.PromptGenerator,
      sd_settings: typing.Dict[str, typing.Any],
      stable_diffusion_client: sd_client.StableDiffusionClient,
      template_store: templates.TemplateStore,
   ):
      self.ai_name = persona_settings.get("ai_name", "")
      self.ooba_client = ooba_client
      self.image_words = sd_settings.get("image_words", [])
      self.prompt_generator = prompt_generator
      self.stable_diffusion_client = stable_diffusion_client
      self.template_store = template_store
      self.image_patterns = [
         re.compile(
            r"^.*\b" + image_word + r"\b[\s]*(of with)?[\s]*[:]?(.*)$",
            re.IGNORECASE,
         )
         for image_word in self.image_words
      ]

   def on_ready(self):
      """
      Called when the bot is connected to Discord.
      """
      fancy_logger.get().debug(
         "Stable Diffusion: image keywords: %s",
         ", ".join(self.image_words),
      )
   async def generate_image(
      self,
      user_image_keywords: str,
      raw_message: discord.Message,
      response_channel: discord.abc.Messageable,
      ) -> discord.Message:
      """
      Generate an image, post it to the channel,
      and handle user messages for interaction.
      """
      image_prompt = self.maybe_get_image_prompt(raw_message)
      if not image_prompt:
         return

      image_message = await self._generate_image(image_prompt, raw_message, response_channel)
      return image_message

   async def _generate_image(
      self,
      image_prompt: str,
      raw_message: discord.Message,
      response_channel: discord.abc.Messageable,
   ) -> discord.Message:
      is_channel_nsfw = False
      # note: public threads in NSFW channels are not considered here
      if isinstance(raw_message.channel, discord.TextChannel):
         is_channel_nsfw = raw_message.channel.is_nsfw()
      image_task = self.stable_diffusion_client.generate_image(
         image_prompt, is_channel_nsfw=is_channel_nsfw
      )
      try:
         file = await image_task_to_file(image_task, image_prompt)
      except (http_client.OobaHttpClientError, discord.DiscordException) as err:
         fancy_logger.get().error("Could not generate image: %s", err, exc_info=True)
         error_message = self.template_store.format(
            templates.Templates.IMAGE_GENERATION_ERROR,
            {
               templates.TemplateToken.USER_NAME: raw_message.author.display_name,
               templates.TemplateToken.IMAGE_PROMPT: image_prompt,
            },
         )
         return await response_channel.send(error_message, reference=raw_message)
   
      image_message = await response_channel.send(
         content="",
         file=file,
         reference=raw_message,
      )
   
      return image_message
   def maybe_get_image_prompt(
      self, raw_message: discord.Message
   ) -> typing.Optional[str]:
      for image_pattern in self.image_patterns:
         match = image_pattern.search(raw_message.content)
         if match:
            image_prompt = match.group(2).strip()
            if len(image_prompt) < self.MIN_IMAGE_PROMPT_LENGTH:
               continue
            fancy_logger.get().debug("Found image prompt: %s", image_prompt)
            return image_prompt
      return None

   async def handle_reply(
      self,
      reply: discord.Message,
      user: discord.User
   ):
      message = reply
      if user.bot or not message.id:  # Check if the user is a bot or if the message exists
         return

      try:
         if reply.content == "$accept":
            await self.accept_image(message)
         elif reply.content == "$reject":
            await self.delete_image(message)
         elif reply.content == "$retry":
            await self.retry_image(message)
      except discord.DiscordException as e:
         fancy_logger.get().error("Error handling reply: %s", e, exc_info=True)

   async def accept_image(self, message: discord.Message):
      # Edit the message to show that it has been accepted
      await message.edit(content="Image accepted.")

   async def delete_image(self, message: discord.Message):
       # Edit the message to show that it is being deleted
       await message.edit(content="Image rejected. Deleting...")
       await asyncio.sleep(2)  # Provide a short delay before deletion
       await message.delete()

   async def retry_image(self, message: discord.Message):
       # Edit the message to show that a retry is happening
       await message.edit(content="Retrying image generation...")
       await asyncio.sleep(2)  # Provide a short delay before retrying
       await message.delete()
       image_prompt = self.maybe_get_image_prompt(message)
       if image_prompt:
         await self.generate_image(image_prompt, message, message.channel)
