import os
import shutil

from hummingbot.client.config.config_var import ConfigVar
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.client.config.config_helpers import (
    get_strategy_config_map,
    parse_cvar_value,
    default_strategy_file_path,
    save_to_yml,
    get_strategy_template_path,
    format_config_file_name,
    parse_config_default_to_text
)
from hummingbot.client.settings import CONF_FILE_PATH, required_exchanges
from hummingbot.client.config.global_config_map import global_config_map
from hummingbot.client.config.security import Security
from hummingbot.client.config.config_validators import validate_strategy
from hummingbot.client.ui.completer import load_completer
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from hummingbot.client.hummingbot_application import HummingbotApplication


class CreateCommand:
    def create(self,  # type: HummingbotApplication
               file_name):
        if file_name is not None:
            file_name = format_config_file_name(file_name)
            if os.path.exists(os.path.join(CONF_FILE_PATH, file_name)):
                self._notify(f"{file_name} already exists.")
                return

        safe_ensure_future(self.prompt_for_configuration(file_name))

    async def prompt_for_configuration(self,  # type: HummingbotApplication
                                       file_name):
        self.app.clear_input()
        self.placeholder_mode = True
        self.app.hide_input = True
        required_exchanges.clear()

        strategy_config = ConfigVar(key="strategy",
                                    prompt="What is your market making strategy? >>> ",
                                    validator=validate_strategy)
        await self.prompt_a_config(strategy_config)
        if self.app.to_stop_config:
            self.app.to_stop_config = False
            return
        strategy = strategy_config.value
        config_map = get_strategy_config_map(strategy)
        self._notify(f"Please see https://docs.hummingbot.io/strategies/{strategy.replace('_', '-')}/ "
                     f"while setting up these below configuration.")
        # assign default values and reset those not required
        for config in config_map.values():
            if config.required:
                config.value = config.default
            else:
                config.value = None
        for config in config_map.values():
            if config.prompt_on_new and config.required:
                if not self.app.to_stop_config:
                    await self.prompt_a_config(config)
                else:
                    self.app.to_stop_config = False
                    return
            else:
                config.value = config.default

        # catch a last key binding to stop config, if any
        if self.app.to_stop_config:
            self.app.to_stop_config = False
            return

        if file_name is None:
            file_name = await self.prompt_new_file_name(strategy)
            if self.app.to_stop_config:
                self.app.to_stop_config = False
                self.app.set_text("")
                return
        self.app.change_prompt(prompt=">>> ")
        strategy_path = os.path.join(CONF_FILE_PATH, file_name)
        template = get_strategy_template_path(strategy)
        shutil.copy(template, strategy_path)
        save_to_yml(strategy_path, config_map)
        self.strategy_file_name = file_name
        self.strategy_name = strategy
        # Reload completer here otherwise the new file will not appear
        self.app.input_field.completer = load_completer(self)
        self._notify(f"A new config file {self.strategy_file_name} created.")
        self.placeholder_mode = False
        self.app.hide_input = False
        if await self.status_check_all():
            self._notify("\nEnter \"start\" to start market making.")
            self.app.set_text("start")

    async def prompt_a_config(self,  # type: HummingbotApplication
                              config: ConfigVar,
                              input_value=None,
                              assign_default=True):
        if input_value is None:
            if assign_default:
                self.app.set_text(parse_config_default_to_text(config))
            input_value = await self.app.prompt(prompt=config.prompt, is_password=config.is_secure)

        if self.app.to_stop_config:
            return
        err_msg = config.validate(input_value)
        if err_msg is not None:
            self._notify(err_msg)
            await self.prompt_a_config(config)
        else:
            config.value = parse_cvar_value(config, input_value)

    async def prompt_new_file_name(self,  # type: HummingbotApplication
                                   strategy):
        file_name = default_strategy_file_path(strategy)
        self.app.set_text(file_name)
        input = await self.app.prompt(prompt="Enter a new file name for your configuration >>> ")
        input = format_config_file_name(input)
        file_path = os.path.join(CONF_FILE_PATH, input)
        if input is None or input == "":
            self._notify("Value is required.")
            return await self.prompt_new_file_name(strategy)
        elif os.path.exists(file_path):
            self._notify(f"{input} file already exists, please enter a new name.")
            return await self.prompt_new_file_name(strategy)
        else:
            return input

    async def update_all_secure_configs(self  # type: HummingbotApplication
                                        ):
        await Security.wait_til_decryption_done()
        Security.update_config_map(global_config_map)
        if self.strategy_config_map is not None:
            Security.update_config_map(self.strategy_config_map)
