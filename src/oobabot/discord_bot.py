# Purpose: Discord client for Rosie
#

import asyncio
import io
import random
import re
import time
import typing

import discord

from oobabot.fancy_logging import get_logger
from oobabot.ooba_client import OobaClient
from oobabot.response_stats import AggregateResponseStats
from oobabot.sd_client import StableDiffusionClient
from oobabot.settings import Settings

# strip newlines and replace them with spaces, to make
# it harder for users to trick the UI into injecting
# other instructions, or data that appears to be from
# a different user
FORBIDDEN_CHARACTERS = r"[\n\r\t]"
FORBIDDEN_CHARACTERS_PATTERN = re.compile(FORBIDDEN_CHARACTERS)


class DiscordBotError(Exception):
    pass


async def image_task_to_file(image_task: asyncio.Task[bytes], photo_prompt: str):
    await image_task
    img_bytes = image_task.result()
    file_of_bytes = io.BytesIO(img_bytes)
    file = discord.File(file_of_bytes)
    file.filename = "photo.png"
    file.description = f"image generated from '{photo_prompt}'"
    return file


class StableDiffusionImageView(discord.ui.View):
    """
    A View that displays buttons to regenerate an image
    from Stable Diffusion with a new seed, or to lock
    in the current image.
    """

    def __init__(
        self,
        sd_client: StableDiffusionClient,
        is_channel_nsfw: bool,
        photo_prompt: str,
        requesting_user_id: int,
        requesting_user_name: str,
        settings: Settings,
    ):
        super().__init__(timeout=120.0)

        self.settings = settings

        # only the user who requested generation of the image
        # can have it replaced
        self.requesting_user_id = requesting_user_id
        self.requesting_user_name = requesting_user_name
        self.photo_prompt = photo_prompt
        self.photo_accepted = False

        #####################################################
        # "Try Again" button
        #
        btn_try_again = discord.ui.Button(
            label="Try Again",
            style=discord.ButtonStyle.blurple,
            row=1,
        )
        self.image_message = None

        async def on_try_again(interaction: discord.Interaction):
            result = await self.diy_interaction_check(interaction)
            if not result:
                # unauthorized user
                return

            # generate a new image
            regen_task = sd_client.generate_image(photo_prompt, is_channel_nsfw)
            regen_file = await image_task_to_file(regen_task, photo_prompt)
            await interaction.response.defer()

            await self.get_image_message().edit(attachments=[regen_file])

        btn_try_again.callback = on_try_again

        #####################################################
        # "Accept" button
        #
        btn_lock_in = discord.ui.Button(
            label="Accept",
            style=discord.ButtonStyle.success,
            row=1,
        )

        async def on_lock_in(interaction: discord.Interaction):
            result = await self.diy_interaction_check(interaction)
            if not result:
                # unauthorized user
                return
            await interaction.response.defer()
            await self.detach_view_keep_img()

        btn_lock_in.callback = on_lock_in

        #####################################################
        # "Delete" button
        #
        btn_delete = discord.ui.Button(
            label="Delete",
            style=discord.ButtonStyle.danger,
            row=1,
        )

        async def on_delete(interaction: discord.Interaction):
            result = await self.diy_interaction_check(interaction)
            if not result:
                # unauthorized user
                return
            await interaction.response.defer()
            await self.delete_image()

        btn_delete.callback = on_delete

        super().add_item(btn_try_again).add_item(btn_lock_in).add_item(btn_delete)

    def set_image_message(self, image_message: discord.Message):
        self.image_message = image_message

    def get_image_message(self) -> discord.Message:
        if self.image_message is None:
            raise ValueError("image_message is None")
        return self.image_message

    async def delete_image(self):
        await self.detach_view_delete_img(self.get_detach_message())

    async def detach_view_delete_img(self, detach_msg: str):
        await self.get_image_message().edit(
            content=detach_msg,
            view=None,
            attachments=[],
        )

    async def detach_view_keep_img(self):
        self.photo_accepted = True
        await self.get_image_message().edit(
            content=None,
            view=None,
        )

    async def on_timeout(self):
        if not self.photo_accepted:
            await self.delete_image()

    async def diy_interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Only allow the requesting user to interact with this view.
        """
        if interaction.user.id == self.requesting_user_id:
            return True
        await interaction.response.send_message(
            f"Sorry, only {self.requesting_user_name} can press the buttons.",
            ephemeral=True,
        )
        return False

    def get_image_message_text(self) -> str:
        return self._get_message(Settings.TEMPLATE_STABLE_DIFFUSION_IMAGE_MESSAGE)

    def get_detach_message(self) -> str:
        return self._get_message(Settings.TEMPLATE_STABLE_DIFFUSION_DETACH_MESSAGE)

    def _get_message(self, message_type: str) -> str:
        return self.settings.template_store.format(
            message_type,
            DISCORD_USER_NAME=self.requesting_user_name,
            PHOTO_PROMPT=self.photo_prompt,
        )


def sanitize_string(raw_string: str) -> str:
    """
    Filter out any characters that are not commonly on a
    US-English keyboard
    """
    return FORBIDDEN_CHARACTERS_PATTERN.sub(" ", raw_string)


def sanitize_message(raw_message: discord.Message) -> dict[str, str]:
    author = sanitize_string(raw_message.author.name)

    raw_guild = raw_message.guild
    if raw_guild:
        raw_guild_name = raw_guild.name
    else:
        raw_guild_name = "DM"

    return {
        "author": author,
        "message_text": sanitize_string(raw_message.content).strip(),
        "server": sanitize_string(raw_guild_name),
    }


class PromptGenerator:
    """
    Purpose: generate a prompt_prefix for the AI to use, given
    the message history and persona.
    """

    REQUIRED_HISTORY_SIZE_CHARS = (
        Settings.DISCORD_HISTORY_LINES_TO_SUPPLY
        * Settings.DISCORD_HISTORY_EST_CHARACTERS_PER_LINE
    )

    def __init__(self, ai_name: str, persona: str, settings: Settings):
        self.ai_name = ai_name
        self.persona = persona
        self.settings = settings

        self.init_photo_request()
        self.init_history_available_chars()

    def init_photo_request(self) -> None:
        self.photo_request_made = self.settings.template_store.format(
            Settings.DISCORD_PROMPT_PHOTO_COMING_TEMPLATE,
            AI_NAME=self.ai_name,
        )

    async def generate_history(
        self,
        ai_user_id: int,
        message_history: typing.AsyncIterator[discord.Message],
        stop_before_message_id: int | None,
    ) -> str:
        # add on more history, but only if we have room
        # if we don't have room, we'll just truncate the history
        # by discarding the oldest messages first
        # this is s
        # it will understand before ignore
        #
        prompt_len_remaining = self.max_history_chars

        # history_lines is newest first, so figure out
        # how many we can take, then append them in
        # reverse order
        history_lines = []

        async for raw_message in message_history:
            # if we've hit the throttle message, stop and don't add any
            # more history
            if stop_before_message_id and raw_message.id == stop_before_message_id:
                break

            clean_message = sanitize_message(raw_message)

            author = clean_message["author"]
            if raw_message.author.id == ai_user_id:
                author = self.ai_name
                # hack: if the message includes the text
                # "tried to make an image with the prompt",
                # ignore it
                if (
                    "tried to make an image with the prompt"
                    in clean_message["message_text"]
                ):
                    continue

            if not clean_message["message_text"]:
                continue

            line = self.settings.template_store.format(
                Settings.DISCORD_PROMPT_HISTORY_LINE_TEMPLATE,
                DISCORD_USER_NAME=author,
                DISCORD_USER_MESSAGE=clean_message["message_text"],
            )

            if len(line) > prompt_len_remaining:
                num_discarded_lines = Settings.DISCORD_HISTORY_LINES_TO_SUPPLY - len(
                    history_lines
                )
                get_logger().warn(
                    "ran out of prompt space, discarding "
                    + f"{num_discarded_lines} lines "
                    + "of chat history"
                )
                break

            prompt_len_remaining -= len(line)
            history_lines.append(line)

        history_lines.reverse()
        return "".join(history_lines)

    def fill_in_prompt_template(
        self,
        message_history: str | None = None,
        photo_request: str | None = None,
    ) -> str:
        """
        Given a template string, fill in the kwargs
        """
        return self.settings.template_store.format(
            Settings.DISCORD_PROMPT_TEMPLATE,
            AI_NAME=self.ai_name,
            PERSONA=self.persona,
            MESSAGE_HISTORY=message_history or "",
            PHOTO_REQUEST=photo_request or "",
        )

    def init_history_available_chars(self) -> None:
        # the number of chars we have available for history
        # is:
        #   number of chars in token space (estimated)
        #   minus the number of chars in the prompt
        #     - without any history
        #     - but with the photo request
        #
        est_chars_in_token_space = (
            Settings.OOBABOT_MAX_AI_TOKEN_SPACE
            * Settings.OOBABOT_EST_CHARACTERS_PER_TOKEN
        )
        possible_prompt = self.fill_in_prompt_template(
            message_history="",
            photo_request=self.photo_request_made,
        )
        max_history_chars = est_chars_in_token_space - len(possible_prompt)
        if max_history_chars < self.REQUIRED_HISTORY_SIZE_CHARS:
            raise ValueError(
                "AI token space is too small for prompt_prefix and history "
                + "by an estimated "
                + f"{self.REQUIRED_HISTORY_SIZE_CHARS - self.max_history_chars}"
                + " characters.  You may lose history context.  You can save space"
                + " by shortening the persona or reducing the requested number of"
                + " lines of history."
            )
        self.max_history_chars = max_history_chars

    async def generate(
        self,
        ai_user_id: int,
        message_history: typing.AsyncIterator[discord.Message],
        photo_requested: bool,
        throttle_message_id: int | None,
    ) -> str:
        """
        Generates a prompt_prefix for the AI to use based on the message.
        """
        prompt = self.fill_in_prompt_template(
            message_history=await self.generate_history(
                ai_user_id, message_history, throttle_message_id
            ),
            photo_request=self.photo_request_made if photo_requested else "",
        )
        return prompt


class DiscordBot(discord.Client):
    # seconds after which we'll lazily purge a channel
    # from channel_last_direct_response

    def __init__(
        self,
        ooba_client: OobaClient,
        settings: Settings,
        stable_diffusion_client: StableDiffusionClient | None = None,
    ):
        self.ooba_client = ooba_client

        self.ai_name = settings.ai_name
        self.persona = settings.persona
        self.ai_user_id = -1
        self.wakewords = settings.wakewords
        self.log_all_the_things = settings.log_all_the_things
        self.ignore_dms = settings.ignore_dms
        self.settings = settings

        # a list of timestamps in which we last posted to a channel
        self.channel_last_direct_response = {}

        self.discard_last_response_after_seconds = max(
            time for time, _ in Settings.DISCORD_TIME_VS_RESPONSE_CHANCE
        )

        # attempts to detect when the bot is stuck in a loop, and will try to
        # stop it by limiting the history it can see
        self.repetition_tracker = RepetitionTracker()

        self.average_stats = AggregateResponseStats(ooba_client)
        self.prompt_prefix_generator = PromptGenerator(
            self.ai_name, self.persona, settings
        )

        # match messages that include any `wakeword`, but not as part of
        # another word
        self.wakeword_patterns = [
            re.compile(rf"\b{wakeword}\b", re.IGNORECASE) for wakeword in self.wakewords
        ]

        photowords = ["drawing", "photo", "pic", "picture", "image", "sketch"]
        self.photo_patterns = [
            re.compile(
                r"^.*\b" + photoword + r"\b[\s]*(of|with)?[\s]*[:]?(.*)$", re.IGNORECASE
            )
            for photoword in photowords
        ]

        self.stable_diffusion_client = stable_diffusion_client

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)

    async def on_ready(self) -> None:
        guilds = self.guilds
        num_guilds = len(guilds)
        num_channels = sum([len(guild.channels) for guild in guilds])

        if self.user:
            self.ai_user_id = self.user.id
            user_id_str = str(self.ai_user_id)
        else:
            user_id_str = "<unknown>"

        get_logger().info(f"Connected to discord as {self.user} (ID: {user_id_str})")
        get_logger().debug(
            f"monitoring {num_channels} channels across " + f"{num_guilds} server(s)"
        )
        if self.ignore_dms:
            get_logger().debug("Ignoring DMs")
        else:
            get_logger().debug("listening to DMs")

        get_logger().debug(f"AI name: {self.ai_name}")
        get_logger().debug(f"AI persona: {self.persona}")

        str_wakewords = ", ".join(self.wakewords) if self.wakewords else "<none>"
        get_logger().debug(f"wakewords: {str_wakewords}")

    async def start(self) -> None:
        # todo: join these at a higher level?
        if self.stable_diffusion_client is not None:
            async with self.stable_diffusion_client:
                await self._inner_start()
        else:
            await self._inner_start()

    async def _inner_start(self):
        async with self.ooba_client:
            try:
                await super().start(self.settings.DISCORD_TOKEN)
            except discord.LoginFailure:
                get_logger().error("Failed to log in to discord.  Check your token?")
            return

    def should_send_direct_response(self, message: discord.Message) -> bool:
        """
        Returns true if the bot was directly addressed in the message,
        and will respond.
        """

        # reply to all private messages
        if discord.ChannelType.private == message.channel.type:
            if self.ignore_dms:
                return False
            return True

        # reply to all messages that include a wakeword
        for wakeword_pattern in self.wakeword_patterns:
            if wakeword_pattern.search(message.content):
                return True

        # reply to all messages in which we're @-mentioned
        if self.user and self.user.id in [m.id for m in message.mentions]:
            return True

        return False

    def should_send_unsolicited_response(self, message: discord.Message) -> bool:
        # if we haven't posted to this channel recently, don't reply
        if message.channel.id not in self.channel_last_direct_response:
            return False

        time_since_last_send = (
            message.created_at.timestamp()
            - self.channel_last_direct_response[message.channel.id]
        )

        # return a base chance that we'll respond to a message that wasn't
        # addressed to us, based on the table in TIME_VS_RESPONSE_CHANCE.
        # other factors might increase this chance.
        response_chance = 0.0
        for duration, chance in Settings.DISCORD_TIME_VS_RESPONSE_CHANCE:
            if time_since_last_send < duration:
                response_chance = chance
                break

        # if the new message ends with a question mark, we'll respond
        if message.content.endswith("?"):
            response_chance += Settings.DISCORD_INTERROBANG_BONUS

        # if the new message ends with an exclamation point, we'll respond
        if message.content.endswith("!"):
            response_chance += Settings.DISCORD_INTERROBANG_BONUS

        if random.random() < response_chance:
            return True

        return False

    def purge_outdated_response_times(self) -> None:
        oldest_time_to_keep = time.time() - self.discard_last_response_after_seconds
        self.channel_last_direct_response = {
            channel_id: response_time
            for channel_id, response_time in self.channel_last_direct_response.items()
            if response_time >= oldest_time_to_keep
        }

    def should_reply_to_message(self, message: discord.Message) -> bool:
        # ignore messages from other bots, out of fear of infinite loops,
        # as well as world domination
        if message.author.bot:
            return False

        # we do not want the bot to reply to itself.  This is redundant
        # with the previous check, except it won't be if someone decides
        # to run this under their own user token, rather than a proper
        # bot token.
        if self.user and message.author.id == self.user.id:
            return False

        if self.should_send_direct_response(message):
            # store the timestamp of this response in channel_last_direct_response
            if message.channel.id:
                self.channel_last_direct_response[message.channel.id] = time.time()
            return True

        ################################################################
        # end of "solicited" response checks.  From here on out, we're
        # only responding to messages that weren't directly addressed
        # to us.

        # if we're not at-mentioned but others are, don't reply
        if message.mentions:
            return False

        # if message is empty, don't reply.  This can happen if someone
        # posts an image or an attachment without a comment.
        if not message.content.strip():
            return False

        # if we've posted recently in this channel, there are a few
        # other reasons we may respond.  But if we haven't, just
        # ignore the message.

        # purge any channels that we haven't posted to in a while
        self.purge_outdated_response_times()

        # we're now in the set of spaces where we have a chance of
        # responding to a message that wasn't directly addressed to us

        if self.should_send_unsolicited_response(message):
            return True

        # ignore anything else
        return False

    def log_stats(self) -> None:
        self.average_stats.write_stat_summary_to_log()

    def make_photo_prompt_from_message(
        self, raw_message: discord.Message
    ) -> str | None:
        for photo_pattern in self.photo_patterns:
            sanitized_content = sanitize_string(raw_message.content)
            match = photo_pattern.search(sanitized_content)
            if match:
                return match.group(2)

    async def request_picture_generation(
        self, photo_prompt: str, raw_message: discord.Message
    ) -> bool:
        async def send_image(stable_diffusion_client: StableDiffusionClient) -> None:
            is_channel_nsfw = False
            if isinstance(raw_message.channel, discord.TextChannel):
                is_channel_nsfw = raw_message.channel.is_nsfw()
            image_task = stable_diffusion_client.generate_image(
                photo_prompt, is_channel_nsfw=is_channel_nsfw
            )
            file = await image_task_to_file(image_task, photo_prompt)

            regen_view = StableDiffusionImageView(
                stable_diffusion_client,
                is_channel_nsfw,
                photo_prompt=photo_prompt,
                requesting_user_id=raw_message.author.id,
                requesting_user_name=raw_message.author.name,
                settings=self.settings,
            )

            image_message = await raw_message.channel.send(
                content=regen_view.get_image_message_text(),
                reference=raw_message,
                file=file,
                view=regen_view,
            )
            regen_view.image_message = image_message

        async def wrapped_send_image(
            stable_diffusion_client: StableDiffusionClient,
        ) -> None:
            try:
                await send_image(stable_diffusion_client)
            except Exception as e:
                get_logger().error(f"Exception while sending image: {e}", exc_info=True)

        if self.stable_diffusion_client is None:
            return False
        asyncio.create_task(wrapped_send_image(self.stable_diffusion_client))
        return True

    async def on_message(self, raw_message: discord.Message) -> None:
        try:
            if not self.should_reply_to_message(raw_message):
                return
        except Exception as e:
            get_logger().error(f"Exception while checking message: {e}", exc_info=True)
            return
        try:
            async with raw_message.channel.typing():
                photo_requested = False
                if self.stable_diffusion_client is not None:
                    photo_prompt = self.make_photo_prompt_from_message(raw_message)
                    if photo_prompt is not None:
                        photo_requested = await self.request_picture_generation(
                            photo_prompt, raw_message
                        )

                await self.send_response(raw_message, photo_requested)
        except Exception as e:
            get_logger().error(f"Exception while sending response: {e}", exc_info=True)

    async def send_response(
        self, raw_message: discord.Message, photo_requested: bool
    ) -> None:
        clean_message = sanitize_message(raw_message)
        author = clean_message["author"]
        server = clean_message["server"]
        get_logger().debug(f"Request from {author} in server [{server}]")

        recent_messages = raw_message.channel.history(
            limit=Settings.DISCORD_HISTORY_LINES_TO_SUPPLY
        )

        repeated_id = self.repetition_tracker.get_throttle_message_id(
            raw_message.channel.id
        )

        prompt_prefix = await self.prompt_prefix_generator.generate(
            self.ai_user_id, recent_messages, photo_requested, repeated_id
        )

        response_stats = self.average_stats.log_request_arrived(prompt_prefix)
        if self.log_all_the_things:
            print("prompt_prefix:\n----------\n")
            print(prompt_prefix)
            print("Response:\n----------\n")

        try:
            async for sentence in self.ooba_client.request_by_sentence(prompt_prefix):
                if self.log_all_the_things:
                    print(sentence)

                # if the AI gives itself a second line, just ignore
                # the line instruction and continue
                if f"{self.ai_name} says:" == sentence:
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, continuing'
                    )
                    continue

                # hack: abort response if it looks like the AI is
                # continuing the conversation as someone else
                if sentence.endswith(" says:"):
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, aborting'
                    )
                    break

                response_message = await raw_message.channel.send(sentence)
                self.repetition_tracker.log_message(
                    raw_message.channel.id, response_message
                )

                response_stats.log_response_part()

        except Exception as err:
            get_logger().error(f"Error: {str(err)}")
            self.average_stats.log_response_failure()
            return

        response_stats.write_to_log(f"Response to {author} done!  ")
        self.average_stats.log_response_success(response_stats)


class RepetitionTracker:
    # how many times the bot can repeat the same thing before we
    # throttle history

    def __init__(
        self, repetition_threshold: int = Settings.DISCORD_REPETITION_THRESHOLD
    ) -> None:
        self.repetition_threshold = repetition_threshold

        # stores a map of channel_id ->
        #   (last_message, throttle_message_id, repetion_count)

        self.repetition_count: typing.Dict[int, typing.Tuple[str, int, int]] = {}

    def get_throttle_message_id(self, channel_id: int) -> int | None:
        """
        Returns the message ID of the last message that should be throttled, or None
        if no throttling is needed
        """
        _, throttle_message_id, _ = self.repetition_count.get(
            channel_id, (None, None, None)
        )
        return throttle_message_id

    def log_message(self, channel_id: int, response_message: discord.Message) -> None:
        """
        Logs a message sent by the bot, to be used for repetition tracking
        """
        # make string into canonical form
        sentence = self.make_canonical(response_message.content)

        last_message, throttle_message_id, repetition_count = self.repetition_count.get(
            channel_id, ("", 0, 0)
        )
        if last_message == sentence:
            repetition_count += 1
        else:
            repetition_count = 0

        get_logger().debug(
            f"Repetition count for channel {channel_id} is {repetition_count}"
        )

        if self.should_throttle(repetition_count):
            get_logger().warning(
                "Repetition found, will throttle history for channel "
                + f"{channel_id} in next request"
            )
            throttle_message_id = response_message.id

        self.repetition_count[channel_id] = (
            sentence,
            throttle_message_id,
            repetition_count,
        )

    def should_throttle(self, repetition_count: int) -> bool:
        """
        Returns whether the bot should throttle history for a given repetition count
        """
        return repetition_count >= self.repetition_threshold

    def make_canonical(self, content: str) -> str:
        return content.strip().lower()
