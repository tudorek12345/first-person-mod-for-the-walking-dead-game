-- Deliberately small API fixture, NOT an emulator or evidence of in-game behavior.
Fake={agents={},keys={},cursor={x=0.5,y=0.5,z=0},logs={},time=0,originalUpdates=0,
      nativeClicks=0,nativeChoices=0,sounds={},confined=false,hit=nil}
io=nil
function print(text) table.insert(Fake.logs,tostring(text)) end
function Vector(x,y,z)
  if type(x)=="table" then return {x=x.x,y=x.y,z=x.z} end
  return {x=x or 0,y=y or 0,z=z or 0}
end
function VectorAdd(a,b) return Vector(a.x+b.x,a.y+b.y,a.z+b.z) end
function VectorScale(a,b) return Vector(a.x*b,a.y*b,a.z*b) end
function VectorDistance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2) end
function Fake.new_agent(name,props,pos,rot,scene)
  local a={name=name,base=props or {},runtime={},pos=Vector(pos or Vector()),rot=Vector(rot or Vector()),
           scene=scene or Fake.scene,valid=true,hidden=false,selectable=true}
  a.mProps=setmetatable({}, {__index=function(_,k)
    if a.runtime[k]~=nil then return a.runtime[k] end
    return a.base[k]
  end,__newindex=function(_,k,v) a.runtime[k]=v end})
  setmetatable(a.runtime,{__index=a.base})
  Fake.agents[name]=a
  return a
end
function AgentCreate(name,resource,pos,rot,scene,hidden)
  assert(Fake.agents[name]==nil or not Fake.agents[name].valid,"duplicate agent "..name)
  local a=Fake.new_agent(name,{},pos,rot,scene); a.hidden=hidden or false
  a.resource=resource
  local alias=string.match(name,"^(twd_fp_%a+)_%d+$")
  if alias then Fake.agents[alias]=a end
  return a
end
function AgentIsValid(a) return type(a)=="table" and a.valid==true end
function AgentExists(name) return AgentIsValid(Fake.agents[name]) end
function AgentFind(name) return Fake.agents[name] end
function AgentDestroy(a) assert(AgentIsValid(a)); a.valid=false end
function AgentGetName(a) return a.name end
function AgentGetScene(a) return a.scene end
function AgentGetParent(a) return a.parent end
function AgentGetProperties(a) return a.mProps end
function AgentGetRuntimeProperties(a) return a.runtime end
function AgentGetWorldPos(a,node)
  if node=="head" then return VectorAdd(a.pos,Vector(0,1.65,0)) end
  if a.parent then return VectorAdd(AgentGetWorldPos(a.parent,a.node),a.pos) end
  return Vector(a.pos)
end
function AgentGetWorldRot(a)
  if a.parent then return VectorAdd(AgentGetWorldRot(a.parent),a.rot) end
  return Vector(a.rot)
end
function AgentGetPos(a) return Vector(a.pos) end
function AgentGetRot(a) return Vector(a.rot) end
function AgentSetWorldPos(a,p)
  local base=a.parent and AgentGetWorldPos(a.parent,a.node) or Vector()
  a.pos=Vector(p.x-base.x,p.y-base.y,p.z-base.z)
end
function AgentSetWorldRot(a,r)
  local base=a.parent and AgentGetWorldRot(a.parent) or Vector()
  a.rot=Vector(r.x-base.x,r.y-base.y,r.z-base.z)
end
function AgentSetPos(a,p) a.pos=Vector(p) end
function AgentSetRot(a,r) a.rot=Vector(r) end
function AgentAttach(a,parent) a.parent=parent end
function AgentAttachToNode(a,parent,node) a.parent=parent; a.node=node end
function AgentHasNode(a,node) return a.hasHead and node=="head" or false end
function AgentGetForwardVec(a)
  local r=AgentGetWorldRot(a)
  return Vector(math.sin(math.rad(r.y))*math.cos(math.rad(r.x)),-math.sin(math.rad(r.x)),math.cos(math.rad(r.y))*math.cos(math.rad(r.x)))
end
function AgentLocalToWorld(a,p) return VectorAdd(AgentGetWorldPos(a),p) end
function AgentHide(a,hidden) a.hidden=hidden end
function AgentIsHidden(a) return a.hidden end
function AgentSetSelectable(a,v) a.selectable=v end
function AgentHasProperty(a,k) return a.mProps[k]~=nil end
function AgentIsParentProperty(a,name) return a.resource==name end
function AgentAtScreenPos(pos,geometry,scene)
  assert(geometry==true and scene==Fake.scene)
  assert(Fake.player.hidden,"player body must not intercept own shots")
  return Fake.hit
end
function AgentSetWorldPosFromScreenPos(a,p) a.screen=Vector(p) end
function PropertyExists(p,k,inherited)
  if inherited==false then return rawget(p,k)~=nil end
  return p[k]~=nil
