from sinner.utilities import suggest_max_memory
from sinner.validators.AttributeLoader import AttributeLoader, Rules


class Sinner(AttributeLoader):

    # the main module cannot be documented with AttributeDocumenter, because it causes a circular import
    def rules(self) -> Rules:
        return [
            {
                'parameter': 'max-memory',
                'attribute': 'max_memory',
                'default': suggest_max_memory(),
                'help': 'The maximum amount of RAM (in GB) that will be allowed for use'
            },
            {
                'parameter': 'gui',
                'default': False,
                'help': 'Run application in a graphic mode'
            },
            {
                'parameter': 'benchmark',
                'default': False,
                'help': 'Run a benchmark on a selected frame processor'
            },
            {
                'parameter': ['threading', 't'],
                'attributes': 'threading',
                'default': True,
                'help': 'Run processing in threads (experimental)'
            },
            {
                'module_help': 'The main application'
            }
        ]
