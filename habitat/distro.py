class Alias(object):
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments

class Distro(object):
    def __init__(self, config):
        super(Distro, self).__init__()
        self.config = config

    def parse(self, config):
        self.name = config["name"]
        self.version = config["version"]
        self.aliases = []
        for system, aliases in config.get("aliases", {}).items():
            if system == 
            self.aliases.append(Alias(alias[0], alias[1]))
        self.environment = config.get("environment", {})
