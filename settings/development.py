# -*- coding: utf-8 -*-

import logging

logging_level = logging.DEBUG



class bot:
    command_prefix = "p!"

    startup_cogs = [
        "cogs.play",
        "cogs.logs"
    ]
