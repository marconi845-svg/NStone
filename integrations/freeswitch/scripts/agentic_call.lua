-- NStone Agentic Calling — turn-based loop via Voice Bridge HTTP API
-- Requires: mod_lua, Python 3 + voice_turn_post.py

local max_turns = 8
local record_seconds = 6
local post_helper = "C:/freeswitch/scripts/voice_turn_post.py"
local wait_max_sec = 180
local hold_interval_sec = 8

local api = freeswitch.API()

local function log_info(msg)
  freeswitch.consoleLog("INFO", "[agentic_call] " .. tostring(msg) .. "\n")
end

local function winpath(p)
  return tostring(p):gsub("/", "\\")
end

local function json_escape(s)
  if not s then return "" end
  s = tostring(s)
  s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "")
  return s
end

local function ensure_dir(path)
  os.execute('mkdir "' .. winpath(path) .. '" 2>nul')
end

local function normalize_json_path(raw)
  if not raw then return nil end
  return raw:gsub("\\\\", "/"):gsub("\\", "/")
end

local function python_exe()
  local f = io.open("C:/freeswitch/scripts/python_path.txt", "r")
  if f then
    local p = (f:read("*l") or ""):gsub("^%s+", ""):gsub("%s+$", "")
    f:close()
    if p ~= "" then return p end
  end
  return "python"
end

local function play_hold_tone()
  session:streamFile("tone_stream://%(80,0,440,480)")
end

local function play_error_tone()
  session:streamFile("tone_stream://%(400,0,350,440);%(400,0,280,440);%(600,0,200,280)")
end

local function spawn_voice_post(json_path, resp_path, stamp)
  local launcher = string.format("C:/freeswitch/tmp/run_%s.cmd", stamp)
  local lf = io.open(launcher, "w")
  if not lf then
    log_info("cannot write launcher " .. launcher)
    return false
  end
  lf:write(string.format(
    "@echo off\r\n\"%s\" \"%s\" \"%s\" \"%s\"\r\n",
    python_exe(),
    winpath(post_helper),
    winpath(json_path),
    winpath(resp_path)
  ))
  lf:close()

  local bg_cmd = 'cmd /c "' .. winpath(launcher) .. '"'
  local job = api:execute("bg_system", bg_cmd)
  log_info("bg_system job=" .. tostring(job) .. " cmd=" .. bg_cmd)
  return job and job:find("+OK") ~= nil
end

local function post_voice_turn(uuid, ext_key, wav_path)
  local body = string.format(
    '{"call_uuid":"%s","extension_key":"%s","wav_in":"%s","source":"freeswitch"}',
    json_escape(uuid),
    json_escape(ext_key),
    json_escape(wav_path:gsub("\\", "/"))
  )

  local tmp_dir = "C:/freeswitch/tmp"
  ensure_dir(tmp_dir)
  local stamp = tostring(os.time()) .. "_" .. uuid:sub(1, 8)
  local tmp_json = string.format("%s/turn_%s.json", tmp_dir, stamp)
  local resp_file = string.format("%s/resp_%s.json", tmp_dir, stamp)

  local jf = io.open(tmp_json, "w")
  if not jf then
    log_info("cannot write temp json")
    return nil
  end
  jf:write(body)
  jf:close()

  os.remove(resp_file)
  os.remove(resp_file .. ".part")

  log_info("POST voice/turn ext=" .. ext_key .. " json=" .. tmp_json)
  if not spawn_voice_post(tmp_json, resp_file, stamp) then
    log_info("bg_system failed, trying synchronous POST")
    local sync_cmd = string.format(
      'cmd /c ""%s" "%s" "%s" "%s""',
      python_exe(),
      winpath(post_helper),
      winpath(tmp_json),
      winpath(resp_file)
    )
    os.execute(sync_cmd)
  end

  session:speak("Un momento per favore, elaboro la richiesta.")

  local waited = 0
  while waited < wait_max_sec do
    if not session:ready() then
      log_info("caller hung up during AI wait")
      return nil
    end

    local rf = io.open(resp_file, "r")
    if rf then
      local raw = rf:read("*a") or ""
      rf:close()
      if #raw > 30 and (raw:find('"text_out"%s*:%s*"') or raw:find('"wav_out"%s*:%s*"')) then
        log_info("bridge response=" .. raw:sub(1, 220))
        return raw
      end
    end

    session:streamFile("silence_stream://" .. tostring(hold_interval_sec * 1000 - 80))
    play_hold_tone()
    waited = waited + hold_interval_sec
  end

  log_info("timeout waiting bridge (" .. wait_max_sec .. "s)")
  return nil
end

local function extract_json_field(raw, field)
  if not raw then return nil end
  local pattern = '"' .. field .. '"%s*:%s*"([^"]*)"'
  return raw:match(pattern)
end

if not session:ready() then
  return
end

session:setVariable("call_timeout", "300")
session:setVariable("session_timer", "300")
session:setVariable("rtp_timeout_sec", "300")
session:setVariable("sip_enable_timer", "false")

local uuid = session:get_uuid()
local ext_key = session:getVariable("agentic_extension_key") or "commercial"
local rec_dir = session:getVariable("agentic_recordings_dir") or "C:/freeswitch/recordings/agentic"
ensure_dir(rec_dir)

session:streamFile("tone_stream://%(250,0,640,480)")
session:sleep(300)

for turn = 1, max_turns do
  if not session:ready() then break end

  local wav_in = string.format("%s/%s_in_%d.wav", rec_dir, uuid, turn)
  session:streamFile("silence_stream://150")
  session:recordFile(wav_in, record_seconds, 500, 3)
  log_info("recorded " .. wav_in)

  local raw = post_voice_turn(uuid, ext_key, wav_in)
  if not raw or raw == "" then
    log_info("voice bridge timeout/offline — avvia legacy\\AVVIA_VOICE_BRIDGE.bat")
    play_error_tone()
    break
  end

  if not session:ready() then
    log_info("caller hung up before playback")
    break
  end

  local wav_out = normalize_json_path(extract_json_field(raw, "wav_out"))
  local text_out = extract_json_field(raw, "text_out")

  if wav_out and wav_out ~= "" then
    log_info("playing " .. wav_out)
    session:streamFile(wav_out)
  elseif text_out and text_out ~= "" then
    session:speak(text_out)
  else
    log_info("no wav_out/text_out in response")
    play_error_tone()
    break
  end
end

session:hangup()
