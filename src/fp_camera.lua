-- Keep authored transforms separate from our render pose, including moving rigs.
FP_Camera={}
local C=FP_Camera
local function parent(a) return AgentGetParent and AgentGetParent(a) or nil end
local function has_local(a) return parent(a) and AgentGetPos and AgentGetRot end
local function changed(a,b) return not b or VectorDistance(a,b)>0.0001 end
function C.snapshot(a)
  local p,r=AgentGetWorldPos(a),AgentGetWorldRot(a)
  assert(FP_View.valid(p) and FP_View.valid(r),"Invalid authored camera transform")
  local saved={authorPos=p,authorRot=r,authorForward=AgentGetForwardVec(a,true),props={},parent=parent(a)}
  if has_local(a) then saved.localPos,saved.localRot=AgentGetPos(a),AgentGetRot(a) end
  return saved
end
function C.observe(a,saved)
  local p,r=AgentGetWorldPos(a),AgentGetWorldRot(a)
  assert(FP_View.valid(p) and FP_View.valid(r),"Invalid observed camera transform")
  if saved.parent~=parent(a) then
    -- Native camera controllers can reparent a rig at a cut.
    saved.parent=parent(a)
    saved.localPos,saved.localRot=nil,nil
    saved.appliedLocalPos,saved.appliedLocalRot=nil,nil
    if has_local(a) then saved.localPos,saved.localRot=AgentGetPos(a),AgentGetRot(a) end
    saved.authorPos,saved.authorRot,saved.authorForward=p,r,AgentGetForwardVec(a,true)
  elseif saved.localPos then
    local lp,lr=AgentGetPos(a),AgentGetRot(a)
    if changed(lp,saved.appliedLocalPos) then saved.localPos=lp end
    if changed(lr,saved.appliedLocalRot) then saved.localRot=lr end
    -- Compute the authored world view under the CURRENT parent transform.
    -- The render pose is reapplied before returning; there is no yield here.
    AgentSetPos(a,saved.localPos); AgentSetRot(a,saved.localRot)
    saved.authorPos,saved.authorRot,saved.authorForward=AgentGetWorldPos(a),AgentGetWorldRot(a),AgentGetForwardVec(a,true)
    AgentSetPos(a,lp); AgentSetRot(a,lr)
  else
    if changed(p,saved.appliedPos) then saved.authorPos=p end
    if changed(r,saved.appliedRot) then saved.authorRot,saved.authorForward=r,AgentGetForwardVec(a,true) end
  end
end
function C.applied(a,saved)
  saved.appliedPos,saved.appliedRot=AgentGetWorldPos(a),AgentGetWorldRot(a)
  if saved.localPos then saved.appliedLocalPos,saved.appliedLocalRot=AgentGetPos(a),AgentGetRot(a) end
end
function C.restore_position(a,saved)
  if saved.localPos and saved.parent==parent(a) then
    if not saved.appliedLocalPos or not changed(AgentGetPos(a),saved.appliedLocalPos) then AgentSetPos(a,saved.localPos) end
  elseif not saved.appliedPos or not changed(AgentGetWorldPos(a),saved.appliedPos) then
    AgentSetWorldPos(a,saved.authorPos)
  end
end
function C.restore_rotation(a,saved)
  if saved.localRot and saved.parent==parent(a) then
    if not saved.appliedLocalRot or not changed(AgentGetRot(a),saved.appliedLocalRot) then AgentSetRot(a,saved.localRot) end
  elseif not saved.appliedRot or not changed(AgentGetWorldRot(a),saved.appliedRot) then
    AgentSetWorldRot(a,saved.authorRot)
  end
end
