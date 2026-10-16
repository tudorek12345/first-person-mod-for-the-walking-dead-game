-- One JSONL log per Lua script session, plus a readable aggregate log.
-- Files are closed after every record so an engine crash loses no buffered log.
if FP_Log then return end
local L={sequence=0,errors=0,warnings=0,repeats={},part=1,bytes=0}
FP_Log=L
local generated=FP_Generated or {}
local function quote(value)
  local text=tostring(value)
  text=string.gsub(text,'[\\"%z\1-\31]',function(c)
    if c=='\\' then return '\\\\' end
    if c=='"' then return '\\"' end
    return string.format('\\u%04x',string.byte(c))
  end)
  return '"'..text..'"'
end
local function encode(fields)
  local parts={}
  for k,v in pairs(fields) do
    local value=quote(v)
    if type(v)=="boolean" then value=tostring(v)
    elseif type(v)=="number" and v==v and v~=math.huge and v~=-math.huge then value=tostring(v) end
    parts[#parts+1]=quote(k)..":"..value
  end
  table.sort(parts)
  return "{"..table.concat(parts,",").."}\n"
end
local function timestamp()
  return os and os.date and os.date("!%Y-%m-%dT%H:%M:%SZ") or "time-unavailable"
end
local stem=string.gsub(timestamp(),"[^%w]","")
local directory=generated.log_dir or "."
local index=1
if io and io.open then
  while index<10000 do
    local candidate=directory.."/fp-"..stem.."-"..index..".jsonl"
    local existing=io.open(candidate,"r")
    if not existing then L.path=candidate; break end
    existing:close(); index=index+1
  end
end
L.session=stem.."-"..index
local function append(path,text)
  if not path or not io or not io.open then return false end
  local file,err=io.open(path,"a")
  if not file then return false,err end
  local ok,why=file:write(text)
  file:close()
  return ok~=nil,why
end
function L.write(level,event,fields)
  local ok,err=pcall(function()
    L.sequence=L.sequence+1
    if level=="error" then L.errors=L.errors+1 elseif level=="warn" then L.warnings=L.warnings+1 end
    local record={time=timestamp(),session=L.session,seq=L.sequence,level=level,event=event,
      build=generated.build or "development",episode=generated.episode or "unknown",native_test=generated.native_test==true}
    for k,v in pairs(fields or {}) do record[k]=v end
    if L.context then
      local good,extra=pcall(L.context)
      if good and extra then for k,v in pairs(extra) do record[k]=v end end
    end
    local line=encode(record)
    if L.bytes+#line>2*1024*1024 and L.path then
      L.part=L.part+1; L.bytes=0
      L.path=directory.."/fp-"..L.session.."-part"..L.part..".jsonl"
    end
    local saved,why=append(L.path,line)
    L.bytes=L.bytes+#line
    local readable="[TWD FP "..L.session.."] "..level.." "..event
    if fields and fields.message then readable=readable..": "..tostring(fields.message) end
    append(generated.log_path or "twd_firstperson.log",readable.."\n")
    if not saved and not L.file_error then
      L.file_error=true; print("[TWD FP] Cannot write session log: "..tostring(why).."; "..readable)
    end
  end)
  if not ok then print("[TWD FP] Logger failure: "..tostring(err)) end
end
function L.traceback(err)
  local message=tostring(err)
  if debug and debug.traceback then
    local ok,trace=pcall(debug.traceback,message,2)
    if ok and type(trace)=="string" and #trace>0 then
      if not string.find(trace,message,1,true) then trace=message.."\n"..trace end
      return trace
    end
  end
  -- Retail Telltale builds can return an empty string from debug.traceback.
  local lines={message}
  if debug and debug.getinfo then
    for depth=2,12 do
      local ok,info=pcall(debug.getinfo,depth,"Sln")
      if not ok or not info then break end
      lines[#lines+1]=tostring(info.short_src or info.source or "?")..":"..
        tostring(info.currentline or "?").." in "..tostring(info.name or "?")
    end
  end
  if #lines==1 then lines[2]="(stack unavailable in this engine build)" end
  return table.concat(lines,"\n")
end
function L.error(label,err)
  local identity=label..":"..tostring(err)
  local count=(L.repeats[identity] or 0)+1
  L.repeats[identity]=count
  -- Record initial occurrences and periodic totals instead of flooding disk.
  if count<=3 or count%100==0 then L.write("error",label,{message=err,occurrences=count}) end
end
function L.try(label,fn,...)
  local args,n={...},select("#",...)
  local result
  local ok,err=xpcall(function() result={fn(unpack(args,1,n))} end,L.traceback)
  if not ok then L.error(label,err); return false,err end
  return true,unpack(result)
end
L.write("info","session_start",{log_path=L.path or "unavailable"})
