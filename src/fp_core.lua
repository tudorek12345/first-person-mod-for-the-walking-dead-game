-- Engine-independent state; Lua 5.1 compatible.
FP_Core = {}
local C = FP_Core
function C.clamp(n,lo,hi) return math.max(lo,math.min(hi,n)) end
function C.wrap(n) return (n+180)%360-180 end
function C.new(config)
  local s={enabled=config.enabled,drawn=false,weapon=1,yaw=0,pitch=0,
    recoil=0,cooldown=0,reload_left=0,aim=0,magazines={},reserves={},
    trigger=false,context="inactive",shots=0}
  for i,w in ipairs(config.weapons) do
    s.magazines[i],s.reserves[i]=w.capacity,w.reserve
  end
  return s
end
function C.set_context(s,context)
  if s.context~=context then
    -- A held menu/choice click must not become a shot when gameplay resumes.
    s.trigger=true
    if context=="paused" then s.paused_from=s.context
    else
      if s.paused_from~=context then s.reload_left,s.aim=0,0 end
      s.paused_from=nil
    end
    s.context=context
  end
end
function C.select(s,index,config)
  if not config.weapons[index] or s.weapon==index then return false end
  s.weapon,s.reload_left,s.aim=index,0,0
  s.cooldown=math.max(s.cooldown,0.2)
  s.trigger=true
  return true
end
function C.reload(s,config)
  local w=config.weapons[s.weapon]
  if not s.enabled or not s.drawn or s.context~="explore" or s.reload_left>0 then return false end
  if s.magazines[s.weapon]>=w.capacity then return false end
  if not config.infinite_reserve and s.reserves[s.weapon]<=0 then return false end
  s.reload_left=w.reload
  return true
end
function C.update(s,dt,input,config)
  local events={}
  dt=C.clamp(dt or 0,0,0.1)
  if not s.enabled or s.context=="inactive" or s.context=="paused" then
    s.trigger=input.fire or false
    return events
  end
  local w=config.weapons[s.weapon]
  s.cooldown=math.max(0,s.cooldown-dt)
  s.recoil=s.recoil*math.exp(-dt*12)
  local aim=(s.drawn and s.context=="explore" and input.aim and not input.cursor) and 1 or 0
  s.aim=s.aim+(aim-s.aim)*(1-math.exp(-dt*16))
  if s.reload_left>0 then
    s.reload_left=math.max(0,s.reload_left-dt)
    if s.reload_left==0 then
      local count=w.capacity-s.magazines[s.weapon]
      if not config.infinite_reserve then
        count=math.min(count,s.reserves[s.weapon])
        s.reserves[s.weapon]=s.reserves[s.weapon]-count
      end
      s.magazines[s.weapon]=s.magazines[s.weapon]+count
      events.reloaded=true
    end
  end
  if input.look then
    local scale=config.sensitivity*(1-0.5*s.aim)
    s.yaw=C.wrap(s.yaw-(input.dx or 0)*scale)
    local sign=config.invert_y and -1 or 1
    s.pitch=C.clamp(s.pitch+(input.dy or 0)*scale*sign,-config.pitch_limit,config.pitch_limit)
  end
  local pressed=input.fire and not s.trigger
  s.trigger=input.fire or false
  if pressed and s.context=="explore" and s.drawn and input.weapon_ready and not input.cursor then
    if s.cooldown==0 and s.reload_left==0 then
      if s.magazines[s.weapon]>0 then
        s.magazines[s.weapon]=s.magazines[s.weapon]-1
        s.cooldown=w.cooldown
        s.shots=s.shots+1
        events.fired=true
        events.recoil=w.recoil
      else events.empty=true end
    end
  end
  return events
end
function C.health_after(health,damage,headshot)
  return math.max(0,health-damage*(headshot and 3 or 1))
end
