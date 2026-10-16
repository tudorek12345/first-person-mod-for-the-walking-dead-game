-- Only compensate hides issued by the original camera-visibility module.
-- Chores, story scripts, exclusive variants and the avatar retain ownership.
if FP_Visibility then return end
local V={}
FP_Visibility=V
local nativeHide=AgentHide
local records,samples={},{}
local enabled,activeScene,avatar,scope=false,nil,nil,0
local clock,hooks=0,0
local function pack(...) return {n=select("#",...),...} end
local function valid(a) return a~=nil and AgentIsValid(a) end
local function resolve(a) if type(a)=="string" then return AgentFind(a) end; return a end
local function scene_name(value)
  if value and type(value)~="string" then value=ResourceGetName(value) end
  local name=string.lower(string.gsub(tostring(value or "none"),"\\","/"))
  name=string.match(name,"([^/]+)$") or name
  return string.gsub(name,"%.scene$","")
end
local function log(event,r,extra)
  if not FP_Log then return end
  local fields={agent=valid(r.agent) and AgentGetName(r.agent) or "invalid",agent_scene=r.scene}
  for k,v in pairs(extra or {}) do fields[k]=v end
  FP_Log.write("info",event,fields)
end
local function attempt(label,fn)
  if FP_Log then return FP_Log.try(label,fn) end
  return pcall(fn)
end
local function exclusive(a)
  local value=a.mProps["Visibility - Show Only in Cameras"]
  if value==nil then return false end
  return EasyContainer(value):getn()>0
end
local function proxy_owned(a)
  local value=a.mProps["Transient Visibility Proxy"]
  return type(value)=="number" and value>=0
end
local function revoke(r,reason)
  if r.overridden then log("visibility_revoked",r,{reason=reason}) end
  r.overridden,r.pending,r.story=false,false,true
end
local function hide_record(r,hidden)
  local extra=r.extra or {n=0}
  return nativeHide(r.agent,hidden,unpack(extra,1,extra.n))
end
local function restore_record(r)
  if not r.overridden then r.pending=false; return end
  if not valid(r.agent) then records[r.agent]=nil; samples[r.agent]=nil; return end
  if proxy_owned(r.agent) then revoke(r,"visibility_proxy"); return end
  if AgentIsHidden(r.agent) or r.agent.mProps["Runtime: Visible"]==false then revoke(r,"native_visibility"); return end
  hide_record(r,r.desired)
  r.overridden,r.pending=false,false
  log("visibility_restored",r,{camera_hidden=r.desired})
end
local function restore_try(r)
  local ok=attempt("visibility_restore_error",function() restore_record(r) end)
  if not ok then
    r.pending=true; r.attempts=(r.attempts or 0)+1
    r.due=clock+(({0.25,1,3})[r.attempts] or 10)
  end
end
local function allowed(r)
  return enabled and r.scene==activeScene and r.agent~=avatar and not r.exclusive
    and r.desired and not r.story and not proxy_owned(r.agent)
end
local function apply(r)
  if not valid(r.agent) then records[r.agent]=nil; samples[r.agent]=nil; return end
  if r.overridden and (proxy_owned(r.agent) or AgentIsHidden(r.agent) or r.agent.mProps["Runtime: Visible"]==false) then
    revoke(r,proxy_owned(r.agent) and "visibility_proxy" or "native_visibility")
  end
  if allowed(r) then
    if not r.overridden then
      hide_record(r,false); r.overridden=true; r.pending=false; r.attempts=0
      log("visibility_override",r,{camera_hidden=true,exclusive=false})
    end
  elseif r.overridden and not r.pending then restore_try(r) end
end
AgentHide=function(agent,hidden,...)
  local extra=pack(...)
  local a=resolve(agent)
  if scope<=0 or not valid(a) then
    local result=pack(nativeHide(agent,hidden,unpack(extra,1,extra.n)))
    local r=records[a]
    if r then revoke(r,"story_agenthide") end
    return unpack(result,1,result.n)
  end
  -- Commit only after the native call succeeds. An exception must not discard
  -- ownership of an earlier override (including its original recursive flag).
  local proposed={agent=a,scene=scene_name(AgentGetScene(a)),extra=extra,
    desired=hidden==true,exclusive=exclusive(a),story=false,pending=false,overridden=false}
  local override=allowed(proposed)
  local applied=hidden
  if override then applied=false end
  local result=pack(nativeHide(agent,applied,unpack(extra,1,extra.n)))
  proposed.overridden=override
  records[a]=proposed
  if override then log("visibility_override",proposed,{camera_hidden=true,exclusive=false}) end
  return unpack(result,1,result.n)
