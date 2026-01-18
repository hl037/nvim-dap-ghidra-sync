# STOP DAP-Ghidra Sync Server - Receives navigation requests from nvim-dap
# @runtime pyghidra
# @author Léo Flaventin HAUCHECORNE
# @description Stop DAP-Ghidra Sync Server
# @category Debug
# @menupath Tools.GOTO-server.Stop Server
# @toolbar

import sys
import logging

MODULE_NAME = "__dap_ghidra_server__"

# Setup logger
logger = logging.getLogger("dap-ghidra")
if not logger.handlers:
  handler = logging.StreamHandler(sys.stdout)
  handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
  logger.addHandler(handler)
  logger.setLevel(logging.INFO)

if MODULE_NAME in sys.modules:
  sys.modules[MODULE_NAME].stop_server()
else:
  logger.warning("DAP-Ghidra server not running")
