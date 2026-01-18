# dap-ghidra-sync.nvim

Synchronize [nvim-dap](https://github.com/mfussenegger/nvim-dap) debugging sessions with [Ghidra](https://ghidra-sre.org/)'s disassembler view.

When you hit a breakpoint in nvim-dap, Ghidra automatically jumps to the corresponding address in the disassembly.

## Features

- 🔄 Automatic synchronization between nvim-dap and Ghidra
- 📚 **Stack frame navigation support** - Syncs when navigating call stack
- 🎯 Auto-detection of PC register (supports ARM, x86, x86_64, RISC-V)
- 🔁 Smart retry logic with silent background retries
- 🌐 Support for remote Ghidra instances
- ⚡ Minimal configuration required

## Requirements

- Neovim >= 0.5.0
- [nvim-dap](https://github.com/mfussenegger/nvim-dap)
- [Ghidra](https://ghidra-sre.org/)
- `curl` (for HTTP communication)

## Installation

### Using [lazy.nvim](https://github.com/folke/lazy.nvim)

```lua
{
  'your-username/nvim-dap-ghidra-sync',
  dependencies = { 'mfussenegger/nvim-dap' },
  config = function()
    require('dap-ghidra-sync').setup()
  end
}
```

### Using [packer.nvim](https://github.com/wbthomason/packer.nvim)

```lua
use {
  'your-username/nvim-dap-ghidra-sync',
  requires = { 'mfussenegger/nvim-dap' },
  config = function()
    require('dap-ghidra-sync').setup()
  end
}
```

### Using [vim-plug](https://github.com/junegunn/vim-plug)

```vim
Plug 'mfussenegger/nvim-dap'
Plug 'your-username/nvim-dap-ghidra-sync'
```

Then in your `init.lua`:

```lua
require('dap-ghidra-sync').setup()
```

### Manual Installation

```bash
git clone https://github.com/your-username/nvim-dap-ghidra-sync ~/.config/nvim/pack/plugins/start/nvim-dap-ghidra-sync
```

## Setup

### Neovim Configuration

Add to your `init.lua`:

```lua
require('dap-ghidra-sync').setup({
  ghidra_host = "127.0.0.1",
  ghidra_port = 18888,
  retry_interval = 3000, -- milliseconds
})
```

### Ghidra Setup

1. Open Ghidra and load your binary
2. Open Script Manager: `Window > Script Manager`
3. Add the directory of this plugin to the script directorories. The script path is displayed when you run `:DapGhidraScriptPath`.
4. Search for "goto server" in the Script manager window
5. Check "In tools" for both start and stop scripts.
6. In the `Tool` window menu, you shold see a new `GOTO-server` entry. Now you can start / stop the ghidra side server.

You will have to repeat this for all the projects you want to use ghidra. Alternatively, you can copy the script in standard locations.

## Usage

### Basic Workflow

1. **Start Ghidra server**: To to `Tool > GOTO-server > Start Server`
2. **Configure nvim-dap**: Set up your debug adapter as usual
3. **Start debugging**: The plugin will automatically sync with Ghidra

### Stack Frame Navigation

The plugin automatically synchronizes when you navigate through the call stack:

- **Frame 0** (current instruction): Uses PC register value
- **Other frames**: Uses instruction pointer from the stack trace

This works automatically with [nvim-dap-ui](https://github.com/rcarriga/nvim-dap-ui) when selecting frames, or you can manually sync with `:DapGhidraSync`.

```lua
-- Example: Navigate stack and sync
vim.keymap.set('n', '<F10>', ':DapStepOver<CR>')
vim.keymap.set('n', '<F11>', ':DapStepInto<CR>')
vim.keymap.set('n', '<leader>ds', ':DapGhidraSync<CR>') -- Manual sync
```

### Connection Handling

- **First connection failure**: Shows an error message with setup instructions
- **Subsequent failures**: Retries silently every 3 seconds in the background
- **Successful connection**: Clears retry state and syncs immediately

### Commands

```vim
" Toggle synchronization on/off
:DapGhidraToggle

" Manually sync current frame (useful when navigating stack)
:DapGhidraSync

" Show Ghidra script path
:DapGhidraScriptPath
```

### Lua API

```lua
local dap_ghidra = require('dap-ghidra-sync')

-- Initial setup
dap_ghidra.setup({
  ghidra_host = "127.0.0.1",
  ghidra_port = 18888
})

-- Reconfigure at runtime
dap_ghidra.setup({
  ghidra_host = "192.168.1.100",
  ghidra_port = 9999
})

-- Toggle sync
dap_ghidra.toggle()

-- Manually sync current frame (useful for stack navigation)
dap_ghidra.sync_current_frame()

-- Get script path
local path = dap_ghidra.get_script_path()
```

## Configuration

### Default Configuration

```lua
{
  ghidra_host = "127.0.0.1",
  ghidra_port = 18888,
  retry_interval = 3000, -- milliseconds
  pc_register_names = { "pc", "rip", "eip", "r15" },
  auto_enable = false -- Disabled by default, toggle with :DapGhidraToggle
}
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ghidra_host` | string | `"127.0.0.1"` | Ghidra server hostname/IP |
| `ghidra_port` | number | `18888` | Ghidra server port |
| `retry_interval` | number | `3000` | Retry interval in milliseconds |
| `pc_register_names` | table | `{"pc", "rip", "eip", "r15"}` | PC register names to detect |
| `auto_enable` | boolean | `false` | Auto-enable when DAP session starts |

### Supported Architectures

The plugin automatically detects the PC register for:

- **ARM/ARM64**: `pc`, `r15`
- **x86_64**: `rip`
- **x86**: `eip`
- **RISC-V**: `pc`

Add custom register names if needed:

```lua
require('dap-ghidra-sync').setup({
  pc_register_names = { "pc", "rip", "eip", "r15", "custom_pc" }
})
```

## Advanced Usage

### Remote Ghidra Instance

```lua
require('dap-ghidra-sync').setup({
  ghidra_host = "192.168.1.100",
  ghidra_port = 18888
})
```

Make sure the port is accessible through your firewall.

### Reconfiguring at Runtime

You can change configuration by calling `setup()` again:

```lua
-- Change to a different server
require('dap-ghidra-sync').setup({
  ghidra_host = "10.0.0.5",
  ghidra_port = 9999
})
```

This will update the configuration and reset the connection state.

### Custom Retry Interval

```lua
require('dap-ghidra-sync').setup({
  retry_interval = 5000, -- 5 seconds
})
```

### Auto-enable on DAP Session

By default, sync is disabled. Auto-enable it when a DAP session starts:

```lua
require('dap-ghidra-sync').setup({
  auto_enable = true
})
```

Note: You can still manually toggle sync on/off with `:DapGhidraToggle` regardless of the `auto_enable` setting.

## Troubleshooting

### Plugin Not Syncing

1. Verify Ghidra script is running: Check Ghidra console for "Server thread started"
2. Check network: `curl -X POST http://127.0.0.1:18888/goto -d '{"address":"0x1000"}'`
3. Verify nvim-dap is working: Use `:DapToggleBreakpoint` and start debugging
4. Check PC register detection: Look for "Detected PC register" notification

### Connection Refused

- Ensure `ghidra_dap_server.py` is running in Ghidra
- Verify host/port configuration matches
- Check firewall settings for remote connections

### Wrong Address

The plugin sends the raw value from the PC register. If addresses don't match:
- Verify the binary loaded in Ghidra matches the one being debugged
- Check if address space configuration is correct in Ghidra
- Look for ASLR or relocation issues

### Session Cleanup

When a DAP session terminates, the plugin automatically cleans up:
- Stops any active retry timers
- Clears pending sync requests
- Resets connection state and detected register cache

The enabled/disabled state persists across sessions - if you had sync enabled, it stays enabled for the next debug session.

## How It Works

1. Plugin hooks into nvim-dap's `after.event_stopped` listener
2. When debugger stops, it queries the PC register value
3. Sends HTTP POST request to Ghidra server with the address
4. Ghidra server navigates to the address in the disassembly view

## Contributing

Contributions are welcome! Feel free to:

- Report bugs
- Suggest features
- Submit pull requests

## License

MIT

## See Also

- [nvim-dap](https://github.com/mfussenegger/nvim-dap) - Debug Adapter Protocol client
- [Ghidra](https://ghidra-sre.org/) - Software reverse engineering framework
