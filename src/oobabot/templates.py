# -*- coding: utf-8 -*-
"""
Templates for text generated by the bot.  There are two types:
 - templates used to generate prompts for the AI
 - templates used to generate UI messages for the user
"""

import enum
import functools
import textwrap
import typing


@functools.total_ordering
class Templates(enum.Enum):
    """
    Enumeration of all different templates.
    """

    COMMAND_LOBOTOMIZE_RESPONSE = "command_lobotomize_response"

    IMAGE_DETACH = "image_detach"
    IMAGE_CONFIRMATION = "image_confirmation"
    IMAGE_GENERATION_ERROR = "image_generation_error"
    IMAGE_UNAUTHORIZED = "image_unauthorized"

    # prompts to the AI to generate text responses
    PROMPT = "prompt"
    EXAMPLE_DIALOGUE = "example_dialogue"
    SECTION_SEPARATOR = "section_separator"
    USER_NAME = "user_name"
    BOT_NAME = "bot_name"
    SYSTEM_SEQUENCE_PREFIX = "system_sequence_prefix"
    SYSTEM_SEQUENCE_SUFFIX = "system_sequence_suffix"
    USER_SEQUENCE_PREFIX = "user_sequence_prefix"
    USER_SEQUENCE_SUFFIX = "user_sequence_suffix"
    BOT_SEQUENCE_PREFIX = "bot_sequence_prefix"
    BOT_SEQUENCE_SUFFIX = "bot_sequence_suffix"
    USER_PROMPT_HISTORY_BLOCK = "user_prompt_history_block"
    BOT_PROMPT_HISTORY_BLOCK = "bot_prompt_history_block"
    PROMPT_IMAGE_COMING = "prompt_image_coming"

    def __str__(self) -> str:
        return self.value

    def __lt__(self, other: "Templates") -> bool:
        return str(self.value) < str(other.value)


class TemplateToken(str, enum.Enum):
    """
    Enumeration of all tokens used in templates.
    Tokens are variable substitutions into the templates.
    """

    AI_NAME = "AI_NAME"
    PERSONA = "PERSONA"
    IMAGE_COMING = "IMAGE_COMING"
    IMAGE_PROMPT = "IMAGE_PROMPT"
    IMAGE_TIMEOUT = "IMAGE_TIMEOUT"
    EXAMPLE_DIALOGUE = "EXAMPLE_DIALOGUE"
    MESSAGE_HISTORY = "MESSAGE_HISTORY"
    SECTION_SEPARATOR = "SECTION_SEPARATOR"
    NAME = "NAME"
    USER_NAME = "USER_NAME"
    BOT_NAME = "BOT_NAME"
    SYSTEM_SEQUENCE_PREFIX = "SYSTEM_SEQUENCE_PREFIX"
    SYSTEM_SEQUENCE_SUFFIX = "SYSTEM_SEQUENCE_SUFFIX"
    USER_SEQUENCE_PREFIX = "USER_SEQUENCE_PREFIX"
    USER_SEQUENCE_SUFFIX = "USER_SEQUENCE_SUFFIX"
    BOT_SEQUENCE_PREFIX = "BOT_SEQUENCE_PREFIX"
    BOT_SEQUENCE_SUFFIX = "BOT_SEQUENCE_SUFFIX"
    MESSAGE = "MESSAGE"
    GUILDNAME = "GUILDNAME"
    CHANNELNAME = "CHANNELNAME"
    CURRENTDATETIME = "CURRENTDATETIME"

    def __str__(self):
        return "{" + self.value + "}"


