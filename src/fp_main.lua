-- Original Season One adapter. No injected DLLs or EXE patches.
if TWD_FP then return end
require("fp_config.lua")
require("fp_core.lua")
require("fp_recovery.lua")
require("fp_view.lua")
require("fp_camera.lua")
require("fp_motion.lua")
require("fp_visibility.lua")
require("fp_policy.lua")
require("fp_cleanup.lua")
if FileExists("fp_generated.lua") then require("fp_generated.lua") end
require("fp_log.lua")
local logger=FP_Log
local compensation=FP_Cleanup.new(logger)
local cfg,core=FP_Config,FP_Core
local recovery,view=FP_Recovery,FP_View
local cameraPose,policy=FP_Camera,FP_Policy
local motion,visibility=FP_Motion,FP_Visibility
local motionState=motion.new()
local fallbackReason
local cameraTrace,traceFrame=nil,-1
if FP_Generated and FP_Generated.log_path then cfg.log_path=FP_Generated.log_path end
local s=core.new(cfg)
local F={version="0.5.1-experimental",state=s,config=cfg,frames=0,recovery=recovery.new(),camera_ready=false}
TWD_FP=F
local scene,player,camera,eye,gun,flash,hud,crosshair
local cameraSaved,headOverrides=nil,{}
local weaponIndex,flashTime,hitTime=0,0,0
local health,deaths,keys,failures={},{},{},{}
local captured,lastContext=false,"inactive"
local message,messageTime="",0
local closed=false
local heartbeat,positionTimer=0,0
local headKeys={}
local peekAnchor,peekOrigin
local ownedSerial={}
local components={}
local bottomName,closedScene,closedPlayer,closedTime=nil,nil,nil,0
local waitingReason,focusTarget,focusSource=nil,nil,"authored_direction"
local focusTimer,focusFrame=0,-1
local focusCutTime=0
local focusHeading,focusHeadingFrame=nil,-1
local lookCursor
local component
local closeupCameras={}
local headInvalid=false
local function owned_name(kind)
  ownedSerial[kind]=(ownedSerial[kind] or 0)+1
  return "twd_fp_"..kind.."_"..ownedSerial[kind]
end
local function log(text)
  logger.write("info","controller",{message=tostring(text),version=F.version})
end
F.log=log
local function optional(label,fn,...)
  local ok,value=logger.try(label,fn,unpack(arg))
  if ok then return value end
end
local function valid(agent) return agent~=nil and AgentIsValid(agent) end
local function hidden_avatar(agent)
  return AgentIsHidden(agent) and not visibility.camera_hidden(agent)
end
local function scene_name(value)
  if value and type(value)~="string" and ResourceGetName then value=ResourceGetName(value) end
  return policy.scene_name(value)
end
logger.context=function()
  return {mode=s.context,enabled=s.enabled,frame=F.frames,shots=s.shots,
    player=valid(player) and AgentGetName(player) or "none",scene=scene_name(scene),
    camera=valid(camera) and AgentGetName(camera) or "none",
    recovery=F.recovery.status,focus_source=focusSource,
    cleanup_pending=compensation:pending(),cleanup_blocked=compensation:blocked(),
    waiting_reason=waitingReason or "none",candidate_player=F.candidate_player or "none",
    candidate_scene=F.candidate_scene or "none",camera_policy=F.camera_policy or "none",
    focus_target=valid(focusTarget) and AgentGetName(focusTarget) or "none",
    bottom_scene=SceneGetBottomScene and scene_name(SceneGetBottomScene()) or "unknown"}
end
local function active(mode) return mode~=nil and Mode_IsActive(mode) end
local function key(code) return InputPCIsVKeyPressed(code) end
local function edge(code)
  local now=key(code)
  local pressed=now and not keys[code]
  keys[code]=now
  return pressed
end
local function notice(text) message,messageTime=text,3; log(text) end
local function release_cursor()
  if captured then
    CursorHide(false,"twd_firstperson")
    CursorConfine(active(mode_Main) and (active(mode_shotgun) or active(mode_sniper)))
    captured=false
  end
end
local function set_runtime(agent,name,value,records)
  local props=AgentGetRuntimeProperties(agent)
  if records[name]==nil or not records[name].modified then
    records[name]={local_key=PropertyExists(props,name,false),value=props[name]}
  end
  props[name]=value
  records[name].modified,records[name].applied=true,value
end
local function observe_props(agent,records)
  local props=AgentGetRuntimeProperties(agent)
  for name,previous in pairs(records) do
    if previous.modified and props[name]~=previous.applied then
      previous.local_key,previous.value=PropertyExists(props,name,false),props[name]
    end
  end
end
local function restore_props(agent,records)
  if not valid(agent) then return end
  local props=AgentGetRuntimeProperties(agent)
  for name,previous in pairs(records) do
    if previous.modified then
      if previous.local_key then props[name]=previous.value else PropertyRemove(props,name) end
      previous.modified=false
    end
  end
end
local function queue_props(agent,records,label)
  for name,previous in pairs(records) do
    local subset={[name]=previous}
    compensation:run(label..":"..name,function()
      if valid(agent) then
        -- A newer authored write takes precedence over our old saved value.
        local props=AgentGetRuntimeProperties(agent)
        if previous.modified and props[name]~=previous.applied then previous.modified=false end
        restore_props(agent,subset)
      end
    end)
  end
end
local function restore_camera()
  local old,saved=camera,cameraSaved
  camera,cameraSaved=nil,nil
  if old and saved then
    compensation:run("camera_position",function() if valid(old) then cameraPose.restore_position(old,saved) end end)
    compensation:run("camera_rotation",function() if valid(old) then cameraPose.restore_rotation(old,saved) end end)
    queue_props(old,saved.props,"camera_property")
  end
