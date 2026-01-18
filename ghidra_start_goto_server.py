# START DAP-Ghidra Sync Server - Receives navigation requests from nvim-dap
# @runtime pyghidra
# @author Léo Flaventin HAUCHECORNE
# @category Debug
# @menupath Tools.GOTO-server.Start Server
# @toolbar

"""
DAP-Ghidra Sync Server
Receives navigation requests from nvim-dap and jumps to addresses in Ghidra.
"""

import asyncio
import json
import logging
import sys
import threading
from typing import Optional
from ghidra.app.services import GoToService

HOST = "127.0.0.1"
PORT = 18888
LOG_FILE = "/tmp/dap-ghidra-server.log"
MODULE_NAME = "__dap_ghidra_server__"

# Setup logger
logger = logging.getLogger("dap-ghidra")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")


# Check if module already exists and stop previous instance
if MODULE_NAME in sys.modules:
  logger.info("Stopping previous server instance...")
  old_module = sys.modules[MODULE_NAME]
  if hasattr(old_module, 'stop_server'):
    old_module.stop_server()
  del sys.modules[MODULE_NAME]
else :
  file_handler = logging.FileHandler(LOG_FILE)
  file_handler.setLevel(logging.DEBUG)
  file_handler.setFormatter(formatter)

  stdout_handler = logging.StreamHandler(sys.stdout)
  stdout_handler.setLevel(logging.DEBUG)
  stdout_handler.setFormatter(formatter)

  logger.addHandler(file_handler)
  logger.addHandler(stdout_handler)

class DAPGhidraServer:
  def __init__(self):
    self.server: Optional[asyncio.Server] = None
    self.running = False
  
  def goto_address(self, address_str: str) -> None:
    """Navigate to the specified address in Ghidra"""
    try:
      address_str = address_str.strip()
      if address_str.startswith("0x") or address_str.startswith("0X"):
        address_str = address_str[2:]
      
      address_value = int(address_str, 16)
      
      def navigate():
        try:
          program = currentProgram
          if program is None:
            logger.warning("No program loaded")
            return
          
          addr_space = program.getAddressFactory().getDefaultAddressSpace()
          address = addr_space.getAddress(address_value)
          
          if address is None:
            logger.warning(f"Invalid address: 0x{address_str}")
            return
          
          tool = state.getTool()
          if tool:
            goto_service = tool.getService(GoToService)
            if goto_service:
              goto_service.goTo(address)
              logger.info(f"Navigated to: {address.toString()}")
            else:
              logger.warning("GoToService not available")
          else:
            logger.warning("Tool not available")
        except Exception as e:
          logger.error(f"Navigation error: {e}")
      
      from javax.swing import SwingUtilities
      SwingUtilities.invokeLater(navigate)
      
    except ValueError:
      logger.error(f"Invalid address format: {address_str}")
    except Exception as e:
      logger.error(f"Address parsing error: {e}")
  
  async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handle HTTP client connection"""
    try:
      request_line = await reader.readline()
      request_line = request_line.decode('utf-8').strip()
      
      headers = {}
      while True:
        line = await reader.readline()
        line = line.decode('utf-8').strip()
        if not line:
          break
        if ':' in line:
          key, value = line.split(':', 1)
          headers[key.strip().lower()] = value.strip()
      
      if not request_line.startswith('POST /goto'):
        response = b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n'
        writer.write(response)
        await writer.drain()
        return
      
      content_length = int(headers.get('content-length', 0))
      body = await reader.read(content_length)
      
      try:
        data = json.loads(body.decode('utf-8'))
        address_str = data.get('address', '')
        
        if address_str:
          self.goto_address(address_str)
          response_body = b'{"status":"ok"}'
          response = f'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(response_body)}\r\n\r\n'.encode()
          writer.write(response + response_body)
        else:
          response_body = b'{"error":"no address provided"}'
          response = f'HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: {len(response_body)}\r\n\r\n'.encode()
          writer.write(response + response_body)
      
      except Exception as e:
        logger.error(f"Error handling request: {e}")
        response_body = json.dumps({"error": str(e)}).encode()
        response = f'HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\nContent-Length: {len(response_body)}\r\n\r\n'.encode()
        writer.write(response + response_body)
      
      await writer.drain()
      
    except Exception as e:
      logger.error(f"Client handler error: {e}")
    finally:
      writer.close()
      await writer.wait_closed()
  
  async def start(self) -> None:
    """Start the HTTP server"""
    if self.running:
      logger.warning("Server already running")
      return
    
    try:
      self.server = await asyncio.start_server(
        self.handle_client,
        HOST,
        PORT
      )
      
      self.running = True
      logger.info("=" * 60)
      logger.info("DAP-Ghidra Sync Server Started")
      logger.info(f"Listening on {HOST}:{PORT}")
      logger.info(f"Logging to: {LOG_FILE}")
      logger.info("=" * 60)
      
    except Exception as e:
      logger.error(f"Failed to start server: {e}")
      self.running = False
  
  async def stop(self) -> None:
    """Stop the HTTP server"""
    if not self.running:
      return
    
    try:
      if self.server:
        self.server.close()
        await self.server.wait_closed()
      
      self.running = False
      logger.info("Server stopped")
      
    except Exception as e:
      logger.error(f"Failed to stop server: {e}")

class VirtualModule:
  def __init__(self):
    self.server = DAPGhidraServer()
    self.loop: Optional[asyncio.AbstractEventLoop] = None
    self.thread: Optional[threading.Thread] = None
    self.stop_event: Optional[asyncio.Event] = None
  
  async def wait_for_stop(self):
    """Wait for stop signal"""
    await self.stop_event.wait()
    await self.server.stop()
    self.loop.stop()
    self.loop.close()
    self.loop = None
  
  async def alive_task(self):
    """Log alive status"""
    while not self.stop_event.is_set():
      logger.debug(f"ALIVE")
      await asyncio.sleep(1)
    logger.info("STOPPED")
  
  def run_event_loop(self):
    """Run event loop in thread"""
    self.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(self.loop)
    self.stop_event = asyncio.Event()
    
    try:
      self.loop.create_task(self.server.start())
      self.loop.create_task(self.wait_for_stop())
      self.loop.create_task(self.alive_task())

      
      self.loop.run_forever()
      
    except Exception as e:
      logger.error(f"Event loop error: {e}")
    finally:
      self.loop.close()
      logger.debug("Event loop closed")
  
  def start_server(self):
    """Start server in thread"""
    if self.thread and self.thread.is_alive():
      logger.warning("Server already running")
      return
    
    self.thread = threading.Thread(target=self.run_event_loop, daemon=True)
    self.thread.start()
    logger.info("Server thread started")
  
  def stop_server(self):
    """Stop server"""
    if not self.thread or not self.thread.is_alive():
      logger.warning("Server not running")
      return
    
    logger.info("Stopping server...")
    self.loop.call_soon_threadsafe(self.stop_event.set)
    self.thread.join(timeout=5)
    
    if self.thread.is_alive():
      logger.warning("Thread did not stop cleanly")
    else:
      logger.info("Server thread stopped")
    
    self.thread = None
    self.loop = None

# Register virtual module
virtual_module = VirtualModule()
sys.modules[MODULE_NAME] = virtual_module

# Start server automatically
virtual_module.start_server()
logger.info("DAP-Ghidra sync plugin loaded successfully")
