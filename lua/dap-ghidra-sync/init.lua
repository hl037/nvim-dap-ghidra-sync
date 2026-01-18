local M = {}

local default_config = {
  ghidra_host = "127.0.0.1",
  ghidra_port = 18888,
  pc_register_names = { "pc", "rip", "eip", "r15" },
  retry_interval = 3000, -- milliseconds
  auto_enable = false,
}

local config = vim.deepcopy(default_config)

local state = {
  detected_pc_register = nil,
  connection_failed_once = false,
  retry_timer = nil,
  pending_address = nil,
  commands_created = false,
  enabled = false, -- Current enabled state (controlled by toggle)
}

local function get_script_path()
  local source = debug.getinfo(1, "S").source
  if source:sub(1, 1) == "@" then
    source = source:sub(2)
  end
  local plugin_dir = vim.fn.fnamemodify(source, ":h:h:h")
  return vim.fn.fnamemodify(plugin_dir, ":p")
end

local function clean_address(addr_str)
  -- Extract just the hex address, ignore symbols like "0x1234 <func+10>"
  local hex_part = addr_str:match("^(0x%x+)")
  if hex_part then
    return hex_part
  end
  return addr_str
end

local function send_to_ghidra(address, callback)
  address = clean_address(address)
  local url = string.format("http://%s:%d/goto", config.ghidra_host, config.ghidra_port)
  local cmd = string.format(
    "curl -s -f -X POST -H 'Content-Type: application/json' -d '{\"address\":\"%s\"}' %s 2>&1",
    address, url
  )
  
  vim.fn.jobstart(cmd, {
    stdout_buffered = true,
    on_stdout = function(_, data)
      if callback then
        callback(true, data)
      end
    end,
    on_exit = function(_, exit_code)
      if callback then
        callback(exit_code == 0, nil)
      end
    end
  })
end

local function handle_connection_error()
  if not state.connection_failed_once then
    state.connection_failed_once = true
    local script_path = get_script_path()
    vim.notify(
      string.format(
        "Failed to connect to Ghidra server at %s:%d\n\n" ..
        "To start the Ghidra server:\n" ..
        "1. Open Ghidra Script Manager (Window > Script Manager)\n" ..
        "2. Run script: %s\n\n" ..
        "Retrying silently every %ds...",
        config.ghidra_host,
        config.ghidra_port,
        script_path,
        config.retry_interval / 1000
      ),
      vim.log.levels.WARN
    )
  end
end

local function schedule_retry(address)
  if state.retry_timer then
    vim.fn.timer_stop(state.retry_timer)
  end
  
  state.pending_address = address
  
  state.retry_timer = vim.fn.timer_start(config.retry_interval, function()
    if not state.enabled or not state.pending_address then
      return
    end
    
    send_to_ghidra(state.pending_address, function(success)
      if success then
        state.pending_address = nil
        state.connection_failed_once = false
        if state.retry_timer then
          vim.fn.timer_stop(state.retry_timer)
          state.retry_timer = nil
        end
      else
        schedule_retry(state.pending_address)
      end
    end)
  end, { ["repeat"] = 1 })
end

local function sync_address(address)
  send_to_ghidra(address, function(success)
    if not success then
      handle_connection_error()
      schedule_retry(address)
    else
      state.connection_failed_once = false
      state.pending_address = nil
    end
  end)
end