end
function V.scoped(fn,...)
  local args,n={...},select("#",...)
  scope=scope+1
  local result=pack(pcall(function() return fn(unpack(args,1,n)) end))
  scope=scope-1
  if not result[1] then assert(false,result[2]) end
  return unpack(result,2,result.n)
end
-- Native fixtures can exercise the exact scope used for original callbacks.
V.camera_call=V.scoped
function V.wrap_callback(fn)
  return function(...) return V.scoped(fn,...) end
end
function V.load_original(loader)
  local callbacks=Callback_CameraChanged
  local own=rawget(callbacks,"Add")
  local add=callbacks.Add
  callbacks.Add=function(self,fn,handler)
    if self==callbacks then
      local result=add(self,V.wrap_callback(fn),handler)
      hooks=hooks+1
      return result
    end
    return add(self,fn,handler)
  end
  local ok,result=pcall(loader)
  rawset(callbacks,"Add",own)
  if not ok then assert(false,result) end
  return result
end
function V.restore()
  enabled=false
  for _,r in pairs(records) do if r.overridden then restore_try(r) end end
end
function V.update(on,scene,player)
  local name=scene and scene_name(scene) or nil
  if activeScene and name and name~=activeScene then
    V.restore(); samples={}
    for a,r in pairs(records) do if not r.overridden and r.scene~=name then records[a]=nil end end
  end
  enabled,activeScene,avatar=on==true,name or activeScene,player
  for _,r in pairs(records) do apply(r) end
end
function V.tick(dt)
  clock=clock+math.max(0,math.min(dt or 0,0.1))
  for _,r in pairs(records) do
    if not valid(r.agent) then records[r.agent]=nil; samples[r.agent]=nil
    elseif r.pending and clock>=(r.due or 0) then restore_try(r) end
  end
  for a in pairs(samples) do if not valid(a) then samples[a]=nil end end
end
function V.stats()
  local out={tracked=0,overridden=0,pending=0,hooks=hooks}
  for _,r in pairs(records) do
    out.tracked=out.tracked+1
    if r.overridden then out.overridden=out.overridden+1 end
    if r.pending then out.pending=out.pending+1 end
  end
  return out
end
function V.camera_hidden(agent)
  local a=resolve(agent)
  local r=records[a]
  return r~=nil and valid(a) and r.desired and not r.exclusive and not r.story
    and not proxy_owned(a) and AgentIsHidden(a)
end
function V.sample(scene,player)
  if not scene or not valid(player) then return end
  local root=AgentGetWorldPos(player)
  local stats=V.stats()
  stats.visible_actors,stats.hidden_actors,stats.scanned,stats.emitted=0,0,0,0
  for _,a in ipairs(SceneGetAgents(scene)) do
    if valid(a) then
      stats.scanned=stats.scanned+1
      local actor=AgentHasNode(a,"head")
      local distance=VectorDistance(root,AgentGetWorldPos(a))
      local r=records[a]
      if (actor and distance<=30) or r then
        local hidden=AgentIsHidden(a)
        if actor and distance<=30 then
          local key=hidden and "hidden_actors" or "visible_actors"; stats[key]=stats[key]+1
        end
        local runtime,proxy=a.mProps["Runtime: Visible"],a.mProps["Transient Visibility Proxy"]
        local identity=tostring(hidden)..":"..tostring(runtime)..":"..tostring(proxy)..":"..tostring(r and r.overridden)
        if samples[a]~=identity and stats.emitted<64 then
          samples[a]=identity; stats.emitted=stats.emitted+1
          log("visibility_state",r or {agent=a,scene=scene_name(scene)},
            {hidden=hidden,runtime_visible=runtime==nil and "unset" or runtime,
             visibility_proxy=proxy==nil and "unset" or proxy,distance=distance,has_head=actor,
             camera_rule=r~=nil,exclusive=r and r.exclusive or false,overridden=r and r.overridden or false})
        end
      end
    end
  end
  if FP_Log then FP_Log.write("info","visibility_summary",stats) end
end
