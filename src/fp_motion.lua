-- Player-eye translation filter. Native camera heading is deliberately untouched.
FP_Motion={}
local M=FP_Motion
local function finite(n) return type(n)=="number" and n==n and math.abs(n)<1000000 end
local function valid(v) return v and finite(v.x) and finite(v.y) and finite(v.z) end
local function copy(v) return v and {x=v.x,y=v.y,z=v.z} end
local function add(a,b) return {x=a.x+b.x,y=a.y+b.y,z=a.z+b.z} end
local function sub(a,b) return {x=a.x-b.x,y=a.y-b.y,z=a.z-b.z} end
local function distance(a,b)
  local x,y,z=a.x-b.x,a.y-b.y,a.z-b.z
  return math.sqrt(x*x+y*y+z*z)
end
local function option(cfg,name,default,minimum,maximum)
  local value=cfg and cfg[name]
  if not finite(value) then value=default end
  return math.max(minimum,math.min(maximum,value))
end
local function event(kind,reason,extra)
  local value=extra or {}; value.kind=kind; value.reason=reason; return value
end
function M.new() return {} end
function M.reset(s) for key in pairs(s) do s[key]=nil end end

-- sample.identity identifies the player+scene, never the current camera agent.
-- sample.eye is the desired world eye position before the look-direction offset.
-- All outputs are plain xyz tables; engine adapters convert them with Vector().
function M.update(s,sample,dt,frame,cfg)
  sample=sample or {}
  if s.identity~=sample.identity then M.reset(s); s.identity=sample.identity end
  -- Authored puzzles/aiming must retain their exact native positions immediately.
  if sample.authored then
    local changed=not s.authored
    s.authored=true; s.frame=frame; s.pending=nil
    if valid(sample.eye) then
      s.position=copy(sample.eye); s.invalid=nil
      return copy(s.position),changed and event("reset","authored_camera") or nil
    end
    local first=s.invalid~="authored_eye"
    s.invalid="authored_eye"
    return copy(s.position),first and event("invalid_sample","authored_eye") or nil
  end
  if frame~=nil and s.frame==frame and not s.authored then return copy(s.position) end
  s.frame=frame
  dt=finite(dt) and math.max(0,math.min(0.1,dt)) or 0
  local root,eye=sample.root,sample.eye
  local invalid=not valid(root) and "root" or (not valid(eye) and "eye" or nil)
  if not invalid and distance(root,eye)>option(cfg,"motion_max_head_distance",5,0.5,20) then
    invalid="head_distance"
  end
  if invalid then
    local first=s.invalid~=invalid
    if s.pending then
      -- Invalid intervals break the consecutive-sample evidence just as a new
      -- destination does; stale confirmation time must not survive them.
      s.pending.time,s.pending.frames=0,0
      s.pending.total_time=s.pending.total_time+dt
      s.pending.total_frames=s.pending.total_frames+1
      if first then s.pending.resets=s.pending.resets+1 end
    end
    s.invalid=invalid
    return copy(s.position),first and event("invalid_sample",invalid) or nil
  end
  local recovered=s.invalid~=nil
  s.invalid=nil
  local offset=sub(eye,root)
  if not s.root or s.authored then
    local reason=s.authored and "authored_exit" or "player_attached"
    s.authored=false; s.root=copy(root); s.offset=copy(offset)
    s.filtered=copy(offset); s.position=copy(eye); s.pending=nil
    return copy(s.position),event("reset",reason)
  end
  local rootDistance=distance(root,s.root)
  local headDistance=distance(offset,s.offset)
  local rootJump=rootDistance>option(cfg,"motion_root_jump",2.5,0.25,25)
  local headJump=headDistance>option(cfg,"motion_head_jump",0.75,0.15,5)
  local change
  if rootJump or headJump then
    local reason=rootJump and "root_discontinuity" or "head_discontinuity"
    local first=s.pending==nil
    s.pending=s.pending or {time=0,frames=0,total_time=0,total_frames=0,resets=0,
      candidate_root=copy(root),candidate_offset=copy(offset),reason=reason}
    local pending=s.pending
    local radius=option(cfg,"motion_candidate_radius",0.5,0.05,2)
    -- Elapsed time alone cannot confirm a teleport: alternating distant samples
    -- are not evidence that the actor has settled at either destination.
    if pending.reason~=reason or distance(root,pending.candidate_root)>radius
      or distance(offset,pending.candidate_offset)>radius then
      pending.time,pending.frames=0,0
      pending.resets=pending.resets+1
    end
    pending.candidate_root,pending.candidate_offset=copy(root),copy(offset)
    pending.reason=reason
    pending.time=pending.time+dt; pending.frames=pending.frames+1
    pending.total_time=pending.total_time+dt; pending.total_frames=pending.total_frames+1
    local confirmed=s.pending.frames>=2 and
      s.pending.time>=option(cfg,"motion_confirm_time",0.08,0.02,0.2)
    if not confirmed then
      -- A bad skeleton sample must not stop normal player translation.
      if not rootJump then s.root=copy(root); s.position=add(root,s.filtered) end
      return copy(s.position),first and event("jump_held",reason,
        {root_distance=rootDistance,head_distance=headDistance}) or nil
    end
    change=event("jump_settled",reason,{held_seconds=pending.total_time,held_frames=pending.total_frames,
      confirmation_seconds=pending.time,confirmation_frames=pending.frames,candidate_resets=pending.resets,
      root_distance=rootDistance,head_distance=headDistance})
    -- A real teleport settles once confirmed. Never sweep through distant walls.
    s.root=copy(root); s.offset=copy(offset); s.filtered=copy(offset)
    s.position=copy(eye); s.pending=nil
    return copy(s.position),change
  elseif s.pending then
    change=event("jump_rejected","transient_sample",
      {held_seconds=s.pending.total_time,held_frames=s.pending.total_frames,
       candidate_resets=s.pending.resets})
    s.pending=nil
  elseif recovered then
    change=event("sample_recovered","valid_transform")
  end
  local amount=1-math.exp(-dt*option(cfg,"motion_smoothing_rate",20,1,120))
  local previous=s.filtered
  local filtered={x=previous.x+(offset.x-previous.x)*amount,
    y=previous.y+(offset.y-previous.y)*amount,z=previous.z+(offset.z-previous.z)*amount}
  local lag=distance(filtered,offset)
  local maxLag=option(cfg,"motion_max_lag",0.12,0,0.5)
  if lag>maxLag and lag>0 then
    local scale=maxLag/lag
    filtered={x=offset.x+(filtered.x-offset.x)*scale,
      y=offset.y+(filtered.y-offset.y)*scale,z=offset.z+(filtered.z-offset.z)*scale}
  end
  s.root=copy(root); s.offset=copy(offset); s.filtered=filtered
  s.position=add(root,filtered)
  return copy(s.position),change
end