end
local function hide_head()
  if not cfg.hide_head or not valid(player) then return end
  for _,property in pairs(PropertyGetKeys(player.mProps)) do
    local name=type(property)=="string" and property or SymbolToString(property)
    local lower=string.lower(name or "")
    if string.find(lower,"^mesh ") and string.find(lower," %- visible$") then
      local part=string.match(lower,"_([^_ ]+) %- visible$") or ""
      if string.find(part,"head") or string.find(part,"hair") or string.find(part,"eye")
        or string.find(part,"teeth") or string.find(part,"tongue") or string.find(part,"mouth")
        or string.find(part,"brow") or string.find(part,"beard") or string.find(part,"hat") then
        set_runtime(player,name,false,headOverrides)
        headKeys[#headKeys+1]=name
      end
    end
  end
  if AgentIsParentProperty then
    for prefab,meshes in pairs(cfg.head_meshes or {}) do
      if AgentIsParentProperty(player,prefab) then
        for _,mesh in ipairs(meshes) do
          local name="Mesh "..mesh.." - Visible"
          if not headOverrides[name] then
            set_runtime(player,name,false,headOverrides)
            headKeys[#headKeys+1]=name
          end
        end
      end
    end
  end
  if #headKeys==0 then logger.write("warn","head_mesh_keys_missing") end
end
local function destroy(agent) if valid(agent) then AgentDestroy(agent) end end
local function queue_destroy(agent,label)
  if agent then
    -- Destruction is deferred by the engine; hide owned graphics immediately.
    optional(label.."_hide",function() if valid(agent) then AgentHide(agent,true) end end)
    compensation:run(label,function() destroy(agent) end)
  end
end
local function clear_weapon()
  local oldFlash,oldGun=flash,gun
  gun,flash,weaponIndex=nil,nil,0
  queue_destroy(oldFlash,"destroy_flash"); queue_destroy(oldGun,"destroy_weapon")
end
local function cleanup()
  optional("visibility_cleanup_error",visibility.restore)
  motion.reset(motionState)
  headInvalid=false
  fallbackReason=nil
  cameraTrace,traceFrame=nil,-1
  compensation:run("release_cursor",release_cursor)
  optional("restore_camera_error",restore_camera)
  queue_props(player,headOverrides,"restore_head")
  headOverrides,headKeys={},{}
  optional("weapon_cleanup_error",clear_weapon)
  queue_destroy(eye,"destroy_eye"); queue_destroy(hud,"destroy_hud"); queue_destroy(crosshair,"destroy_crosshair")
  eye,hud,crosshair,scene,player=nil,nil,nil,nil,nil
  health,deaths={},{}
  s.reload_left,s.aim,s.trigger=0,0,true
  s.context,s.paused_from="inactive",nil
  lastContext="inactive"
  peekAnchor,peekOrigin=nil,nil
  F.camera_ready=false
  focusTarget,focusTimer,focusFrame=nil,0,-1
  focusCutTime=0
  focusHeading,focusHeadingFrame=nil,-1
  s.look_idle=0
  lookCursor=nil
end
F.cleanup=cleanup
function F.recover()
  compensation:reset(); cleanup(); recovery.reset(F.recovery); components={}; waitingReason=nil
  logger.write("info","recovery_reset",{reason="manual"})
end
function F.toggle()
  s.enabled=not s.enabled
  F.recover()
  notice(s.enabled and "First person ON" or "Original camera restored")
end
local function station_camera()
  local candidateScene=scene or (SceneGetBottomScene and SceneGetBottomScene())
  local current=candidateScene and SceneGetCamera(candidateScene)
  local station=Station_GetCurrent and Station_GetCurrent()
  -- The current station can outlive its camera during cutscenes. Match ancestry.
  for depth=1,12 do
    if not valid(current) then return false end
    if current==station or (AgentIsParentProperty and AgentIsParentProperty(current,"cam_station.prop")) then return true end
    current=AgentGetParent and AgentGetParent(current)
  end
  return false
end
local function closeup_camera()
  local current=SceneGetCamera(scene or SceneGetBottomScene())
  for depth=1,12 do
    if not valid(current) then return false end
    if closeupCameras[AgentGetName(current)] then return true end
    current=AgentGetParent and AgentGetParent(current)
  end
  return false
end
if Game_EnterCloseUp then
  local enter=Game_EnterCloseUp
  Game_EnterCloseUp=function(cam,...)
    local result=enter(cam,unpack(arg))
    closeupCameras[type(cam)=="string" and cam or AgentGetName(cam)]=true
    logger.write("info","closeup_enter",{closeup=tostring(cam)})
    return result
  end
end
if Game_ExitCloseUp then
  local leave=Game_ExitCloseUp
  Game_ExitCloseUp=function(cam,...)
    local result=leave(cam,unpack(arg))
    closeupCameras[type(cam)=="string" and cam or AgentGetName(cam)]=nil
    logger.write("info","closeup_exit",{closeup=tostring(cam)})
    return result
  end
end
local function context()
  return policy.context({main=active(mode_Main),dialogue=active(mode_DialogChoice),
    action_choice=active(mode_DialogActionChoice),direction_choice=active(mode_choice),
    qte=active(mode_Struggle) or active(mode_balance) or InputMapperIsActive("struggle.imap"),peek=active(mode_peek),
    combat=active(mode_shotgun) or active(mode_sniper),station=station_camera(),closeup=closeup_camera(),
    cinematic=active(mode_Cutscene_Movement) or active(mode_Cutscene_Interaction),
    presentation=policy.presentation(scene_name(SceneGetBottomScene())),
    explore=active(mode_thirdperson) and active(mode_Reticle) and InputMapperIsActive("Navigate")})
end
local function full_cutscene_look()
  return cfg.cutscene_free_look and active(mode_Cutscene_Movement) and active(mode_Cutscene_Interaction)
end
local function resolve_player()
  local bottom=SceneGetBottomScene and SceneGetBottomScene() or nil
  local function current(agent)
    if valid(agent) then F.candidate_player,F.candidate_scene=AgentGetName(agent),scene_name(AgentGetScene(agent)) end
    return valid(agent) and (not bottom or scene_name(AgentGetScene(agent))==scene_name(bottom))
  end
  F.candidate_player,F.candidate_scene=nil,nil
  local candidate=Main_GetAvatar and Main_GetAvatar() or nil
  if current(candidate) then return candidate end
  if Game_GetPlayer then candidate=Game_GetPlayer() end
  if current(candidate) then return candidate end
  for _,name in ipairs({"Lee","Clementine","Vince","Wyatt","Russell","Bonnie","Shel"}) do
    if AgentExists(name) then
      candidate=AgentFind(name)
      if current(candidate) then return candidate end
    end
  end
end
local function setup(candidate)
  cleanup()
  player,scene=candidate,AgentGetScene(candidate)
  eye=AgentCreate(owned_name("eye"),"module_null.prop",Vector(0,0,0),Vector(0,0,0),scene,false,false)
  if AgentHasNode(player,"head") then
    AgentAttachToNode(eye,player,"head",false)
    AgentSetPos(eye,Vector(0,0,0)); AgentSetRot(eye,Vector(0,0,0))
  else
    AgentAttach(eye,player,false); AgentSetPos(eye,Vector(0,cfg.fallback_eye_height,0))
  end
  hide_head()
  s.yaw,s.pitch=AgentGetWorldRot(player).y,0
  logger.write("info","player_attached",{has_head=AgentHasNode(player,"head"),hidden_meshes=#headKeys})
  for _,weapon in ipairs(cfg.weapons) do
    local resource="none"
    for _,name in ipairs(weapon.props) do if FileExists(name) then resource=name; break end end
    logger.write("info","weapon_capability",{weapon=weapon.id,available=resource~="none",resource=resource})
  end
end
local function update_focus()
  if focusFrame==F.frames then return end
  focusFrame=F.frames
  focusCutTime=math.max(0,focusCutTime-core.clamp(GetFrameTime(),0,0.1))
  focusTimer=focusTimer-core.clamp(GetFrameTime(),0,0.1)
  if focusTimer>0 then return end
  focusTimer=0.35
  local target,source=nil,"authored_direction"
  local function usable(a)
    return valid(a) and a~=player and a~=camera and a~=gun and a~=eye and a~=flash
      and scene_name(AgentGetScene(a))==scene_name(scene) and not AgentIsHidden(a)
  end
  for _,owner in ipairs({camera,player}) do
    local name=owner.mProps["Look At - Agent"]
    if owner.mProps["Look At - Enabled"]~=false and type(name)=="string" and name~="" and AgentExists(name) then
      local a=AgentFind(name)
      if usable(a) then target,source=a,"authored_look_target"; break end
    end
  end
  -- When no explicit look target exists, infer the actor nearest the shot axis.
  -- This is a framing hint, not a claim to understand the scene's narrative.
  if not target and SceneGetAgents then
    local origin,forward=cameraSaved.authorPos,cameraSaved.authorForward
    local best=0.85
    for _,a in ipairs(SceneGetAgents(scene)) do
      if usable(a) and AgentHasNode(a,"head") then
        local p=AgentGetWorldPos(a,"head")
        local d=VectorDistance(p,origin)
        if d>0.1 and d<40 then
          local score=((p.x-origin.x)*forward.x+(p.y-origin.y)*forward.y+(p.z-origin.z)*forward.z)/d
          if score>best then best,target,source=score,a,"shot_axis_actor" end
        end
      end
    end
    if target~=focusTarget and focusSource=="shot_axis_actor" and usable(focusTarget) then
      local p=AgentGetWorldPos(focusTarget,"head")
      local d=VectorDistance(p,origin)
      if d>0.1 and d<40 then
        local score=((p.x-origin.x)*forward.x+(p.y-origin.y)*forward.y+(p.z-origin.z)*forward.z)/d
        if score>=0.85 and score>=best-0.04 then target,source=focusTarget,"shot_axis_actor" end
      end
    end
  end
  if target~=focusTarget or source~=focusSource then
    focusTarget,focusSource=target,source
    logger.write("info","focus_changed")
  end
end
local function focus_heading(pos)
  update_focus()
  if focusCutTime>0 and focusHeading then return focusHeading end
  local base=cameraSaved.authorRot
  local pitch,yaw=base.x,base.y
  if valid(focusTarget) then
    local target=AgentHasNode(focusTarget,"head") and AgentGetWorldPos(focusTarget,"head") or AgentGetWorldPos(focusTarget)
    local p,y=view.direction(pos,target)
    if p then pitch,yaw=p,y end
  end
  if not focusHeading then focusHeading=Vector(pitch,yaw,base.z)
  elseif focusHeadingFrame~=F.frames then
    local amount=1-math.exp(-core.clamp(GetFrameTime(),0,0.1)*10)
    focusHeading=Vector(focusHeading.x+(pitch-focusHeading.x)*amount,
      core.wrap(focusHeading.y+core.wrap(yaw-focusHeading.y)*amount),base.z)
  end
  focusHeadingFrame=F.frames
  return focusHeading
end
local function update_camera(ctx)
  local current=SceneGetCamera(scene)
  if not valid(current) then F.camera_ready=false; release_cursor(); return false end
  if current~=camera then
    local continuous=valid(camera) and F.camera_policy=="player_eye" and not policy.authored(ctx)
      and not hidden_avatar(player) and not key(cfg.cursor_key)
    restore_camera(); camera=current
    cameraSaved=cameraPose.snapshot(camera)
    peekAnchor,peekOrigin=nil,nil
    if continuous then
      -- One-frame native cuts must not reset user look or the focus heading.
      focusTimer=cfg.focus_cut_delay
      focusCutTime=cfg.focus_cut_delay
    else
      focusTarget,focusTimer,focusFrame=nil,0,-1
      focusHeading,focusHeadingFrame=nil,-1
      focusCutTime=0
      if ctx~="explore" and ctx~="combat" then s.yaw,s.pitch=0,0 end
    end
    logger.write("info","camera_changed",{continuous=continuous})
  end
  cameraPose.observe(camera,cameraSaved)
  observe_props(camera,cameraSaved.props)
  if cameraSaved.context~=ctx then restore_props(camera,cameraSaved.props); cameraSaved.context=ctx end
  assert(view.valid(cameraSaved.authorPos) and view.valid(cameraSaved.authorRot),"Invalid authored camera transform")
  -- Query the animated skeleton directly. A newly attached proxy can retain
  -- yesterday's transform until the engine's attachment update on some cuts.
  local root=AgentGetWorldPos(player)
  assert(view.valid(root),"Invalid player root transform")
  local skeletonEye=AgentHasNode(player,"head")
  local invalidHead=false
  local pos
  if skeletonEye then pos=AgentGetWorldPos(player,"head")
  else pos=VectorAdd(root,Vector(0,cfg.fallback_eye_height,0)) end
  if not view.valid(pos) or VectorDistance(pos,root)>5 then
    if not headInvalid then
      logger.write("warn","head_position_invalid",{x=pos and pos.x,y=pos and pos.y,z=pos and pos.z})
    end
    pos=VectorAdd(root,Vector(0,cfg.fallback_eye_height,0))
    skeletonEye=false
    invalidHead=true
  end
  if headInvalid and not invalidHead then logger.write("info","head_position_recovered") end
  headInvalid=invalidHead
  local heading
  local policyReason=policy.authored(ctx) and ctx or
    (key(cfg.cursor_key) and "manual_cursor" or (hidden_avatar(player) and "hidden_avatar" or "player_eye"))
  local authored=policyReason~="player_eye"
  F.head_height=pos.y-root.y
  F.eye_source=skeletonEye and "animated_head" or "fallback"
  F.eye_lift=authored and 0 or (skeletonEye and view.eye_lift(F.head_height,cfg) or cfg.low_pose_head_up)
  -- Aim from the final eye height, so the focus point stays under the cursor.
  if not authored then pos.y=pos.y+F.eye_lift end
  F.eye_target=Vector(pos.x,pos.y,pos.z)
  local dt=core.clamp(GetFrameTime(),0,0.1)
  local filtered,motionEvent=motion.update(motionState,{eye=authored and cameraSaved.authorPos or pos,
    root=root,identity=player,authored=authored},dt,F.frames,cfg)
  if motionEvent then
    logger.write("info","camera_motion",motionEvent)
  end
  -- A valid relocation stays in first person. An authored-camera detour adds
  -- two unrelated cuts and can be farther away than the actor's actual move.
  local nextFallback=not authored and invalidHead and "invalid_head" or nil
  if nextFallback~=fallbackReason then
    if fallbackReason then logger.write("info","camera_fallback",{reason=fallbackReason,stage="exit"}) end
    fallbackReason=nextFallback
    if fallbackReason then logger.write("info","camera_fallback",{reason=fallbackReason,stage="enter"}) end
  end
  authored=authored or fallbackReason~=nil
  F.camera_policy=fallbackReason and "authored_fallback" or (authored and "authored" or "player_eye")
  F.motion_state=motionState.pending and "holding" or (fallbackReason and "fallback" or "tracking")
  if filtered and not authored then pos=Vector(filtered.x,filtered.y,filtered.z) end
  if authored then
    -- Station01 at the motel is over 30m from crouching Lee. Its authored
    -- projection is part of the interaction puzzle; a head offset breaks it.
    pos=Vector(cameraSaved.authorPos.x,cameraSaved.authorPos.y,cameraSaved.authorPos.z)
    local rotation=cameraSaved.authorRot
    heading=Vector(core.clamp(rotation.x+s.pitch,-89,89),rotation.y+s.yaw,0)
    if (fallbackReason and ctx=="explore") or
      not policy.mouse_look(ctx,{right=key(2),alt=key(cfg.cursor_key),full_cutscene=full_cutscene_look()}) then
      heading=Vector(rotation.x,rotation.y,rotation.z)
    end
  elseif ctx=="explore" then
    heading=Vector(s.pitch-s.recoil,s.yaw,0)
  else
    local base=component("focus",focus_heading,pos) or cameraSaved.authorRot
    heading=Vector(core.clamp(base.x+s.pitch,-89,89),base.y+s.yaw,cfg.cinematic_roll and base.z or 0)
  end
  assert(view.valid(pos) and view.valid(heading),"Invalid first-person camera transform")
  AgentSetWorldRot(camera,heading)
  if not authored then
    pos=VectorAdd(pos,VectorScale(AgentGetForwardVec(camera,true),cfg.head_forward))
  end
  AgentSetWorldPos(camera,pos)
  -- The engine canonicalizes Euler angles (including equivalent 180-degree
  -- representations). Compare subsequent updates to the read-back transform.
  cameraPose.applied(camera,cameraSaved)
  local traceReason=fallbackReason or policyReason
  local traceDistance=cameraTrace and VectorDistance(cameraTrace.pos,pos) or 0
  local policyChanged=cameraTrace and (cameraTrace.policy~=F.camera_policy or cameraTrace.reason~=traceReason)
  if not cameraTrace or policyChanged or (traceFrame~=F.frames and traceDistance>cfg.motion_root_jump) then
    logger.write("info","camera_transition",{reason=traceReason,
      trigger=motionEvent and motionEvent.kind or (policyChanged and "policy_change" or "render_displacement"),
      previous_policy=cameraTrace and cameraTrace.policy or "none",next_policy=F.camera_policy,
      from_x=cameraTrace and cameraTrace.pos.x,from_y=cameraTrace and cameraTrace.pos.y,
      from_z=cameraTrace and cameraTrace.pos.z,to_x=pos.x,to_y=pos.y,to_z=pos.z,
      distance=traceDistance,root_distance=cameraTrace and VectorDistance(cameraTrace.root,root) or 0,
      alt=key(cfg.cursor_key),player_hidden=AgentIsHidden(player)})
  end
  if traceFrame~=F.frames or policyChanged or not cameraTrace then
    cameraTrace={pos=Vector(pos.x,pos.y,pos.z),root=Vector(root.x,root.y,root.z),
      policy=F.camera_policy,reason=traceReason}; traceFrame=F.frames
  end
  if authored then restore_props(camera,cameraSaved.props)
  else
    set_runtime(camera,"Field of View",cfg.fov+(cfg.aim_fov-cfg.fov)*s.aim,cameraSaved.props)
    set_runtime(camera,"Clip Plane - Near",cfg.near_clip,cameraSaved.props)
    set_runtime(camera,"Depth Of Field Enabled",false,cameraSaved.props)
  end
  if ctx=="explore" and not authored then
    -- Native DirectControl otherwise follows a fixed authored axis agent.
    set_runtime(camera,"NavCam - Direct Control Axis Agent","",cameraSaved.props)
    set_runtime(camera,"NavCam - Direct Control Axis Update",true,cameraSaved.props)
  end
  -- Chores may animate mesh visibility after setup; reapply only known keys.
  if authored then restore_props(player,headOverrides)
  else for _,name in ipairs(headKeys) do set_runtime(player,name,false,headOverrides) end end
  visibility.update(cfg.camera_visibility and not authored,scene,player)
  if ctx=="explore" and (authored or F.motion_state=="holding") then release_cursor() end
  F.camera_ready=true
  return true
end
local function ensure_weapon()
  if valid(gun) and weaponIndex==s.weapon then return true end
  clear_weapon()
  local weapon=cfg.weapons[s.weapon]
  for _,resource in ipairs(weapon.props) do
    if FileExists(resource) then
      gun=AgentCreate(owned_name("weapon"),resource,nil,nil,scene,true,false)
      if valid(gun) then break end
    end
  end
  if not valid(gun) then
    if not failures[weapon.id] then failures[weapon.id]=true; notice(weapon.label.." model unavailable in this episode") end
    assert(false,"Weapon model unavailable: "..weapon.id)
  end
  AgentSetSelectable(gun,false)
  if FileExists(weapon.flash) then
    flash=AgentCreate(owned_name("flash"),weapon.flash,nil,nil,scene,true,false)
    if valid(flash) then AgentSetSelectable(flash,false) end
  end
  weaponIndex=s.weapon
  logger.write("info","weapon_created",{weapon=weapon.id,agent=AgentGetName(gun)})
  return true
end
local function update_weapon(ctx)
  if not cfg.free_weapons or not s.drawn or ctx~="explore" or F.camera_policy~="player_eye"
    or F.motion_state=="holding" then
    if valid(gun) then AgentHide(gun,true) end
    if valid(flash) then AgentHide(flash,true) end
    return false
  end
  if not ensure_weapon() or not valid(camera) then return false end
  local w=cfg.weapons[s.weapon]
  local offset=Vector(w.offset.x+(w.aim_offset.x-w.offset.x)*s.aim,
    w.offset.y+(w.aim_offset.y-w.offset.y)*s.aim,w.offset.z+(w.aim_offset.z-w.offset.z)*s.aim)
  offset.z=offset.z-s.recoil*0.012
  local tilt=0
  if s.reload_left>0 then
    local wave=math.sin((1-s.reload_left/w.reload)*math.pi)
    offset.y,tilt=offset.y-wave*0.22,wave*30
  end
  AgentSetWorldPos(gun,AgentLocalToWorld(camera,offset))
  local rot=AgentGetWorldRot(camera)
  AgentSetWorldRot(gun,Vector(rot.x+w.rotation.x-s.recoil*2+tilt,rot.y+w.rotation.y,rot.z+w.rotation.z))
  AgentHide(gun,false)
  if valid(flash) then
    AgentSetWorldPos(flash,AgentLocalToWorld(gun,Vector(0,0,0.28)))
    AgentSetWorldRot(flash,AgentGetWorldRot(gun)); AgentHide(flash,flashTime<=0)
  end
  return true
end
local function walker(agent)
  local name=string.lower(AgentGetName(agent))
  if string.find(name,"zombie") or string.find(name,"walker") or AgentHasProperty(agent,"Zombie - Die") then return true end
  for _,property in pairs(PropertyGetKeys(agent.mProps)) do
    local text=type(property)=="string" and property or SymbolToString(property)
    if text and string.find(string.lower(text),"^mesh .*zombie") then return true end
  end
  return false
end
local function damage(agent,amount)
  if not valid(agent) or agent==player or agent==gun or deaths[agent] then return false end
  if not AgentHasNode(agent,"head") then return false end
  local isWalker=walker(agent)
  if not ((isWalker and cfg.damage_walkers) or (not isWalker and cfg.damage_story_characters)) then return false end
  health[agent]=core.health_after(health[agent] or 100,amount,false)
  hitTime=0.15
  if health[agent]>0 then return true end
  deaths[agent]=true
  if AgentHasProperty(agent,"Zombie - Die") then
    agent.mProps["Zombie - Die"]=true
  else
    local animation="sk55_zombieaveragewalka_headshot.anm"
    if isWalker and FileExists(animation) then
      local controller=PlayAnimation(agent,animation)
      ControllerSetLooping(controller,false); ControllerSetEndPause(controller,true)
      ControllerSetPriority(controller,100)
    else AgentHide(agent,true) end
    AgentSetSelectable(agent,false)
  end
  log("Free-fire defeat: "..AgentGetName(agent))
  return true
end
local function fire()
  local w=cfg.weapons[s.weapon]
  flashTime=0.065
  local count=0
  -- Exclude the player's body and view model from the engine screen pick.
  local playerHidden=AgentIsHidden(player)
  AgentHide(player,true); AgentHide(gun,true)
  local ok,err=xpcall(function()
    for pellet=1,w.pellets do
      local x,y=0.5,0.5
      if w.pellets>1 then
        local angle=(pellet-1)*2*math.pi/w.pellets
        x,y=x+math.cos(angle)*w.spread,y+math.sin(angle)*w.spread
      end
      local target=AgentAtScreenPos(Vector(x,y,0),true,scene)
      if valid(target) and VectorDistance(AgentGetWorldPos(camera),AgentGetWorldPos(target))<=w.range then
        if damage(target,w.damage) then count=count+1 end
      end
    end
  end,logger.traceback)
  AgentHide(player,playerHidden); AgentHide(gun,false)
  if not ok then assert(false,err) end
  SoundPlay(w.sound)
  log("Shot "..w.id..", ammo="..s.magazines[s.weapon]..", damaging hits="..count)
end
local function update_hud(ctx)
  if not cfg.show_hud then return end
  local uiScene=AgentExists("ui_reticle_parent") and AgentGetScene(AgentFind("ui_reticle_parent")) or nil
  if not uiScene then return end
  if not valid(hud) or not valid(crosshair) or AgentGetScene(hud)~=uiScene then
    queue_destroy(hud,"replace_hud"); queue_destroy(crosshair,"replace_crosshair")
    hud,crosshair=nil,nil
    hud=AgentCreate(owned_name("hud"),"ui_text.prop",nil,nil,uiScene,false,false)
    hud.mProps["Text Font"]="Arial_30.font"
    hud.mProps["Text Alignment Horizontal"]="Left Justified"
    hud.mProps["Text Scale"]=0.7
    AgentSetSelectable(hud,false)
    crosshair=AgentCreate(owned_name("crosshair"),"ui_text.prop",nil,nil,uiScene,false,false)
    crosshair.mProps["Text Font"]="Arial_30.font"
    crosshair.mProps["Text Alignment Horizontal"]="Center"
    AgentSetSelectable(crosshair,false)
  end
  local visible=ctx=="explore" or messageTime>0
  AgentHide(hud,not visible)
  AgentHide(crosshair,ctx~="explore" or not s.drawn or key(cfg.cursor_key)
    or F.camera_policy~="player_eye" or F.motion_state=="holding")
  if visible then
    local w=cfg.weapons[s.weapon]
    local text="FP | G: draw | F6: camera | Alt: cursor"
    if s.drawn then
      text=w.label.."  "..s.magazines[s.weapon].."/"..w.capacity.."  R: reload  F: use"
      if s.reload_left>0 then text=text.."  RELOADING" end
    end
    hud.mProps["Text String"]=messageTime>0 and message or text
    AgentSetWorldPosFromScreenPos(hud,Vector(0.025,0.93,0))
    crosshair.mProps["Text String"]=hitTime>0 and "x" or "+"
    AgentSetWorldPosFromScreenPos(crosshair,Vector(0.5,0.5,0))
  end
end
component=function(name,fn,...)
  local r=components[name]
  if not r then r=recovery.new(); components[name]=r end
  if not recovery.ready(r) then return false end
  local ok,value=logger.try(name.."_error",fn,unpack(arg))
  if ok then
    if recovery.success(r) then logger.write("info","component_recovered",{component=name}) end
    return value
  end
  local status,attempt,delay=recovery.fail(r)
  logger.write("warn","component_recovery",{component=name,status=status,attempt=attempt,delay=delay})
  if status=="blocked" and (name=="weapon" or name=="fire") then
    s.drawn=false; notice("Weapon recovery paused. F8 retries.")
  end
  if name=="weapon" or name=="fire" then optional("weapon_recovery_cleanup",clear_weapon)
  elseif name=="hud" then
    queue_destroy(hud,"recover_hud"); queue_destroy(crosshair,"recover_crosshair")
    hud,crosshair=nil,nil
  elseif name=="focus" then focusTarget,focusSource=nil,"authored_direction"
  end
  return false
end
local function wants_free_input()
  return s.enabled and F.recovery.status=="active" and F.camera_ready and not closed
    and F.camera_policy=="player_eye" and F.motion_state~="holding"
    and context()=="explore" and valid(player) and not hidden_avatar(player) and not key(cfg.cursor_key)
end
local function swallow_click() return wants_free_input() and s.drawn and valid(gun) and weaponIndex==s.weapon end
local function guarded(predicate)
  local ok,result=logger.try("input_guard_error",predicate)
  return ok and result
end
local function wrap_global(name,predicate)
  local original=_G[name]
  if type(original)~="function" then return end
  _G[name]=function(...)
    if guarded(predicate) then return end
    return original(unpack(arg))
  end
end
for _,name in ipairs({"Navigate_OnMouseL","Navigate_OnMouseLDouble","Navigate_OnMouseLUp"}) do wrap_global(name,swallow_click) end
for _,name in ipairs({"Navigate_OnMouseR","Navigate_OnMouseRUp","Navigate_OnMouseMove"}) do wrap_global(name,wants_free_input) end
if mode_Reticle then
  local original=mode_Reticle.OnMouseDown
  mode_Reticle.OnMouseDown=function(self,event)
    if not guarded(swallow_click) then return original(self,event) end
  end
  local choice=mode_Reticle.OnChoice
  mode_Reticle.OnChoice=function(self,event)
    if not guarded(swallow_click) then return choice(self,event) end
  end
end
local originalReticleUpdate=ReticleController_Update
ReticleController_Update=function(...)
  if guarded(wants_free_input) then ReticleController_SetScreenPos(0.5,0.5); return end
  -- The native reticle recenters the physical cursor. Read it before that
  -- happens, but still run its choice/QTE/controller updates unchanged.
  if s.enabled and F.camera_ready and F.recovery.status=="active" and captured then
    lookCursor=CursorGetPos()
  end
  return originalReticleUpdate(unpack(arg))
end
local function waiting(reason)
  F.camera_ready=false; release_cursor()
  if reason~=waitingReason then
    waitingReason=reason; logger.write("info","adapter_waiting",{reason=reason})
  end
end
local function frame()
  local candidate=resolve_player()
  if not valid(candidate) then if player then cleanup() end; waiting("player"); return end
  local ctx=context()
  if hidden_avatar(candidate) and ctx=="explore" then ctx="scripted" end
  if ctx=="paused" then
    visibility.update(false,scene,player)
    release_cursor(); core.set_context(s,ctx)
    if valid(hud) then AgentHide(hud,true) end
    if valid(crosshair) then AgentHide(crosshair,true) end
    return
  end
  if candidate~=player or AgentGetScene(candidate)~=scene or not valid(eye) then setup(candidate) end
  if not valid(SceneGetCamera(scene)) then
    waiting("camera"); component("weapon",update_weapon,"inactive"); return
  end
  if waitingReason then logger.write("info","adapter_resumed",{reason=waitingReason}); waitingReason=nil end
  if ctx~=lastContext then
    if ctx=="explore" or ctx=="combat" then
      local rot=valid(camera) and AgentGetWorldRot(camera) or AgentGetWorldRot(player)
      s.yaw,s.pitch=rot.y,core.clamp(rot.x,-cfg.pitch_limit,cfg.pitch_limit)
    elseif policy.authored(ctx) or policy.authored(lastContext) or lastContext=="explore"
      or lastContext=="inactive" or lastContext=="paused" then s.yaw,s.pitch=0,0 end
    s.look_idle=0
    lastContext=ctx; log("Mode: "..ctx)
    if ctx~="peek" then peekAnchor,peekOrigin=nil,nil end
  end
  core.set_context(s,ctx)
  local dt=core.clamp(GetFrameTime(),0,0.1)
  flashTime,hitTime,messageTime=math.max(0,flashTime-dt),math.max(0,hitTime-dt),math.max(0,messageTime-dt)
  local cursorFree=key(cfg.cursor_key)
  local look=policy.mouse_look(ctx,{right=key(2),alt=cursorFree,full_cutscene=full_cutscene_look()})
  if ctx=="explore" and (motionState.pending or headInvalid) then look=false end
  local dx,dy=0,0
  if look then
    if captured then
      local pos=lookCursor or CursorGetPos()
      dx,dy=core.clamp(pos.x-0.5,-0.45,0.45),core.clamp(pos.y-0.5,-0.45,0.45)
    else
      captured=true; CursorHide(true,"twd_firstperson"); CursorConfine(true)
    end
    CursorSetAtScreenCenter()
  else release_cursor() end
  lookCursor=nil
  if policy.authored(ctx) and not look then s.yaw,s.pitch=0,0 end
  local drawPressed,reloadPressed,usePressed=edge(cfg.draw_key),edge(cfg.reload_key),edge(cfg.use_key)
  for i=1,#cfg.weapons do
    if edge(48+i) and ctx=="explore" and s.drawn and not cursorFree then core.select(s,i,cfg) end
  end
  if ctx=="explore" and not cursorFree then
    if drawPressed and cfg.free_weapons then
      s.drawn=not s.drawn; s.reload_left=0; s.trigger=true
      notice(s.drawn and "Weapon drawn" or "Weapon holstered")
    end
    if reloadPressed and core.reload(s,cfg) then SoundPlay("wpn_gun_load_1.wav") end
    if usePressed and mode_Reticle and Reticle_SomethingHasFocus() then
      ThreadStart(function() mode_Reticle:DoAction() end)
    end
  end
  if not update_camera(ctx) then return end
  local ready=component("weapon",update_weapon,ctx)
  if F.camera_policy~="player_eye" or F.motion_state=="holding" then ready=false end
  if components.fire and not recovery.ready(components.fire) then ready=false end
  local events=core.update(s,dt,{fire=key(1),aim=key(2),look=look,dx=dx,dy=dy,cursor=cursorFree,weapon_ready=ready},cfg)
  if ctx~="explore" and ctx~="combat" and ctx~="station" and ctx~="peek" then
    view.assist(s,dt,math.abs(dx)+math.abs(dy)>0.0001,key(cfg.focus_key),cfg)
  elseif (ctx=="station" or ctx=="peek") and key(cfg.focus_key) then s.yaw,s.pitch=0,0 end
  update_camera(ctx)
  if events.fired then
    component("fire",fire)
    -- Apply kick after the hit query so the bullet follows the visible aim.
    s.recoil=s.recoil+(events.recoil or 0)
    update_camera(ctx)
  end
  if events.reloaded then logger.write("info","reload_complete",{weapon=cfg.weapons[s.weapon].id}) end
  if events.empty then SoundPlay("wpn_handgun_empty_chamber_click.wav"); notice("Empty - press R to reload") end
  component("weapon",update_weapon,ctx); component("hud",update_hud,ctx)
  if ctx=="explore" and DirectControl_OnCameraChange then DirectControl_OnCameraChange(camera) end
  positionTimer=positionTimer+dt
  if positionTimer>=2 then
    positionTimer=0
    local p,c=AgentGetWorldPos(player),AgentGetWorldPos(camera)
    local actual=SceneGetCamera(scene)
    logger.write("info","position_sample",{player_x=p.x,player_y=p.y,player_z=p.z,
      camera_x=c.x,camera_y=c.y,camera_z=c.z,yaw=s.yaw,pitch=s.pitch,
      head_height=F.head_height,eye_lift=F.eye_lift,eye_height=c.y-p.y,eye_source=F.eye_source,
      player_hidden=AgentIsHidden(player),player_camera_hidden=visibility.camera_hidden(player),motion_state=F.motion_state,
      motion_hold_seconds=motionState.pending and motionState.pending.total_time or 0,
      eye_target_x=F.eye_target.x,eye_target_y=F.eye_target.y,eye_target_z=F.eye_target.z,
      fov=camera.mProps["Field of View"],near_clip=camera.mProps["Clip Plane - Near"],
      far_clip=camera.mProps["Clip Plane - Far"],cull_objects=camera.mProps["Cull Objects"],
      w=key(87),a=key(65),s=key(83),d=key(68),navigate=InputMapperIsActive("Navigate"),
      thirdperson=active(mode_thirdperson),peek=active(mode_peek),
      station=ctx=="station",cursor_captured=captured,
      closeup=ctx=="closeup",qte=ctx=="qte",combat=ctx=="combat",choice=ctx=="choice",
      interaction_view=policy.authored(ctx) and not look,
      camera_pitch=AgentGetWorldRot(camera).x,camera_yaw=AgentGetWorldRot(camera).y,
      author_pitch=cameraSaved.authorRot.x,author_yaw=cameraSaved.authorRot.y,
      cursor_x=CursorGetPos().x,cursor_y=CursorGetPos().y,
      peek_moving=Peek_MoveInProgress and Peek_MoveInProgress() or false,
      author_x=cameraSaved.authorPos.x,author_y=cameraSaved.authorPos.y,author_z=cameraSaved.authorPos.z,
      actual_camera=valid(actual) and AgentGetName(actual) or "none"})
    component("visibility_sample",visibility.sample,scene,player)
  end
end
local previousPostUpdate=EnginePostUpdate
local function supervise()
  local dt=core.clamp(GetFrameTime(),0,0.1)
  compensation:tick(dt)
  visibility.tick(dt)
  recovery.advance(F.recovery,dt)
  for _,r in pairs(components) do recovery.advance(r,dt) end
  if edge(cfg.toggle_key) then F.toggle() end
  if edge(cfg.recover_key) then F.recover() end
  local bottom=scene_name(SceneGetBottomScene())
  if bottom~=bottomName then
    bottomName=bottom; closeupCameras={}
    cleanup(); recovery.reset(F.recovery); compensation:reset(); components={}
    logger.write("info","scene_detected",{detected_scene=bottom})
  end
  if closed then
    closedTime=closedTime+dt
    -- Recover a missed open callback only once a different valid scene/avatar
    -- is active. Never reattach to the old scene while it is being destroyed.
    if closedTime>=2 and active(mode_Main) then
      local candidate=resolve_player()
      if valid(candidate) and (bottom~=closedScene or candidate~=closedPlayer) then
        closed=false; recovery.reset(F.recovery)
        logger.write("warn","scene_callback_recovered")
      end
    end
    if closed then return end
  end
  if compensation:pending()>0 then
    -- A failed teardown may originate in a weapon/HUD swap while the camera
    -- is still active. Restore all active ownership before suspending updates.
    if player or camera or eye or gun or hud or crosshair then cleanup() end
    if compensation:blocked()>0 and F.recovery.status~="blocked" then
      F.recovery.status="blocked"; logger.write("warn","cleanup_blocks_recovery")
    end
    waiting("cleanup"); return
  end
  if not s.enabled or not recovery.ready(F.recovery) then return end
  frame()
  if recovery.success(F.recovery) then logger.write("info","controller_recovered") end
end
function EnginePostUpdate(...)
  local originalOK,originalError=logger.try("original_post_update_error",previousPostUpdate,unpack(arg))
  if not originalOK then assert(false,originalError) end
  F.frames=F.frames+1
  heartbeat=heartbeat+math.max(0,math.min(GetFrameTime(),0.1))
  if heartbeat>=10 then
    heartbeat=0; logger.write("info","heartbeat",{closed=closed,errors=logger.errors,warnings=logger.warnings})
  end
  local ok,err=logger.try("frame_error",supervise)
  if not ok then
    local status,attempt,delay=recovery.fail(F.recovery)
    optional("error_cleanup",cleanup)
    logger.write("warn","controller_recovery",{status=status,attempt=attempt,delay=delay,
      message=status=="blocked" and "Original controls restored. F8 or next scene retries." or "Retry scheduled"})
  end
end
Callback_OnGameSceneClose:Add(function(name)
  logger.write("info","scene_close",{next_script=tostring(name)})
  closedScene,closedPlayer,closedTime=bottomName,player,0
  closed=true; optional("scene_cleanup_error",cleanup)
end)
Callback_SceneOpenFinished:Add(function(value)
  local opened=scene_name(value)
  if value and (opened~=scene_name(SceneGetBottomScene()) or string.find(opened,"^ui_")) then
    logger.write("info","scene_open_ignored",{opened_scene=opened}); return
  end
  closed=false; recovery.reset(F.recovery); compensation:reset(); components={}
  logger.write("info","scene_open",{opened_scene=scene_name(value)})
end)
if Callback_AppExit then
  Callback_AppExit:Add(function()
    optional("exit_cleanup_error",cleanup)
    logger.write("info","session_end",{errors=logger.errors,warnings=logger.warnings})
  end)
end
if FP_Generated and FP_Generated.native_test then
  F.testing={setup=setup,update_camera=update_camera,ensure_weapon=ensure_weapon,
    update_weapon=update_weapon,cleanup=cleanup,context=context,station_camera=station_camera,
    set_focus=function(target)
      focusTarget,focusSource,focusTimer,focusFrame=target,"native_fixture",10,F.frames
      focusHeading,focusHeadingFrame=nil,-1
    end,
    get=function() return player,camera,eye,gun end}
  require("fp_native_tests.lua")
end
log("Bootstrap loaded. F6 camera; F8 recover; Tab focus; G weapon.")
