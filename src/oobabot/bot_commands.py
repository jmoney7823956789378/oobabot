# -*- coding: utf-8 -*-
"""
Implementation of the bot's slash commands.
"""
import typing

import discord

from oobabot import audio_commands
from oobabot import decide_to_respond
from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import ooba_client
from oobabot import persona
from oobabot import prompt_generator
from oobabot import repetition_tracker
from oobabot import templates


class BotCommands:
    """
    Implementation of the bot's slash commands.
    """

    def __init__(
        self,
        decide_to_respond: decide_to_respond.DecideToRespond,
        repetition_tracker: repetition_tracker.RepetitionTracker,
        persona: persona.Persona,
        discord_settings: dict,
        template_store: templates.TemplateStore,
        ooba_client: ooba_client.OobaClient,
        prompt_generator: prompt_generator.PromptGenerator,
    ):
        self.decide_to_respond = decide_to_respond
        self.repetition_tracker = repetition_tracker
        self.persona = persona
        self.include_lobotomize_response = discord_settings["include_lobotomize_response"]
        self.reply_in_thread = discord_settings["reply_in_thread"]
        self.template_store = template_store
        self.ooba_client = ooba_client

        (
            self.discrivener_location,
            self.discrivener_model_location,
        ) = discord_utils.validate_discrivener_locations(
            discord_settings["discrivener_location"],
            discord_settings["discrivener_model_location"],
        )
        self.speak_voice_replies = discord_settings["speak_voice_replies"]
        self.post_voice_replies = discord_settings["post_voice_replies"]

        if (
            discord_settings["discrivener_location"]
            and self.discrivener_location is None
        ):
            fancy_logger.get().warning(
                "Audio disabled because executable at discrivener_location "
                + "could not be found: %s",
                discord_settings["discrivener_location"],
            )

        if (
            discord_settings["discrivener_model_location"]
            and self.discrivener_model_location is None
        ):
            fancy_logger.get().warning(
                "Audio disable because the discrivener_model_location "
                + "could not be found: %s",
                discord_settings["discrivener_model_location"],
            )

        if self.discrivener_location is None or self.discrivener_model_location is None:
            self.audio_commands = None
        else:
            self.audio_commands = audio_commands.AudioCommands(
                persona,
                ooba_client,
                prompt_generator,
                self.discrivener_location,
                self.discrivener_model_location,
                self.speak_voice_replies,
                self.post_voice_replies,
            )

    async def on_ready(self, client: discord.Client):
        """
        Register commands with Discord.
        """

        async def get_messageable(
            interaction: discord.Interaction,
        ) -> (
            typing.Optional[
                typing.Union[
                    discord.TextChannel,
                    discord.Thread,
                    discord.DMChannel,
                    discord.GroupChannel,
                ]
            ]
        ):
            if interaction.channel_id is not None:
                # find the current message in this channel
                # tell the Repetition Tracker to hide messages
                # before this message
                channel = await interaction.client.fetch_channel(interaction.channel_id)
                if channel is not None:
                    if isinstance(channel, discord.TextChannel):
                        return channel
                    if isinstance(channel, discord.Thread):
                        return channel
                    if isinstance(channel, discord.DMChannel):
                        return channel
                    if isinstance(channel, discord.GroupChannel):
                        return channel
            return None


        @discord.app_commands.command(
            name="stop",
            description=f"Force {self.persona.ai_name} to stop typing the current message.",
        )
        async def stop(interaction: discord.Interaction):
            if interaction.channel_id is None:
                await discord_utils.fail_interaction(interaction)
                return
            response = await self.ooba_client.stop()
            str_response = response if response is not None else "No response from server."
            await interaction.response.send_message(str_response)
            return

        @discord.app_commands.command(
            name="poke",
            description=f"Prompt {self.persona.ai_name} to write a response to the last message, if posted by a user."
        )
        async def poke(interaction: discord.Interaction):
            channel = await get_messageable(interaction)
            if channel is None:
                await discord_utils.fail_interaction(interaction)
                return

            channel_name = discord_utils.get_channel_name(channel)
            fancy_logger.get().debug(
                "/%s called by user '%s' in channel #%s",
                interaction.command.name,
                interaction.user.name,
                channel_name,
            )

            async for message in channel.history(limit=1):
                if message.author.id == client.user.id:
                    return await discord_utils.fail_interaction(
                    interaction,
                    "I can't reply to my own messages.",
                )
                await interaction.response.defer(ephemeral=True, thinking=False)
                client.dispatch("message", message)
                return await interaction.delete_original_response()

        @discord.app_commands.command(
            name="regenerate",
            description=f"Delete and regenerate {self.persona.ai_name}'s last message."
        )
        async def regenerate(interaction: discord.Interaction):
            channel = await get_messageable(interaction)
            if channel is None:
                await discord_utils.fail_interaction(interaction)
                return

            channel_name = discord_utils.get_channel_name(channel)
            fancy_logger.get().debug(
                "/%s called by user '%s' in channel #%s",
                interaction.command.name,
                interaction.user.name,
                channel_name,
            )

            history_limit = 100
            bot_last_message = None
            user_last_message = None

            async for message in channel.history(limit=history_limit):
                if bot_last_message and message.author.id != client.user.id:
                    user_last_message = message
                    break
                if message.author.id == client.user.id and not bot_last_message:
                    bot_last_message = message

            if bot_last_message and user_last_message:
                await interaction.response.defer(ephemeral=True, thinking=False)
                await bot_last_message.delete()
                client.dispatch("message", user_last_message)
                await interaction.delete_original_response()
            else:
                await discord_utils.fail_interaction(
                    interaction,
                    "Can't find my last message in the last {history_limit} messages."
                )

        @discord.app_commands.command(
            name="say",
            description=f"Force {self.persona.ai_name} to say the provided message.",
        )
        @discord.app_commands.rename(text_to_send="message")
        @discord.app_commands.describe(
            text_to_send=f"Message to force {self.persona.ai_name} to say."
        )
        async def say(interaction: discord.Interaction, text_to_send: str):
            if interaction.channel_id is None:
                await discord_utils.fail_interaction(interaction)
                return

            # if reply_in_thread is True, we don't want our bot to
            # speak in guild channels, only threads and private messages
            if self.reply_in_thread:
                channel = await get_messageable(interaction)
                if channel is None or isinstance(channel, discord.TextChannel):
                    await discord_utils.fail_interaction(
                        interaction,
                        f"{self.persona.ai_name} may only speak in threads"
                    )
                    return

            channel_name = discord_utils.get_channel_name(channel)
            fancy_logger.get().debug(
                "/%s called by user '%s' in channel #%s",
                interaction.command.name,
                interaction.user.name,
                channel_name,
            )
            # this will cause the bot to monitor the channel
            # and consider unsolicited responses
            self.decide_to_respond.log_mention(
                channel_id=interaction.channel_id,
                send_timestamp=interaction.created_at.timestamp(),
            )
            await interaction.response.send_message(
                text_to_send,
                suppress_embeds=True,
            )

        @discord.app_commands.command(
            name="lobotomize",
            description=f"Erase {self.persona.ai_name}'s memory of any message "
            + "before now in this channel.",
        )
        async def lobotomize(interaction: discord.Interaction):
            channel = await get_messageable(interaction)
            if channel is None:
                await discord_utils.fail_interaction(interaction)
                return

            channel_name = discord_utils.get_channel_name(channel)
            fancy_logger.get().debug(
                "/%s called by user '%s' in channel #%s",
                interaction.command.name,
                interaction.user.name,
                channel_name,
            )

            response = self.template_store.format(
                template_name=templates.Templates.COMMAND_LOBOTOMIZE_RESPONSE,
                format_args={
                    templates.TemplateToken.AI_NAME: self.persona.ai_name,
                    templates.TemplateToken.NAME: interaction.user.name,
                },
            )
            await interaction.response.send_message(
                response,
                silent=True,
                suppress_embeds=True,
            )
            # find the current message in this channel or the
            # message before that if we're including our response.
            # tell the Repetition Tracker to hide messages
            # before this message
            history_limit = 2 if self.include_lobotomize_response else 1
            if not self.include_lobotomize_response:
                fancy_logger.get().debug("Excluding bot response from context.")
            async for message in channel.history(limit=history_limit):
                self.repetition_tracker.hide_messages_before(
                    channel_id=channel.id,
                    message_id=message.id,
                )

        fancy_logger.get().debug(
            "Registering commands, sometimes this takes a while..."
        )

        tree = discord.app_commands.CommandTree(client)
        tree.add_command(lobotomize)
        tree.add_command(say)
        tree.add_command(stop)
        tree.add_command(poke)
        tree.add_command(regenerate)

        if self.audio_commands is not None:
            self.audio_commands.add_commands(tree)

        commands = await tree.sync(guild=None)
        for command in commands:
            fancy_logger.get().info(
                "Registered command: %s: %s", command.name, command.description
            )
