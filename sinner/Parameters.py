import shlex
import sys
from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
from typing import List

from sinner.utilities import get_app_dir
from sinner.validators.AttributeDocumenter import AttributeDocumenter


class Parameters:
    parser: ArgumentParser = ArgumentParser()
    parameters: Namespace

    _config_name: str

    def __init__(self, source: Namespace | str | None = None):
        if isinstance(source, Namespace):
            self.parameters: Namespace = source
        elif isinstance(source, str):
            self.parameters: Namespace = self.command_line_to_namespace(source)
        else:
            self.parameters: Namespace = Namespace()
        if 'h' in self.parameters or 'help' in self.parameters:
            AttributeDocumenter().show_help()
        if 'ini' in self.parameters:
            self._config_name = self.parameters.ini
        else:
            self._config_name = get_app_dir('sinner.ini')

        config = ConfigParser()
        config.read(self._config_name)
        if config.has_section('sinner'):
            for key in config['sinner']:
                value = config['sinner'][key]
                key = key.replace('-', '_')
                if key not in self.parameters:
                    self.parameters.__setattr__(key, value)

    def module_parameters(self, module_name: str) -> Namespace | None:
        module_parameters: Namespace = Namespace()
        config = ConfigParser()
        config.read(self._config_name)
        if config.has_section(module_name):
            for key in config[module_name]:
                value = config[module_name][key]
                key = key.replace('-', '_')
                module_parameters.__setattr__(key, value)
            return module_parameters
        return None

    @staticmethod
    def command_line_to_namespace(cmd_params: str | None = None) -> Namespace:
        processed_parameters: Namespace = Namespace()
        if cmd_params is None:
            args_list = sys.argv[1:]
        else:
            args_list = shlex.split(cmd_params)
        result = []
        current_sublist: List[str] = []
        for item in args_list:
            if item.startswith('--'):
                if current_sublist:
                    result.append(current_sublist)
                    current_sublist = []
                current_sublist.append(item)
            else:
                current_sublist.append(item)
        if current_sublist:
            result.append(current_sublist)

        for parameter in result:
            if len(parameter) > 2:
                setattr(processed_parameters, parameter[0].lstrip('-').replace('-', '_'), parameter[1:])
            elif len(parameter) == 1 and '=' not in parameter[0]:
                setattr(processed_parameters, parameter[0].lstrip('-').replace('-', '_'), True)
            else:  # 2 args
                key, value = parameter[0].split('=') if '=' in parameter[0] else parameter
                setattr(processed_parameters, key.lstrip('-').replace('-', '_'), value)
        return processed_parameters

    @staticmethod
    def parse_argument(argument: str) -> tuple[str, str] | tuple[str, list[str]] | None:  # key and list of values
        if not argument.startswith('--'):
            return None
        if '=' in argument:  # '--key=value'
            key, value = argument[2:].split('=')
            return key, value
        elif ' ' not in argument:  # --key
            return None
        else:  # '--key value1 value2'
            key, value = argument[2:].split('=')
            return key, value.split()