end
function PropertyRemove(p,k) rawset(p,k,nil) end
function PropertyGetKeys(p)
  local result={}
  for _,a in pairs(Fake.agents) do
    if a.mProps==p then
      for k in pairs(a.base) do table.insert(result,k) end
      for k in pairs(a.runtime) do if a.base[k]==nil then table.insert(result,k) end end
      return result
    end
  end
  for k in pairs(p) do table.insert(result,k) end
  return result
end
function SymbolToString(s) return s end
function InputPCIsVKeyPressed(code) return Fake.keys[code] or false end
function InputMapperIsActive(name) return (name=="Navigate" and Fake.navigate) or (Fake.inputMaps and Fake.inputMaps[name]) or false end
function CursorGetPos() return Vector(Fake.cursor) end
function CursorSetAtScreenCenter() Fake.cursor=Vector(0.5,0.5,0) end
function CursorHide(hide,owner) Fake.cursorHidden=hide end
function CursorConfine(value) Fake.confined=value end
function SceneGetCamera(scene) return scene.camera end
function SceneGetBottomScene() return Fake.scene end
function SceneGetAgents(scene)
  local result={}; local seen={}
  for _,a in pairs(Fake.agents) do
    if a.valid and a.scene==scene and not seen[a] then result[#result+1]=a; seen[a]=true end
  end
  return result
end
function Station_GetCurrent() return Fake.station end
function ResourceGetName(scene) return scene.name end
function Mode_IsActive(mode) return mode.active end
function FileExists(name) return not Fake.missing or not Fake.missing[name] end
function GetFrameTime() return Fake.dt or 1/60 end
function EnginePostUpdate()
  Fake.originalUpdates=Fake.originalUpdates+1
  if Fake.updateReticle then ReticleController_Update() end
end
function Main_GetAvatar() return Fake.player end
function Game_GetPlayer() return Fake.player end
function Game_EnterCloseUp(name)
  Fake.beforeCloseup=Fake.scene.camera; Fake.scene.camera=AgentFind(name)
end
function Game_ExitCloseUp(name) Fake.scene.camera=Fake.beforeCloseup end
function DirectControl_OnCameraChange() end
function ThreadStart(fn,...) return fn(...) end
function ReticleController_Update()
  Fake.reticleOriginal=true
  if Fake.updateReticle then CursorSetAtScreenCenter() end
end
function ReticleController_SetScreenPos(x,y) Fake.reticle=Vector(x,y,0) end
function Reticle_SomethingHasFocus() return Fake.focus or false end
function Navigate_OnMouseL() Fake.nativeClicks=Fake.nativeClicks+1 end
Navigate_OnMouseLDouble=Navigate_OnMouseL
Navigate_OnMouseLUp=Navigate_OnMouseL
Navigate_OnMouseR=Navigate_OnMouseL
Navigate_OnMouseRUp=Navigate_OnMouseL
Navigate_OnMouseMove=Navigate_OnMouseL
function SoundPlay(name) table.insert(Fake.sounds,name) end
function ChorePlay(name) table.insert(Fake.sounds,name) end
function PlayAnimation(a,name) return {agent=a,name=name} end
function ControllerSetLooping(c,v) c.loop=v end
function ControllerSetEndPause(c,v) c.endpause=v end
function ControllerSetPriority(c,v) c.priority=v end
function ControllerKill(c) c.killed=true end
function Fake.callback()
  return {subscribers={},Add=function(self,fn) table.insert(self.subscribers,fn) end,
    Run=function(self,...) for _,fn in ipairs(self.subscribers) do fn(...) end end}
end
Callback_OnGameSceneClose=Fake.callback()
Callback_SceneOpenFinished=Fake.callback()
mode_Main={active=true}
mode_thirdperson={active=true}
mode_Reticle={active=true,OnMouseDown=function() Fake.nativeClicks=Fake.nativeClicks+1 end,
  OnChoice=function() Fake.nativeChoices=Fake.nativeChoices+1 end,
  DoAction=function() Fake.uses=(Fake.uses or 0)+1 end}
mode_DialogChoice={active=false}
mode_DialogActionChoice={active=false}
mode_choice={active=false}
mode_balance={active=false}
mode_shotgun={active=false}
mode_sniper={active=false}
mode_peek={active=false,OnDirection=function(self,event) Fake.peekEvent=event end}
mode_Cutscene_Movement={active=false}
mode_Cutscene_Interaction={active=false}
Fake.scene={name="test_scene"}
Fake.scene.camera=Fake.new_agent("camera",{["Field of View"]=55,["Clip Plane - Near"]=0.1,
  ["Depth Of Field Enabled"]=true},Vector(5,4,6),Vector(10,25,0))
Fake.player=Fake.new_agent("Lee",{["Mesh sk54_lee_head - Visible"]=true,
  ["Mesh sk54_lee_armL - Visible"]=true,["Mesh sk54_lee_legs - Visible"]=true},Vector(1,0,2),Vector())
Fake.player.hasHead=true
Fake.new_agent("ui_reticle_parent",{},nil,nil,{name="ui"})
Fake.navigate=true
function Fake.tick(count) for i=1,(count or 1) do EnginePostUpdate() end end
function Fake.press(code)
  Fake.keys[code]=true; Fake.tick(); Fake.keys[code]=false; Fake.tick()
end
