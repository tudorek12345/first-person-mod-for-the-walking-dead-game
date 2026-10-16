-- Bounded recovery of mod-owned state. Never changes story flags or navigation.
FP_Recovery={}
local R=FP_Recovery
function R.new() return {status="active",clock=0,failures={},due=0} end
function R.advance(r,dt) r.clock=r.clock+math.max(0,math.min(dt or 0,0.1)) end
function R.ready(r)
  if r.status=="blocked" then return false end
  return r.status=="active" or r.clock>=r.due
end
function R.fail(r)
  local recent={}
  for _,t in ipairs(r.failures) do if r.clock-t<60 then recent[#recent+1]=t end end
  recent[#recent+1]=r.clock; r.failures=recent
  local delays={0.25,1,3}
  r.status=#recent>3 and "blocked" or "waiting"
  r.due=r.clock+(delays[#recent] or 0)
  return r.status,#recent,r.due-r.clock
end
function R.success(r)
  local changed=r.status~="active"
  r.status="active"
  return changed
end
function R.reset(r) r.status,r.failures,r.due="active",{},0 end
