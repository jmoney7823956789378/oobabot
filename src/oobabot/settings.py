
import argparse
import os


class Settings(argparse.ArgumentParser):
    # reads settings from environment variables and command line arguments

    DISCORD_TOKEN_ENV_VAR = 'DISCORD_TOKEN'
    DISCORD_TOKEN = os.environ.get(DISCORD_TOKEN_ENV_VAR, None)

    REQUEST_PREFIX_ENV_VAR = 'OOBABOT_REQUEST_PREFIX'
    REQUEST_PREFIX_ENV = os.environ.get(REQUEST_PREFIX_ENV_VAR, None)

    DEFAULT_WAKEWORDS = ['oobabot']
    DEFAULT_URL = 'ws://localhost:5005'

    def __init__(self):
        self._settings = None

        super().__init__(
            description="Discord bot for oobabooga's text-generation-webui",
            epilog='Also, to authenticate to Discord, you must set the ' +
            'environment variable:\n'
            f"\t{self.DISCORD_TOKEN_ENV_VAR} = <your bot's discord token>"
        )
        self.add_argument(
            '--base-url',
            type=str,
            default=self.DEFAULT_URL,
            help='Base URL for the oobabooga instance.  ' +
            'This should be ws://hostname[:port] for plain websocket connections, ' +
            'or wss://hostname[:port] for websocket connections using TLS'
        ),
        self.add_argument(
            '--wakewords',
            type=str,
            nargs='*',
            default=self.DEFAULT_WAKEWORDS,
            help='One or more words that the bot will listen for.\n ' +
            'The bot will listen in all discord channels can ' +
            'access for one of these words to be mentioned, then reply ' +
            'to any messages it sees with a matching word.  ' +
            'The bot will always reply to @-mentions and ' +
            'direct messages, even if no wakewords are supplied.')
        self.add_argument(
            '--request-prefix',
            type=str,
            default=self.REQUEST_PREFIX_ENV,
            help='This prefix will be added in front of every user-supplied request.  ' +
            "This is useful for setting up a 'character' for the bot to play.  " +
            f'Alternatively, this can be set with the {self.REQUEST_PREFIX_ENV_VAR} ' +
            'environment variable.'
        )
        self.add_argument(
            '--local-repl',
            default=False,
            help='rather than connecting to Discord, instead start a local REPL',
            action='store_true'
        )

    def settings(self):
        if self._settings is None:
            self._settings = {
                self.DISCORD_TOKEN_ENV_VAR: self.DISCORD_TOKEN,
            }
            self._settings.update(self.parse_args().__dict__)

            # either we're using a local REPL, or we're connecting to Discord.
            # assume the user wants to connect to Discord
            if not (self.local_repl or self.DISCORD_TOKEN):
                msg = f"Please set the '{Settings.DISCORD_TOKEN_ENV_VAR}' " + \
                    "environment variable to your bot's discord token."
                # will exit() after printing
                self.error(msg)

        return self._settings

    def __getattr__(self, name):
        return self.settings()[name]

    def __repr__(self) -> str:
        return super().__repr__()