class TemplateStore:
    """
    Data object storing all template definitions and default values.
    """

    # mapping of template names to tokens allowed in that template
    #  key: template name
    #  value: tuple of (list of tokens, description, is_an_ai_prompt)
    TEMPLATES: typing.Dict[
        Templates, typing.Tuple[typing.List[TemplateToken], str, bool]
    ] = {
        Templates.COMMAND_LOBOTOMIZE_RESPONSE: (
            [
                TemplateToken.AI_NAME,
                TemplateToken.NAME,
            ],
            "Displayed in Discord after a successful /lobotomize command.  "
            + "Both the discord users and the bot AI will see this message.",
            True,
        ),
        Templates.PROMPT: (
            [
                TemplateToken.SYSTEM_SEQUENCE_PREFIX,
                TemplateToken.SYSTEM_SEQUENCE_SUFFIX,
                TemplateToken.AI_NAME,
                TemplateToken.IMAGE_COMING,
                TemplateToken.MESSAGE_HISTORY,
                TemplateToken.SECTION_SEPARATOR,
                TemplateToken.PERSONA,
                TemplateToken.CHANNELNAME,
                TemplateToken.GUILDNAME,
                TemplateToken.CURRENTDATETIME,
            ],
            "The main prompt sent to Oobabooga to generate a response from "
            + "the bot AI.  The AI's reply to this prompt will be sent to "
            + "discord as the bot's response.",
            True,
        ),
        Templates.EXAMPLE_DIALOGUE: (
            [
                TemplateToken.USER_SEQUENCE_PREFIX,
                TemplateToken.USER_SEQUENCE_SUFFIX,
                TemplateToken.BOT_SEQUENCE_PREFIX,
                TemplateToken.BOT_SEQUENCE_SUFFIX,
                TemplateToken.AI_NAME,
            ],
            "The example dialogue inserted directly before the message history. "
            + "This is gradually pushed out as the chat grows beyond the context "
            + "length in the same as as the message history itself.",
            True,
        ),
        Templates.SECTION_SEPARATOR: (
            [
                TemplateToken.SYSTEM_SEQUENCE_PREFIX,
                TemplateToken.SYSTEM_SEQUENCE_SUFFIX,
                TemplateToken.AI_NAME,
                TemplateToken.CURRENTDATETIME,
            ],
            "Separator between different sections, if necessary. For example, to "
            "separate example dialogue from the main chat transcript.",
            True,
        ),
        Templates.USER_NAME: (
            [
                TemplateToken.NAME,
            ],
            "The template that will be applied to user display names, and becomes {USER_NAME}.",
            True,
        ),
        Templates.SYSTEM_SEQUENCE_PREFIX: (
            [],
            "The BOS token that should be inserted before the system block.",
            True,
        ),
        Templates.SYSTEM_SEQUENCE_SUFFIX: (
            [],
            "The EOS token that should be inserted after the system block.",
            True,
        ),
        Templates.USER_SEQUENCE_PREFIX: (
            [],
            "The BOS token that should be inserted before the user message block.",
            True,
        ),
        Templates.USER_SEQUENCE_SUFFIX: (
            [],
            "The EOS token that should be inserted after the user message block.",
            True,
        ),
        Templates.BOT_SEQUENCE_PREFIX: (
            [],
            "The BOS token that should be inserted before the bot message block.",
            True,
        ),
        Templates.BOT_SEQUENCE_SUFFIX: (
            [],
            "The EOS token that should be inserted after the bot message block.",
            True,
        ),
        Templates.BOT_NAME: (
            [
                TemplateToken.NAME,
            ],
            "The template that will be applied to the bot's display name, and becomes {BOT_NAME}.",
            True,
        ),
        Templates.USER_PROMPT_HISTORY_BLOCK: (
            [
                TemplateToken.MESSAGE,
                TemplateToken.USER_NAME,
            ],
            "Part of the AI response-generation prompt, this is used to "
            + "render a single line of chat history for users.  A list of these, "
            + "one for each past user message, will become part of {MESSAGE_HISTORY} "
            + "and inserted into the main prompt",
            True,
        ),
        Templates.BOT_PROMPT_HISTORY_BLOCK: (
            [
                TemplateToken.MESSAGE,
                TemplateToken.BOT_NAME,
            ],
            "Part of the AI response-generation prompt, this is used to "
            + "render a single line of chat history for the bot.  A list of these, "
            + "one for each past bot message, will become part of {MESSAGE_HISTORY} "
            + "and inserted into the main prompt",
            True,
        ),
        Templates.PROMPT_IMAGE_COMING: (
            [
                TemplateToken.AI_NAME,
            ],
            "Part of the AI response-generation prompt, this is used to "
            + "inform the AI that it is in the process of generating an "
            + "image.",
            True,
        ),
        Templates.IMAGE_DETACH: (
            [
                TemplateToken.IMAGE_PROMPT,
                TemplateToken.NAME,
            ],
            "Shown in Discord when the user selects to discard an image "
            + "that Stable Diffusion had generated.",
            True,
        ),
        Templates.IMAGE_CONFIRMATION: (
            [
                TemplateToken.IMAGE_PROMPT,
                TemplateToken.IMAGE_TIMEOUT,
                TemplateToken.NAME,
            ],
            "Shown in Discord when an image is first generated from "
            + "Stable Diffusion.  This should prompt the user to either "
            + "save or discard the image.",
            True,
        ),
        Templates.IMAGE_GENERATION_ERROR: (
            [
                TemplateToken.IMAGE_PROMPT,
                TemplateToken.NAME,
            ],
            "Shown in Discord when the we could not contact Stable Diffusion "
            + "to generate an image.",
            True,
        ),
        Templates.IMAGE_UNAUTHORIZED: (
            [
                TemplateToken.NAME,
            ],
            "Shown in Discord privately to a user if they try to regenerate "
            "an image that was requested by someone else.",
            True,
        ),
    }

    DEFAULT_TEMPLATES: typing.Dict[Templates, str] = {
        Templates.PROMPT: textwrap.dedent(
            """
            You are in a chat room called {CHANNELNAME}/{GUILDNAME} with multiple participants.
            Below is a transcript of recent messages in the conversation.
            Write the next one to three messages that you would send in this
            conversation, from the point of view of the participant named
            {AI_NAME}.

            {PERSONA}

            All responses you write must be from the point of view of
            {AI_NAME}.
            ### Transcript:
            {MESSAGE_HISTORY}
            {IMAGE_COMING}
            """
        ),
        Templates.EXAMPLE_DIALOGUE: textwrap.dedent(
            ""
        ),
        Templates.SECTION_SEPARATOR: textwrap.dedent(
            "***"
        ),
        Templates.USER_NAME: textwrap.dedent(
            """
            {NAME}
            """
        ),
        Templates.BOT_NAME: textwrap.dedent(
            """
            {NAME}
            """
        ),
        Templates.SYSTEM_SEQUENCE_PREFIX: textwrap.dedent(
            ""
        ),
        Templates.SYSTEM_SEQUENCE_SUFFIX: textwrap.dedent(
            ""
        ),
        Templates.USER_SEQUENCE_PREFIX: textwrap.dedent(
            ""
        ),
        Templates.USER_SEQUENCE_SUFFIX: textwrap.dedent(
            ""
        ),
        Templates.BOT_SEQUENCE_PREFIX: textwrap.dedent(
            ""
        ),
        Templates.BOT_SEQUENCE_SUFFIX: textwrap.dedent(
            ""
        ),
        Templates.USER_PROMPT_HISTORY_BLOCK: textwrap.dedent(
            """
            {USER_NAME}: {MESSAGE}
            """
        ),
        Templates.BOT_PROMPT_HISTORY_BLOCK: textwrap.dedent(
            """
            {BOT_NAME}: {MESSAGE}
            """
        ),
        Templates.PROMPT_IMAGE_COMING: textwrap.dedent(
            """
            {AI_NAME}: is currently generating an image, as requested.
            """
        ),
        Templates.IMAGE_DETACH: textwrap.dedent(
            """
            {NAME} asked for an image with the prompt:
                '{IMAGE_PROMPT}'
            ...but couldn't find a suitable one.
            """
        ),
        Templates.IMAGE_CONFIRMATION: textwrap.dedent(
            """
            {NAME}, is this what you wanted?
            If no choice is made, this message will 💣 self-destruct 💣 in 3 minutes.
            """
        ),
        Templates.IMAGE_GENERATION_ERROR: textwrap.dedent(
            """
            Something went wrong generating your image.  Sorry about that!
            """
        ),
        Templates.IMAGE_UNAUTHORIZED: textwrap.dedent(
            """
            Sorry, only {NAME} can press the buttons.
            """
        ),
        Templates.COMMAND_LOBOTOMIZE_RESPONSE: textwrap.dedent(
            """
            Ummmm... what were we talking about?
            """
        ),
    }

    def __init__(self, settings: dict):
        self.templates: typing.Dict[Templates, TemplateMessageFormatter] = {}
        for template, (tokens, purpose, is_ai_prompt) in self.TEMPLATES.items():
            template_name = str(template)
            template_fmt = settings[template_name]
            if template_fmt is None:
                raise ValueError(f"Template {template_name} has no default format")
            self.add_template(template, template_fmt, tokens, purpose, is_ai_prompt)

    def add_template(
        self,
        template_name: Templates,
        format_str: str,
        allowed_tokens: typing.List[TemplateToken],
        purpose: str,
        is_ai_prompt: bool,
    ):
        self.templates[template_name] = TemplateMessageFormatter(
            template_name,
            format_str,
            allowed_tokens,
            purpose,
            is_ai_prompt,
        )

    def format(
        self, template_name: Templates, format_args: typing.Dict[TemplateToken, str]
    ) -> str:
        return self.templates[template_name].format(format_args)


