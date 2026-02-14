# -*- encoding=utf8 -*-
__author__ = "admin"

from airtest.core.api import *
from airtest.cli.parser import cli_setup

if not cli_setup():
    auto_setup(__file__, logdir=True, devices=["android://127.0.0.1:5037/64fb07e2?touch_method=MAXTOUCH&",], project_root="/Users/admin/go/src/go_cookies/autovt")

poco(text="Créer un compte").click()


poco(text="Créer un nouveau compte").click()