function M.setup(opts)
  config = vim.tbl_deep_extend("force", default_config, opts or {})
  
  -- Initialize enabled state from auto_enable config
  state.enabled = config.auto_enable
  
  local ok, dap = pcall(require, "dap")
  if not ok then
    vim.notify("nvim-dap not found. Please install nvim-dap", vim.log.levels.ERROR)
    return
  end
  
  dap.listeners.after.event_stopped["dap-ghidra-sync"] = function(session, body)
    if not state.enabled then
      return
    end
    M.sync_with_ghidra(session)
  end
  
  -- Cleanup when DAP session terminates
  dap.listeners.after.event_terminated["dap-ghidra-sync"] = function(session, body)
    if state.retry_timer then
      vim.fn.timer_stop(state.retry_timer)
      state.retry_timer = nil
    end
    state.pending_address = nil
    state.connection_failed_once = false
    state.detected_pc_register = nil
  end
  
  -- Sync when navigating stack frames
  local function sync_on_frame_change()
    if not state.enabled then
      return
    end
    
    local session = dap.session()
    if not session then
      return
    end
    
    local current_frame = session.current_frame
    if not current_frame then
      return
    end
    
    -- Frame 0 is the current instruction, use PC register
    -- Other frames use instructionPointerReference from stack trace
    if current_frame.id == 0 then
      M.sync_with_ghidra(session)
    else
      -- Use instructionPointerReference directly for non-current frames
      if current_frame.instructionPointerReference then
        sync_address(current_frame.instructionPointerReference)
      end
    end
  end
  
  -- Hook into dap up/down commands by wrapping them
  local group = vim.api.nvim_create_augroup("DapGhidraSync", { clear = true })
  
  -- Also sync on stopped event (initial breakpoint)
  vim.api.nvim_create_autocmd("User", {
    pattern = "DapStopped",
    callback = sync_on_frame_change,
    group = group
  })
  
  -- Wrap dap.up() and dap.down() to trigger sync
  if dap.up then
    local original_up = dap.up
    dap.up = function()
      original_up()
      vim.defer_fn(sync_on_frame_change, 100)
    end
  end
  
  if dap.down then
    local original_down = dap.down
    dap.down = function()
      original_down()
      vim.defer_fn(sync_on_frame_change, 100)
    end
  end
  
  if not state.commands_created then
    vim.api.nvim_create_user_command("DapGhidraToggle", function()
      M.toggle()
    end, { desc = "Toggle DAP-Ghidra synchronization" })
    
    vim.api.nvim_create_user_command("DapGhidraScriptPath", function()
      print(M.get_script_path())
    end, { desc = "Display Ghidra script path" })
    
    vim.api.nvim_create_user_command("DapGhidraSync", function()
      M.sync_current_frame()
    end, { desc = "Manually sync current frame with Ghidra" })
    
    state.commands_created = true
  end
end

function M.sync_with_ghidra(session)
  if not session then
    return
  end
  
  local function try_register(reg_name, callback)
    session:request("evaluate", {
      expression = "$" .. reg_name,
      frameId = 0,
      context = "watch"
    }, function(err, response)
      if not err and response and response.result then
        callback(reg_name, response.result)
      end
    end)
  end
  
  if state.detected_pc_register then
    try_register(state.detected_pc_register, function(_, result)
      sync_address(result)
    end)
  else
    local found = false
    for _, reg_name in ipairs(config.pc_register_names) do
      if found then break end
      
      try_register(reg_name, function(name, result)
        if not found then
          found = true
          state.detected_pc_register = name
          vim.notify(string.format("Detected PC register: %s", name), vim.log.levels.INFO)
          sync_address(result)
        end
      end)
    end
  end
end

function M.sync_current_frame()
  local dap = require("dap")
  local session = dap.session()
  
  if not session then
    vim.notify("No active DAP session", vim.log.levels.WARN)
    return
  end
  
  local current_frame = session.current_frame
  if not current_frame then
    vim.notify("No current frame", vim.log.levels.WARN)
    return
  end
  
  -- Frame 0 is the current instruction, use PC register
  if current_frame.id == 0 then
    M.sync_with_ghidra(session)
  elseif current_frame.instructionPointerReference then
    -- For other frames, use the instruction pointer reference
    sync_address(current_frame.instructionPointerReference)
  else
    vim.notify("Cannot determine frame address", vim.log.levels.WARN)
  end
end
  
function M.toggle()
  state.enabled = not state.enabled
  
  if state.enabled then
    -- Sync immediately if DAP session is active
    local dap = require("dap")
    if dap.session() then
      M.sync_current_frame()
    end
  else
    -- Cleanup when disabling
    if state.retry_timer then
      vim.fn.timer_stop(state.retry_timer)
      state.retry_timer = nil
      state.pending_address = nil
    end
  end
end

function M.get_script_path()
  return get_script_path()
end

return M