class TemplateMessageFormatter:
    """
    Validates that templates are safe to run string.format() on, and
    runs string.format()
    """

    def __init__(
        self,
        template_name: Templates,
        template: str,
        allowed_tokens: typing.List[TemplateToken],
        purpose: str,
        is_ai_prompt: bool,
    ):
        self._validate_format_string(template_name, template, allowed_tokens)
        self.template_name = template_name
        self.template = template
        self.allowed_tokens = allowed_tokens
        self.purpose = purpose
        self.is_ai_prompt = is_ai_prompt

    def __str__(self):
        return self.template

    def format(self, format_args: typing.Dict[TemplateToken, str]) -> str:
        return self.template.format(**format_args)

    @staticmethod
    def _validate_format_string(
        template_name: Templates,
        format_str: str,
        allowed_args: typing.List[TemplateToken],
    ):
        def find_all_ch(string: str, char: str) -> typing.Generator[int, None, None]:
            # find all indices of ch in s
            for i, letter in enumerate(string):
                if letter == char:
                    yield i

        # raises if fmt_string contains any args not in allowed_args
        allowed_close_brace_indices: typing.Set[int] = set()

        for open_brace_idx in find_all_ch(format_str, "{"):
            for allowed_arg in allowed_args:
                idx_end = open_brace_idx + len(allowed_arg) + 1
                next_substr = format_str[open_brace_idx : idx_end + 1]
                if next_substr == "{" + allowed_arg + "}":
                    allowed_close_brace_indices.add(idx_end)
                    break
            else:
                raise ValueError(
                    f"invalid template: {template_name} contains "
                    + f"an argument not in {allowed_args}"
                )
        for close_brace_idx in find_all_ch(format_str, "}"):
            if close_brace_idx not in allowed_close_brace_indices:
                raise ValueError(
                    f"invalid template: {template_name} contains "
                    + f"an argument not in {allowed_args}"
                )
