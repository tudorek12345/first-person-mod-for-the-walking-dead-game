-- Camera arithmetic independent of engine objects, in degrees.
FP_View={}
local V=FP_View
function V.finite(n) return type(n)=="number" and n==n and math.abs(n)<1000000 end
function V.valid(p) return p and V.finite(p.x) and V.finite(p.y) and V.finite(p.z) end
function V.eye_lift(height,config)
  -- A continuous transition avoids a height jump as an animation stands up.
  -- Measure relative to the avatar root, so stairs do not change the offset.
  local t=FP_Core.clamp((height-config.low_pose_height)/
    (config.standing_head_height-config.low_pose_height),0,1)
  t=t*t*(3-2*t)
  return config.low_pose_head_up+(config.head_up-config.low_pose_head_up)*t
end
local function atan2(y,x)
  if math.atan2 then return math.atan2(y,x) end
  if x>0 then return math.atan(y/x) end
  if x<0 then return math.atan(y/x)+(y>=0 and math.pi or -math.pi) end
  return y>0 and math.pi/2 or (y<0 and -math.pi/2 or 0)
end
function V.direction(from,to)
  if not V.valid(from) or not V.valid(to) then return nil end
  local x,y,z=to.x-from.x,to.y-from.y,to.z-from.z
  local flat=math.sqrt(x*x+z*z)
  if flat*flat+y*y<0.000001 then return nil end
  return -math.deg(atan2(y,flat)),math.deg(atan2(x,z))
end
function V.assist(s,dt,moved,focus,config)
  if moved then s.look_idle=0 else s.look_idle=(s.look_idle or 0)+dt end
  if focus or (config.focus_assist and s.look_idle>=config.focus_delay) then
    local amount=1-math.exp(-dt*(focus and 12 or config.focus_speed))
    s.yaw=FP_Core.wrap(s.yaw)*(1-amount)
    s.pitch=s.pitch*(1-amount)
  end
end
